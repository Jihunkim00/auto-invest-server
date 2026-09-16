"""Run one real-profile automation analysis without any order side effect.

This command is intentionally a developer CLI, not another scheduler. It
resolves the requested profile/owner scope and delegates the actual analysis
to the same profile-aware service used by the canonical scheduler.

Usage:
    python -m app.scripts.run_automation_shadow_once --profile-id 5 --owner-user-id 1 --slot 13:30 --no-submit

--no-submit is deliberately an explicit acknowledgement. The CLI also uses a
transaction rollback and a scoped submit interceptor so an accidental
execution path cannot reach a KIS order endpoint or leave audit rows behind.
"""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import UTC, datetime
from typing import Any, Callable, Iterator
from unittest.mock import patch

from sqlalchemy.orm import Session

from app.brokers.kis_auth_manager import KisAuthManager
from app.brokers.kis_broker import KisBroker
from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.db.database import SessionLocal
from app.db.models import User
from app.schemas.strategy_dry_run_auto_buy import ProfileAwareDryRunAutoBuyRequest
from app.services.automation_profile_service import (
    AutomationProfileNotFound,
    AutomationProfileService,
)
from app.services.kis_manual_order_service import KisManualOrderService
from app.services.kis_watchlist_preview_service import normalize_symbol_identity
from app.services.profile_aware_dry_run_auto_buy_factory import (
    build_profile_aware_dry_run_auto_buy_service,
)


CLI_TRIGGER_SOURCE = "automation_shadow_cli"
KIS_PROVIDER = "kis"
KR_MARKET = "KR"
DEFAULT_SLOT = "13:30"


class ShadowCliError(RuntimeError):
    """A user-correctable developer CLI input or scope error."""


class _ShadowSubmitAttempt(RuntimeError):
    """Raised by a scoped order interceptor before any external request."""


