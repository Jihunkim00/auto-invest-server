"""One-time reconciliation script for KIS scheduler sell runs.

Usage:
  python -m app.scripts.reconcile_kis_scheduler_sell_runs --order-id 49 [--apply]
  python -m app.scripts.reconcile_kis_scheduler_sell_runs --order-id 49 --run-id 371 [--apply]
  python -m app.scripts.reconcile_kis_scheduler_sell_runs --order-id 49 --run-ids 371,372,373 [--apply]

By default runs in dry-run mode and will not modify the database.
Only when `--apply` is provided will the script persist changes.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import OrderLog, TradeRunLog


ALLOWED_ORDER_STATUSES = {"FILLED", "SUBMITTED", "ACCEPTED", "PARTIALLY_FILLED"}
ALLOWED_EXPLICIT_MODES = {
    "kis_limited_auto_stop_loss_run",
    "kis_scheduler_guarded_sell",
    "kis_scheduler_live_once",
}


def _parse_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _matches_response_order_id(payload: dict[str, Any], order_id: int) -> bool:
    # Look for order_id keys on top-level or inside trade_result
    if not isinstance(payload, dict):
        return False
    if payload.get("order_id") == order_id:
        return True
    if payload.get("related_order_id") == order_id:
        return True
    trade_result = payload.get("trade_result")
    if isinstance(trade_result, dict):
        if trade_result.get("order_id") == order_id:
            return True
    return False


def _validate_order_for_reconciliation(order: OrderLog | None) -> str | None:
    """Validate OrderLog for reconciliation. Return error message if invalid, None if valid."""
    if order is None:
        return "Order not found"

    provider = (order.broker or "").lower()
    if provider != "kis":
        return f"broker is not 'kis' (found '{order.broker}')"

    if (order.market or "").upper() != "KR":
        return "market is not 'KR'"

    if (order.side or "").lower() != "sell":
        return "side is not 'sell'"

    status = str(order.internal_status or "").upper()
    if status not in ALLOWED_ORDER_STATUSES:
        return f"internal_status '{order.internal_status}' not in allowed set"

    if not (order.kis_odno or order.broker_order_id):
        return "no kis_odno or broker_order_id"

    return None


def _validate_explicit_run(run: TradeRunLog | None, order: OrderLog) -> str | None:
    """Validate explicit TradeRunLog for reconciliation. Return error message if invalid, None if valid."""
    if run is None:
        return "Run not found"

    mode = str(run.mode or "").lower()
    if mode not in ALLOWED_EXPLICIT_MODES:
        return f"mode '{run.mode}' not in allowed set"

    # symbol must match order symbol or be WATCHLIST or null
    if run.symbol and run.symbol != order.symbol and run.symbol.upper() != "WATCHLIST":
        return f"symbol '{run.symbol}' does not match order symbol '{order.symbol}' and is not WATCHLIST/null"

    return None


def _get_auto_linked_runs(session, order: OrderLog) -> list[TradeRunLog]:
    """Find automatically linked runs via order_id column or payload references."""
    linked: list[TradeRunLog] = []
    rows = session.execute(select(TradeRunLog).where(TradeRunLog.symbol == order.symbol)).scalars().all()

    for row in rows:
        # Connected if order_id column equals or response/request payload contains order_id
        try:
            if row.order_id == order.id:
                linked.append(row)
                continue
        except Exception:
            pass

        response_payload = _parse_json(row.response_payload)
        request_payload = _parse_json(row.request_payload)
        if _matches_response_order_id(response_payload, order.id) or _matches_response_order_id(request_payload, order.id):
            linked.append(row)

    return linked


def _get_explicit_runs(session, order: OrderLog, run_ids: list[int]) -> list[TradeRunLog]:
    """Validate explicit run-ids and return runs that pass validation."""
    explicit: list[TradeRunLog] = []

    for run_id in run_ids:
        run = session.get(TradeRunLog, run_id)
        error = _validate_explicit_run(run, order)
        if error:
            print(f"Skipping run {run_id}: {error}.")
            continue
        explicit.append(run)

    return explicit


def _reconcile_runs(
    session,
    order: OrderLog,
    runs: list[TradeRunLog],
    apply: bool = False,
) -> None:
    """Reconcile TradeRunLog runs linked to an OrderLog."""
    to_fix: list[TradeRunLog] = []

    for row in runs:
        reason_text = str(row.reason or "").lower()
        # Only adjust blocked/manual-submit-blocked runs
        if row.result not in {"blocked", "manual_submit_blocked"} and "manual_submit" not in reason_text:
            print(f"Skipping run {row.id}: not blocked/manual_submit_blocked (result={row.result}, reason={row.reason}).")
            continue
        to_fix.append(row)

    if not to_fix:
        print("No runs require reconciliation.")
        return

    print(f"Preparing to reconcile {len(to_fix)} run(s) for order {order.id}.")

    for row in to_fix:
        orig_payload = _parse_json(row.response_payload)
        updated_payload = dict(orig_payload)  # copy

        # Determine final result and reason
        st = str(order.internal_status or "").upper()
        if st in {"FILLED", "PARTIALLY_FILLED"}:
            new_result = "filled"
            new_reason = "kis_sell_filled"
        else:
            new_result = "submitted"
            new_reason = "kis_sell_submitted"

        # update fields
        updated_payload.update(
            {
                "action": "sell",
                "result": new_result,
                "reason": new_reason,
                "order_id": order.id,
                "related_order_id": order.id,
                "real_order_submitted": True,
                "broker_submit_called": True,
                "manual_submit_called": False,
                "kis_odno": order.kis_odno,
                "broker_order_id": order.broker_order_id,
                "reconciled_from_order": True,
                "reconciliation_reason": "linked_kis_sell_order_filled",
                "scheduler_origin": True,
                "operator_manual_click": False,
                "execution_path": "limited_auto_sell_via_manual_order_service",
            }
        )

        # idempotent: skip if already reconciled
        already_reconciled = (
            row.order_id == order.id
            and str(row.result or "").lower() == new_result
            and isinstance(orig_payload, dict)
            and orig_payload.get("reconciled_from_order") is True
        )
        if already_reconciled:
            print(f"Run {row.id}: already reconciled; skipping write.")
            continue

        print(f"Run {row.id}: set result={new_result}, reason={new_reason}, order_id={order.id}")

        if apply:
            row.result = new_result
            row.reason = new_reason
            row.order_id = order.id
            # persist updated response_payload as JSON string
            try:
                row.response_payload = json.dumps(updated_payload, ensure_ascii=False)
            except Exception:
                # fallback: stringify
                row.response_payload = str(updated_payload)

    if apply:
        session.commit()
        print(f"Applied changes to {len(to_fix)} run(s).")
    else:
        print("Dry-run complete; no database changes applied.")



def reconcile_order(
    order_id: int,
    apply: bool = False,
    run_ids: list[int] | None = None,
) -> None:
    """Reconcile TradeRunLog rows linked to an OrderLog (auto or explicit)."""
    session = SessionLocal()
    try:
        order = session.get(OrderLog, order_id)
        error = _validate_order_for_reconciliation(order)
        if error:
            print(f"Order {order_id}: {error}; skipping.")
            return

        # Collect candidate runs: explicit (if provided) + auto (if no explicit)
        candidate_runs: list[TradeRunLog] = []

        if run_ids:
            # Explicit run-ids: validate without requiring order_id column linkage
            candidate_runs.extend(_get_explicit_runs(session, order, run_ids))
        else:
            # Auto-linked: require order_id column or payload linkage
            candidate_runs.extend(_get_auto_linked_runs(session, order))

        if not candidate_runs:
            if run_ids:
                print(f"No valid runs among explicit run-ids {run_ids}.")
            else:
                print(f"No linked TradeRunLog rows found for order {order_id} (symbol={order.symbol}).")
            return

        print(f"Found {len(candidate_runs)} candidate TradeRunLog row(s) for order {order_id} (dry-run={not apply}).")

        # Reconcile identified runs
        _reconcile_runs(session, order, candidate_runs, apply=apply)

    finally:
        session.close()



def main() -> None:
    parser = argparse.ArgumentParser(description="Reconcile historical KIS scheduler sell runs using an OrderLog.")
    parser.add_argument("--order-id", type=int, required=True, help="OrderLog.id to reconcile from")
    parser.add_argument("--apply", action="store_true", help="Persist changes to the database (default: dry-run)")
    parser.add_argument("--dry-run", action="store_true", help="Explicit dry-run (no DB changes)")
    parser.add_argument(
        "--run-id",
        type=int,
        help="Optional TradeRunLog.id to limit reconciliation to a specific run"
    )
    parser.add_argument(
        "--run-ids",
        type=str,
        help="Optional comma-separated TradeRunLog.ids to reconcile specific runs"
    )

    args = parser.parse_args()
    
    if args.dry_run and args.apply:
        parser.error("cannot specify both --dry-run and --apply")

    # Collect run_ids from either --run-id or --run-ids
    run_ids_list: list[int] | None = None
    if args.run_id is not None:
        run_ids_list = [args.run_id]
    elif args.run_ids:
        try:
            run_ids_list = [int(rid.strip()) for rid in args.run_ids.split(",") if rid.strip()]
        except ValueError as e:
            parser.error(f"Invalid --run-ids format: {e}")

    reconcile_order(args.order_id, apply=args.apply, run_ids=run_ids_list)


if __name__ == "__main__":
    main()