class _NoSubmitKisClient:
    """Delegate read-only calls while making every client submit fail closed."""

    _BLOCKED_METHODS = {
        "submit_order",
        "submit_domestic_cash_order",
        "cancel_domestic_cash_order",
    }

    def __init__(self, client: KisClient, state: dict[str, bool]) -> None:
        self._client = client
        self._state = state

    def __getattr__(self, name: str) -> Any:
        if name in self._BLOCKED_METHODS:
            return self._blocked
        return getattr(self._client, name)

    def _blocked(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs
        self._state["intercepted"] = True
        raise _ShadowSubmitAttempt("shadow CLI intercepted a KIS submit path")


def _blocked_submit(state: dict[str, bool]) -> Callable[..., Any]:
    def callback(*args: Any, **kwargs: Any) -> Any:
        del args, kwargs
        state["intercepted"] = True
        raise _ShadowSubmitAttempt("shadow CLI intercepted an order submit path")

    return callback


@contextmanager
def _shadow_safety_scope(state: dict[str, bool]) -> Iterator[None]:
    """Intercept order paths and turn every commit into a reversible flush."""
    blocked = _blocked_submit(state)
    with ExitStack() as stack:
        # The preview path is read-only today. These guards make the safety
        # property independent of market hours or runtime live-mode settings.
        for owner, method in (
            (KisClient, "submit_order"),
            (KisClient, "submit_domestic_cash_order"),
            (KisClient, "cancel_domestic_cash_order"),
            (KisClient, "_request_order"),
            (KisBroker, "submit_market_buy"),
            (KisBroker, "submit_market_buy_qty"),
            (KisBroker, "submit_market_sell"),
            (KisManualOrderService, "submit_manual"),
        ):
            stack.enter_context(patch.object(owner, method, blocked))

        # Several existing services call commit internally. Flushing keeps
        # their normal orchestration intact while the final rollback removes
        # all rows created by this CLI invocation.
        stack.enter_context(
            patch.object(Session, "commit", lambda session: session.flush())
        )
        yield


def _utc_now(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _normalize_slot(value: str) -> str:
    raw = str(value or "").strip()
    try:
        hour, minute = (int(part) for part in raw.split(":", 1))
    except (TypeError, ValueError):
        raise ShadowCliError(f"invalid slot: {value}") from None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ShadowCliError(f"invalid slot: {value}")
    return f"{hour:02d}:{minute:02d}"


def _resolve_profile(
    db: Session,
    *,
    profile_id: int,
    owner_user_id: int,
    now: datetime,
    profiles: AutomationProfileService,
) -> tuple[dict[str, Any], dict[str, Any], User]:
    owner = db.get(User, int(owner_user_id))
    if owner is None or not bool(owner.enabled):
        raise ShadowCliError(f"owner user not found or disabled: {owner_user_id}")

    try:
        if str(owner.role or "").strip().lower() == "admin":
            row = profiles.get_admin(db, str(profile_id), int(owner_user_id))
        else:
            row = profiles.get_owned(db, str(profile_id), int(owner_user_id))
    except (AutomationProfileNotFound, ValueError):
        raise ShadowCliError(
            f"profile/owner mismatch: profile_id={profile_id} owner_user_id={owner_user_id}"
        ) from None

    if int(row.id) != int(profile_id):
        raise ShadowCliError(
            f"profile/owner mismatch: profile_id={profile_id} owner_user_id={owner_user_id}"
        )
    if (
        str(owner.role or "").strip().lower() != "admin"
        and int(row.owner_user_id or 0) != int(owner_user_id)
    ):
        raise ShadowCliError(
            f"profile/owner mismatch: profile_id={profile_id} owner_user_id={owner_user_id}"
        )

    profile = profiles.serialize(row, now=now)
    if str(profile.get("provider") or "").strip().lower() != KIS_PROVIDER:
        raise ShadowCliError(f"profile provider is not kis: {profile.get('provider')}")
    if str(profile.get("market") or "").strip().upper() != KR_MARKET:
        raise ShadowCliError(f"profile market is not KR: {profile.get('market')}")
    if not bool(profile.get("enabled")) or str(profile.get("status")) != "active":
        raise ShadowCliError(
            f"profile is not active: profile_id={profile_id} status={profile.get('status')}"
        )

    schedule = profiles._profile_schedule(row, now=now)
    if not isinstance(schedule, dict) or schedule.get("status") != "active":
        raise ShadowCliError(f"profile schedule is not active: profile_id={profile_id}")
    return profile, schedule, owner


def _client_factory(state: dict[str, bool]) -> Callable[[Session], _NoSubmitKisClient]:
    def factory(db: Session) -> _NoSubmitKisClient:
        settings = get_settings()
        client = KisClient(settings, KisAuthManager(settings, db))
        return _NoSubmitKisClient(client, state)

    return factory


def _profile_budget(profile: dict[str, Any], snapshot: dict[str, Any]) -> Any:
    value = snapshot.get("effective_entry_budget_krw")
    if value is not None:
        return value
    capital = profile.get("capital")
    if isinstance(capital, dict):
        return capital.get("fixed_budget") or capital.get("initial_budget_krw")
    return None


def _as_symbols(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    symbols: list[str] = []
    for item in value:
        operand = item.get("symbol") if isinstance(item, dict) else item
        symbol = normalize_symbol_identity(operand)
        if symbol:
            symbols.append(symbol)
    return symbols


def _symbol_operand(item: Any) -> Any:
    return item.get("symbol") if isinstance(item, dict) else item


def _candidate_is_gpt_completed(item: Any) -> bool:
    return (
        isinstance(item, dict)
        and bool(item.get("gpt_used"))
        and str(item.get("gpt_analysis_status") or "").strip().lower() == "completed"
        and item.get("ai_buy_score") is not None
        and item.get("ai_sell_score") is not None
    )


def _symbol_diagnostics(value: Any) -> list[tuple[Any, str, int]]:
    values = value if isinstance(value, list) else []
    normalized = [
        normalize_symbol_identity(_symbol_operand(item))
        for item in values
    ]
    counts = Counter(symbol for symbol in normalized if symbol)
    return [
        (_symbol_operand(item), symbol, counts.get(symbol, 0))
        for item, symbol in zip(values, normalized)
    ]


def _candidate_name(item: dict[str, Any]) -> str:
    return str(item.get("name") or item.get("symbol") or "-")


def _result_with_scope(
    result: dict[str, Any],
    *,
    profile: dict[str, Any],
    owner_user_id: int,
    slot: str,
    snapshot: dict[str, Any],
    state: dict[str, bool],
) -> dict[str, Any]:
    response = dict(result)
    response["profile"] = profile
    response.setdefault("profile_id", profile.get("id"))
    response.setdefault("owner_user_id", owner_user_id)
    response.setdefault("scheduler_slot", slot)
    response.setdefault("snapshot_id", snapshot.get("id"))
    response["broker_submit_called"] = False
    response["real_order_submitted"] = False
    response["would_submit"] = bool(
        response.get("action") == "would_buy" or state.get("intercepted")
    )
    response["safety"] = {
        **(
            response.get("safety")
            if isinstance(response.get("safety"), dict)
            else {}
        ),
        "would_submit": response["would_submit"],
        "broker_submit_called": False,
        "real_order_submitted": False,
        "manual_submit_called": False,
        "db_persisted": False,
    }
    return response


def _validate_shadow_invariants(
    result: dict[str, Any],
    *,
    snapshot_selected_symbols: list[str],
    runtime_input_symbols: list[str],
) -> None:
    """Fail closed if the shadow report is not the canonical profile result."""
    if not bool(result.get("canonical_profile_pipeline")):
        return
    assert set(runtime_input_symbols) == set(snapshot_selected_symbols), (
        "snapshot selected symbols must equal runtime input symbols"
    )
    runtime_count = int(result.get("runtime_quant_candidate_count") or 0)
    assert runtime_count <= len(snapshot_selected_symbols), (
        "runtime quant candidate count must not exceed snapshot selected count"
    )
    assert not _as_symbols(result.get("unaffordable_runtime_candidates")), (
        "unaffordable runtime candidate reached the entry universe"
    )
    completed = set(_as_symbols(result.get("gpt_completed_symbols")))
    final_items = result.get("final_ranked_top5")
    final_items = final_items if isinstance(final_items, list) else []
    final_symbols = {
        normalize_symbol_identity(item.get("symbol"))
        for item in final_items
        if isinstance(item, dict) and item.get("final_rank") is not None
    }
    assert completed == final_symbols, (
        "GPT completed symbols must equal final candidate symbols"
    )
    if final_symbols:
        selected_items = [
            item for item in final_items
            if isinstance(item, dict) and bool(item.get("final_selected"))
        ]
        assert len(selected_items) == 1, "final candidate selection must contain exactly one item"
        selected_symbol = normalize_symbol_identity(result.get("selected_final_symbol") or result.get("selected_symbol"))
        rank_one = next(
            (
                normalize_symbol_identity(item.get("symbol"))
                for item in final_items
                if isinstance(item, dict) and item.get("final_rank") == 1
            ),
            "",
        )
        assert normalize_symbol_identity(selected_items[0].get("symbol")) == rank_one == selected_symbol, (
            "final selected, rank one, and selected symbol must match"
        )

def run_shadow_once(
    db: Session,
    *,
    profile_id: int,
    owner_user_id: int,
    slot: str = DEFAULT_SLOT,
    now: datetime | None = None,
    profile_service: AutomationProfileService | None = None,
    analysis_service_factory: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """Run the canonical profile analysis in a rollback-only DB scope."""
    current = _utc_now(now)
    normalized_slot = _normalize_slot(slot)
    profiles = profile_service or AutomationProfileService()
    profile, schedule, owner = _resolve_profile(
        db,
        profile_id=int(profile_id),
        owner_user_id=int(owner_user_id),
        now=current,
        profiles=profiles,
    )
    configured_slots = {
        _normalize_slot(value) for value in (schedule.get("analysis_times") or [])
    }
    if normalized_slot not in configured_slots:
        raise ShadowCliError(
            f"slot is not configured for profile: profile_id={profile_id} slot={normalized_slot}"
        )

    state = {"intercepted": False}
    from app.services.automation_profile_watchlist_service import (
        AutomationProfileWatchlistService,
    )

    snapshot_service = AutomationProfileWatchlistService()
    snapshot_result: dict[str, Any] = {}
    try:
        with _shadow_safety_scope(state):
            snapshot_result = snapshot_service.build(
                db,
                profile=profile,
                owner_user_id=(
                    int(profile["owner_user_id"])
                    if profile.get("owner_user_id") is not None
                    else None
                ),
                scheduler_slot=normalized_slot,
                now=current,
            )
            factory = (
                analysis_service_factory
                or build_profile_aware_dry_run_auto_buy_service
            )
            analysis = factory(
                db,
                client_factory=_client_factory(state),
            )
            request = ProfileAwareDryRunAutoBuyRequest(
                provider=KIS_PROVIDER,
                market=KR_MARKET,
                automation_profile_key=str(profile.get("profile_key") or "") or None,
                automation_profile_name=str(profile.get("display_name") or "") or None,
                scheduler_slot=normalized_slot,
                trigger_source=CLI_TRIGGER_SOURCE,
                use_watchlist=True,
                save_logs=False,
                max_candidates=5,
            )
            result = analysis.run_once(
                db,
                request,
                now=current,
                execution_mode="test",
            )
            if not isinstance(result, dict):
                raise ShadowCliError("canonical analysis returned a non-object result")
            response = _result_with_scope(
                result,
                profile=profile,
                owner_user_id=int(owner.id),
                slot=normalized_slot,
                snapshot=snapshot_result.get("snapshot") or {},
                state=state,
            )
    except _ShadowSubmitAttempt:
        # The interceptor has already guaranteed that no external request was
        # made. Keep the report useful if an unexpected path tries to submit.
        response = {
            "status": "blocked",
            "action": "hold",
            "reason": "shadow_submit_intercepted",
            "profile": profile,
            "profile_id": profile.get("id"),
            "owner_user_id": int(owner.id),
            "scheduler_slot": normalized_slot,
            "would_submit": True,
            "broker_submit_called": False,
            "real_order_submitted": False,
            "safety": {
                "would_submit": True,
                "broker_submit_called": False,
                "real_order_submitted": False,
                "manual_submit_called": False,
                "db_persisted": False,
            },
        }
    finally:
        # The caller supplied a fresh CLI session. Roll back even when a
        # service internally flushed rows or an unexpected error occurred.
        db.rollback()

    response["snapshot"] = snapshot_result.get("snapshot") or {}
    response["snapshot_items"] = snapshot_result.get("items") or []
    response["owner_user_id"] = int(owner.id)
    response["broker_submit_called"] = False
    response["real_order_submitted"] = False
    response["would_submit"] = bool(
        response.get("would_submit") or state.get("intercepted")
    )
    response["safety"].update(
        {
            "would_submit": response["would_submit"],
            "broker_submit_called": False,
            "real_order_submitted": False,
            "db_persisted": False,
        }
    )
    snapshot_selected_symbols = _as_symbols(
        response.get("profile_snapshot_selected_symbols")
        or [
            item.get("symbol")
            for item in response.get("snapshot_items", [])
            if isinstance(item, dict)
        ]
    )
    runtime_input_symbols = _as_symbols(response.get("runtime_input_symbols"))
    response["profile_snapshot_selected_symbols"] = snapshot_selected_symbols
    response["runtime_input_symbols"] = runtime_input_symbols
    _validate_shadow_invariants(
        response,
        snapshot_selected_symbols=snapshot_selected_symbols,
        runtime_input_symbols=runtime_input_symbols,
    )
    return response


def _value(value: Any) -> str:
    return "-" if value is None else str(value)


def _print_candidate_line(index: int, item: dict[str, Any], *, final: bool) -> None:
    symbol = item.get("symbol") or "-"
    name = _candidate_name(item)
    if not final:
        print(
            f"#{index} {name}({symbol}) "
            f"ai_buy={_value(item.get('ai_buy_score'))} "
            f"ai_sell={_value(item.get('ai_sell_score'))} "
            f"confidence={_value(item.get('confidence'))} "
            f"gpt_status={_value(item.get('gpt_analysis_status'))}"
        )
        return
    print(
        f"#{index} {name}({symbol}) "
        f"quant_buy={_value(item.get('runtime_quant_buy_score', item.get('quant_buy_score')))} "
        f"ai_buy={_value(item.get('ai_buy_score'))} "
        f"ai_sell={_value(item.get('ai_sell_score'))} "
        f"final_buy={_value(item.get('final_buy_score'))} "
        f"final_sell={_value(item.get('final_sell_score'))} "
        f"confidence={_value(item.get('confidence'))}"
    )


def print_shadow_result(result: dict[str, Any]) -> None:
    """Print the operator-facing report required by the developer command."""
    profile = (
        result.get("profile")
        if isinstance(result.get("profile"), dict)
        else {}
    )
    snapshot = (
        result.get("snapshot")
        if isinstance(result.get("snapshot"), dict)
        else {}
    )
    final_top5 = result.get("final_ranked_top5")
    if not isinstance(final_top5, list):
        final_top5 = []

    print("PROFILE")
    print(f"profile_id={result.get('profile_id', profile.get('id'))}")
    print(f"owner_user_id={result.get('owner_user_id')}")
    print(f"slot={result.get('scheduler_slot')}")
    print(f"budget={_profile_budget(profile, snapshot)}")

    print("\nSNAPSHOT")
    print(f"source_count={snapshot.get('source_count', result.get('snapshot_source_count', 0))}")
    print(f"eligible_count={snapshot.get('eligible_count', result.get('snapshot_eligible_count', 0))}")
    print(f"selected_count={snapshot.get('selected_count', result.get('snapshot_selected_count', 0))}")

    snapshot_items = result.get("snapshot_items")
    snapshot_items = snapshot_items if isinstance(snapshot_items, list) else []
    snapshot_selected_symbols = _as_symbols(
        result.get("profile_snapshot_selected_symbols")
        or [
            item.get("symbol")
            for item in snapshot_items
            if isinstance(item, dict)
        ]
    )
    runtime_input_symbols = _as_symbols(result.get("runtime_input_symbols"))
    effective_max_candidate_price = snapshot.get("effective_max_candidate_price")
    if effective_max_candidate_price is None:
        effective_max_candidate_price = result.get("effective_max_candidate_price")
    unaffordable_runtime_candidates = _as_symbols(
        result.get("unaffordable_runtime_candidates")
    )
    snapshot_first10 = ",".join(snapshot_selected_symbols[:10]) or "-"
    runtime_first10 = ",".join(runtime_input_symbols[:10]) or "-"
    print("\nSNAPSHOT SELECTED")
    print(f"count={len(snapshot_selected_symbols)}")
    print(f"first10={snapshot_first10}")
    print("\nRUNTIME INPUT")
    print(f"count={len(runtime_input_symbols)}")
    print(f"first10={runtime_first10}")
    print("\nCHECK")
    print("snapshot_selected == runtime_input : " + ("PASS" if set(snapshot_selected_symbols) == set(runtime_input_symbols) else "FAIL"))
    print("\nPROFILE AFFORDABILITY")
    print(f"effective_max_candidate_price={effective_max_candidate_price}")
    print(f"unaffordable_runtime_candidates={unaffordable_runtime_candidates}")
    # The canonical response evaluates only Final #1 for risk. Final TOP5
    # still carries all runtime quant/GPT rank projections needed for display.
    displayed_items = []
    for key in ("candidates", "gpt_top5_candidates", "final_ranked_top5"):
        values = result.get(key)
        if isinstance(values, list):
            displayed_items.extend(item for item in values if isinstance(item, dict))
    by_symbol = {
        normalize_symbol_identity(item.get("symbol")): item
        for item in displayed_items
        if str(item.get("symbol") or "").strip()
    }

    print("\nRUNTIME QUANT TOP5")
    runtime_symbols = _as_symbols(result.get("runtime_quant_top5_symbols"))
    for index, symbol in enumerate(runtime_symbols[:5], start=1):
        _print_candidate_line(index, by_symbol.get(symbol, {"symbol": symbol}), final=True)

    print("\nGPT TARGET TOP5")
    target_symbols = _as_symbols(result.get("gpt_target_symbols"))
    for index, symbol in enumerate(target_symbols[:5], start=1):
        _print_candidate_line(index, by_symbol.get(symbol, {"symbol": symbol}), final=False)

    print("\nFINAL TOP5")
    for index, item in enumerate(final_top5[:5], start=1):
        if isinstance(item, dict):
            _print_candidate_line(index, item, final=True)

    selected_symbol = result.get("selected_final_symbol") or result.get("selected_symbol")
    selected_identity = normalize_symbol_identity(selected_symbol)
    selected = next(
        (
            item
            for item in final_top5
            if isinstance(item, dict)
            and normalize_symbol_identity(item.get("symbol")) == selected_identity
        ),
        {},
    )
    risk = result.get("target_risk_result")
    risk = risk if isinstance(risk, dict) else {}
    print("\nFINAL SELECTED")
    print(f"symbol={selected_symbol or '-'}")
    print(f"name={selected.get('name') or result.get('selected_symbol_name') or '-'}")
    print(f"final_buy_score={result.get('selected_final_buy_score', result.get('final_buy_score'))}")
    print(f"required_score={result.get('required_entry_score', result.get('effective_min_entry_score'))}")
    print(f"action={result.get('action') or 'hold'}")
    print(f"risk_result={risk.get('action', risk.get('approved', '-'))}")
    print(f"block_reason={risk.get('block_reason') or result.get('reason') or '-'}")

    if result.get("preview_error"):
        print("preview_error=" + str(result.get("preview_error")))
    completed_raw = result.get("gpt_completed_symbols")
    final_symbols_raw = result.get("final_candidate_symbols")
    print("\nSYMBOL IDENTITY DIAGNOSTICS")
    for label, raw in (
        ("gpt_completed_symbols", completed_raw),
        ("final_candidate_symbols", final_symbols_raw),
    ):
        print(f"{label} raw={raw!r}")
        for operand, normalized, duplicate_count in _symbol_diagnostics(raw):
            print(
                f"{label} symbol={operand!r} "
                f"symbol_type={type(operand).__name__} "
                f"normalized={normalized!r} "
                f"duplicate_count={duplicate_count}"
            )

    completed = _as_symbols(completed_raw)
    final_ranked_symbols = [
        normalize_symbol_identity(item.get("symbol"))
        for item in final_top5
        if isinstance(item, dict) and item.get("final_rank") is not None
    ]
    final_symbols = final_ranked_symbols
    print("\nINVARIANTS")
    print(
        "snapshot_selected == runtime_input : "
        + ("PASS" if set(snapshot_selected_symbols) == set(runtime_input_symbols) else "FAIL")
    )
    print(
        "runtime_top5 == gpt_targets : "
        + ("PASS" if runtime_symbols == target_symbols else "FAIL")
    )
    print(
        "gpt_completed == final_candidates : "
        + ("PASS" if set(completed) == set(final_symbols) else "FAIL")
    )
    final_gpt_ok = bool(final_top5) and all(_candidate_is_gpt_completed(item) for item in final_top5)
    print("gpt_not_run_in_final : " + ("PASS" if final_gpt_ok else "FAIL"))
    selected_items = [
        item
        for item in final_top5
        if isinstance(item, dict) and bool(item.get("final_selected"))
    ]
    selected_count = len(selected_items)
    print("final_selected_count == 1 : " + ("PASS" if selected_count == 1 else "FAIL"))
    rank_one_identity = next(
        (
            normalize_symbol_identity(item.get("symbol"))
            for item in final_top5
            if isinstance(item, dict) and item.get("final_rank") == 1
        ),
        "",
    )
    selected_consistency = (
        selected_count == 1
        and bool(rank_one_identity)
        and normalize_symbol_identity(selected_items[0].get("symbol")) == rank_one_identity
        and selected_identity == rank_one_identity
    )
    print(
        "final_selected == final_rank1 == selected_symbol : "
        + ("PASS" if selected_consistency else "FAIL")
    )

    if len(completed) < 5:
        failed = _as_symbols(result.get("gpt_failed_symbols"))
        print("\nGPT FAILURE SUMMARY")
        print(f"gpt_requested={result.get('gpt_requested_count', len(target_symbols))}")
        print(f"gpt_completed={len(completed)}")
        print(f"gpt_failed={len(failed)}")
        print(f"replacement_count={result.get('gpt_replacement_count', 0)}")
        print(f"failed_symbols={','.join(failed)}")

    safety = result.get("safety") if isinstance(result.get("safety"), dict) else {}
    print("\nSAFETY")
    print(f"would_submit={str(bool(result.get('would_submit'))).lower()}")
    print(f"broker_submit_called={str(bool(safety.get('broker_submit_called'))).lower()}")
    print(f"real_order_submitted={str(bool(safety.get('real_order_submitted'))).lower()}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one real KIS automation profile analysis with an absolute no-submit guard."
    )
    parser.add_argument("--profile-id", required=True, type=int)
    parser.add_argument("--owner-user-id", required=True, type=int)
    parser.add_argument("--slot", default=DEFAULT_SLOT)
    parser.add_argument(
        "--no-submit",
        action="store_true",
        help="required acknowledgement; no broker submit is ever allowed",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.no_submit:
        print("ERROR: --no-submit is required for shadow automation CLI", file=sys.stderr)
        return 2

    db = SessionLocal()
    try:
        result = run_shadow_once(
            db,
            profile_id=args.profile_id,
            owner_user_id=args.owner_user_id,
            slot=args.slot,
        )
        print_shadow_result(result)
        return 0
    except ShadowCliError as exc:
        db.rollback()
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        db.rollback()
        print(
            f"ERROR: shadow automation failed: {exc.__class__.__name__}: {exc}",
            file=sys.stderr,
        )
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
