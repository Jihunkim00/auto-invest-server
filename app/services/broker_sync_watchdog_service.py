from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.brokers.kis_broker import KisBroker
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, TradeRunLog
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "broker_sync_watchdog"
PROVIDER = "kis"
MARKET = "KR"
LOCAL_OPEN_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
    "PENDING_SUBMIT",
    "PENDING_SYNC",
    "SYNC_REQUIRED",
}
LOCAL_TERMINAL_STATUSES = {
    InternalOrderStatus.FILLED.value,
    InternalOrderStatus.CANCELED.value,
    InternalOrderStatus.REJECTED.value,
    InternalOrderStatus.EXPIRED.value,
    InternalOrderStatus.FAILED.value,
    InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
    InternalOrderStatus.DRY_RUN_SIMULATED.value,
}
PENDING_SYNC_STATUSES = {
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
    "PENDING_SYNC",
    "SYNC_REQUIRED",
    "UNKNOWN",
}
LIVE_ID_STATUSES = {
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}


class BrokerSyncWatchdogService:
    """Read-only broker/local reconciliation watchdog."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        broker_factory: Callable[[Session], Any] | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.broker_factory = broker_factory or (lambda db: KisBroker())

    def status(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        persist: bool = False,
        allow_broker_reads: bool | None = None,
        now: datetime | None = None,
        trigger_source: str = "manual_watchdog_status",
    ) -> dict[str, Any]:
        now_utc = _utc(now)
        safe_provider = _provider(provider)
        safe_market = _market(market, safe_provider)
        settings = self.runtime_settings.get_settings_read_only(db)
        stale_order_minutes = max(
            1,
            _int(settings.get("broker_sync_watchdog_stale_order_minutes"), 10),
        )
        stale_position_minutes = max(
            1,
            _int(settings.get("broker_sync_watchdog_stale_position_minutes"), 10),
        )
        read_broker = (
            bool(settings.get("broker_sync_watchdog_allow_broker_reads", True))
            if allow_broker_reads is None
            else bool(allow_broker_reads)
        )

        local_orders = self._local_orders(
            db,
            provider=safe_provider,
            market=safe_market,
        )
        open_local = [row for row in local_orders if _is_open_order(row)]
        issues: list[dict[str, Any]] = []
        for row in local_orders:
            issues.extend(
                self._local_order_issues(
                    row,
                    provider=safe_provider,
                    market=safe_market,
                    now_utc=now_utc,
                    stale_order_minutes=stale_order_minutes,
                )
            )

        broker_open_orders: list[dict[str, Any]] = []
        broker_positions: list[dict[str, Any]] = []
        account_payload: dict[str, Any] | None = None
        broker_read_failed = False
        if read_broker:
            try:
                broker = self.broker_factory(db)
                broker_open_orders = _as_dict_list(broker.list_open_orders())
                broker_positions = _as_dict_list(broker.list_positions())
                account = broker.get_account()
                account_payload = account if isinstance(account, dict) else {}
            except Exception as exc:
                broker_read_failed = True
                issues.append(
                    self._issue(
                        issue_type="broker_read_failed",
                        severity="critical",
                        provider=safe_provider,
                        market=safe_market,
                        detected_at=now_utc,
                        automation_blocking=True,
                        recommended_action="inspect_broker_app",
                        reason="read_only_broker_state_unavailable",
                        sanitized_context={"error": _safe_error(exc)},
                    )
                )
        else:
            issues.append(
                self._issue(
                    issue_type="broker_read_failed",
                    severity="warning",
                    provider=safe_provider,
                    market=safe_market,
                    detected_at=now_utc,
                    automation_blocking=False,
                    recommended_action="manual_review",
                    reason="broker_reads_disabled_by_watchdog_setting",
                    sanitized_context={"broker_reads_enabled": False},
                )
            )

        if read_broker and not broker_read_failed:
            issues.extend(
                self._broker_order_issues(
                    open_local=open_local,
                    broker_open_orders=broker_open_orders,
                    provider=safe_provider,
                    market=safe_market,
                    detected_at=now_utc,
                )
            )
            issues.extend(
                self._position_issues(
                    local_orders=local_orders,
                    broker_positions=broker_positions,
                    provider=safe_provider,
                    market=safe_market,
                    detected_at=now_utc,
                )
            )

        stale_position_snapshot_count = self._stale_position_snapshot_count(
            db,
            now_utc=now_utc,
            stale_position_minutes=stale_position_minutes,
        )
        if stale_position_snapshot_count:
            issues.append(
                self._issue(
                    issue_type="unknown",
                    severity="warning",
                    provider=safe_provider,
                    market=safe_market,
                    detected_at=now_utc,
                    automation_blocking=False,
                    recommended_action="manual_review",
                    reason="position_management_snapshot_stale",
                    sanitized_context={
                        "stale_position_snapshot_count": stale_position_snapshot_count
                    },
                )
            )

        last_successful_sync_at = _max_dt(
            [row.last_synced_at for row in local_orders if row.last_synced_at is not None]
        )
        last_watchdog_run_at = self._last_watchdog_run_at(db)
        response = self._response(
            settings=settings,
            provider=safe_provider,
            market=safe_market,
            now_utc=now_utc,
            local_orders=local_orders,
            open_local=open_local,
            broker_open_orders=broker_open_orders,
            issues=issues,
            broker_read_failed=broker_read_failed,
            stale_position_snapshot_count=stale_position_snapshot_count,
            cash_snapshot_stale=False if account_payload is not None else False,
            last_successful_sync_at=last_successful_sync_at,
            last_watchdog_run_at=last_watchdog_run_at,
        )
        if persist:
            response = self._save_run(
                db,
                response=response,
                trigger_source=trigger_source,
                now_utc=now_utc,
            )
        return response

    def run_once(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        now: datetime | None = None,
        trigger_source: str = "manual_watchdog_run_once",
    ) -> dict[str, Any]:
        return self.status(
            db,
            provider=provider,
            market=market,
            persist=True,
            now=now,
            trigger_source=trigger_source,
        )

    def latest(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )
        if row is not None:
            payload = _json_dict(row.response_payload)
            if payload:
                payload["run_id"] = payload.get("run_id") or row.id
                return sanitize_kis_payload(payload)
        return self.status(
            db,
            provider=provider,
            market=market,
            allow_broker_reads=False,
            persist=False,
            now=now,
            trigger_source="latest_without_run",
        )

    def _local_orders(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> list[OrderLog]:
        return (
            db.query(OrderLog)
            .filter(OrderLog.broker == provider)
            .filter(or_(OrderLog.market == market, OrderLog.market.is_(None)))
            .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
            .limit(1000)
            .all()
        )

    def _local_order_issues(
        self,
        row: OrderLog,
        *,
        provider: str,
        market: str,
        now_utc: datetime,
        stale_order_minutes: int,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        status = _status(row)
        age = _age_minutes(now_utc, _latest_order_time(row))
        needs_sync = _needs_sync(row)
        if _is_open_order(row) and age is not None and age > stale_order_minutes:
            issues.append(
                self._issue(
                    issue_type="stale_local_order",
                    severity="critical",
                    provider=provider,
                    market=market,
                    detected_at=now_utc,
                    symbol=row.symbol,
                    order_id=row.id,
                    broker_order_id=_text(row.broker_order_id),
                    kis_odno=_text(row.kis_odno),
                    age_minutes=age,
                    local_status=status,
                    broker_status=_broker_status(row),
                    local_quantity=_quantity(row),
                    automation_blocking=True,
                    recommended_action="run_sync",
                    reason="local_open_order_exceeded_watchdog_stale_threshold",
                    sanitized_context=_order_context(row),
                )
            )
        if needs_sync:
            issues.append(
                self._issue(
                    issue_type="pending_sync_order",
                    severity="critical",
                    provider=provider,
                    market=market,
                    detected_at=now_utc,
                    symbol=row.symbol,
                    order_id=row.id,
                    broker_order_id=_text(row.broker_order_id),
                    kis_odno=_text(row.kis_odno),
                    age_minutes=age,
                    local_status=status,
                    broker_status=_broker_status(row),
                    local_quantity=_quantity(row),
                    automation_blocking=True,
                    recommended_action="run_sync",
                    reason="local_order_requires_broker_status_reconciliation",
                    sanitized_context=_order_context(row),
                )
            )
        if _live_order_requiring_identifier(row) and not _text(row.broker_order_id):
            issues.append(
                self._issue(
                    issue_type="missing_broker_order_id",
                    severity="critical",
                    provider=provider,
                    market=market,
                    detected_at=now_utc,
                    symbol=row.symbol,
                    order_id=row.id,
                    kis_odno=_text(row.kis_odno),
                    age_minutes=age,
                    local_status=status,
                    broker_status=_broker_status(row),
                    local_quantity=_quantity(row),
                    automation_blocking=True,
                    recommended_action="manual_review",
                    reason="live_local_order_missing_broker_order_id",
                    sanitized_context=_order_context(row),
                )
            )
        if provider == "kis" and _live_order_requiring_identifier(row) and not _text(row.kis_odno):
            issues.append(
                self._issue(
                    issue_type="missing_kis_odno",
                    severity="critical",
                    provider=provider,
                    market=market,
                    detected_at=now_utc,
                    symbol=row.symbol,
                    order_id=row.id,
                    broker_order_id=_text(row.broker_order_id),
                    age_minutes=age,
                    local_status=status,
                    broker_status=_broker_status(row),
                    local_quantity=_quantity(row),
                    automation_blocking=True,
                    recommended_action="manual_review",
                    reason="kis_live_order_missing_odno",
                    sanitized_context=_order_context(row),
                )
            )
        return issues

    def _broker_order_issues(
        self,
        *,
        open_local: list[OrderLog],
        broker_open_orders: list[dict[str, Any]],
        provider: str,
        market: str,
        detected_at: datetime,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        local_by_key: dict[str, OrderLog] = {}
        for row in open_local:
            for key in _local_order_keys(row):
                local_by_key[key] = row
        broker_keys: set[str] = set()
        for item in broker_open_orders:
            order_key = _broker_order_key(item)
            if order_key:
                broker_keys.add(order_key)
            if not order_key or order_key not in local_by_key:
                issues.append(
                    self._issue(
                        issue_type="broker_order_missing_local_record",
                        severity="critical",
                        provider=provider,
                        market=market,
                        detected_at=detected_at,
                        symbol=_symbol(item),
                        broker_order_id=order_key,
                        kis_odno=order_key if provider == "kis" else None,
                        broker_status=_broker_item_status(item),
                        broker_quantity=_float_or_none(
                            item.get("unfilled_qty") or item.get("qty")
                        ),
                        automation_blocking=True,
                        recommended_action="manual_review",
                        reason="broker_open_order_has_no_matching_local_order",
                        sanitized_context=_broker_order_context(item),
                    )
                )
        for row in open_local:
            keys = _local_order_keys(row)
            if keys and not any(key in broker_keys for key in keys):
                issues.append(
                    self._issue(
                        issue_type="local_order_missing_broker_record",
                        severity="critical",
                        provider=provider,
                        market=market,
                        detected_at=detected_at,
                        symbol=row.symbol,
                        order_id=row.id,
                        broker_order_id=_text(row.broker_order_id),
                        kis_odno=_text(row.kis_odno),
                        local_status=_status(row),
                        broker_status="not_found_in_open_orders",
                        local_quantity=_quantity(row),
                        automation_blocking=True,
                        recommended_action="manual_review",
                        reason="local_open_order_not_found_in_broker_open_orders",
                        sanitized_context=_order_context(row),
                    )
                )
            elif not keys:
                issues.append(
                    self._issue(
                        issue_type="ambiguous_order_state",
                        severity="critical",
                        provider=provider,
                        market=market,
                        detected_at=detected_at,
                        symbol=row.symbol,
                        order_id=row.id,
                        local_status=_status(row),
                        broker_status=_broker_status(row),
                        local_quantity=_quantity(row),
                        automation_blocking=True,
                        recommended_action="manual_review",
                        reason="local_open_order_has_no_broker_identifier_for_matching",
                        sanitized_context=_order_context(row),
                    )
                )
        return issues

    def _position_issues(
        self,
        *,
        local_orders: list[OrderLog],
        broker_positions: list[dict[str, Any]],
        provider: str,
        market: str,
        detected_at: datetime,
    ) -> list[dict[str, Any]]:
        issues: list[dict[str, Any]] = []
        local_positions = _local_positions_from_orders(local_orders)
        broker_by_symbol: dict[str, float] = {}
        for item in broker_positions:
            symbol = _symbol(item)
            qty = _float_or_none(item.get("qty") or item.get("quantity")) or 0.0
            if symbol and qty > 0:
                broker_by_symbol[symbol] = broker_by_symbol.get(symbol, 0.0) + qty
        for symbol, local_qty in local_positions.items():
            broker_qty = broker_by_symbol.get(symbol, 0.0)
            if broker_qty <= 0:
                issues.append(
                    self._issue(
                        issue_type="position_symbol_mismatch",
                        severity="critical",
                        provider=provider,
                        market=market,
                        detected_at=detected_at,
                        symbol=symbol,
                        local_quantity=local_qty,
                        broker_quantity=0.0,
                        automation_blocking=True,
                        recommended_action="manual_review",
                        reason="local_position_missing_from_broker_positions",
                        sanitized_context={"source": "filled_local_orders"},
                    )
                )
                continue
            if abs(local_qty - broker_qty) > 1e-6:
                issues.append(
                    self._issue(
                        issue_type="position_quantity_mismatch",
                        severity="critical",
                        provider=provider,
                        market=market,
                        detected_at=detected_at,
                        symbol=symbol,
                        local_quantity=local_qty,
                        broker_quantity=broker_qty,
                        automation_blocking=True,
                        recommended_action="manual_review",
                        reason="local_and_broker_position_quantities_differ",
                        sanitized_context={"source": "filled_local_orders"},
                    )
                )
        for symbol, broker_qty in broker_by_symbol.items():
            if symbol not in local_positions:
                issues.append(
                    self._issue(
                        issue_type="position_symbol_mismatch",
                        severity="critical",
                        provider=provider,
                        market=market,
                        detected_at=detected_at,
                        symbol=symbol,
                        local_quantity=0.0,
                        broker_quantity=broker_qty,
                        automation_blocking=True,
                        recommended_action="manual_review",
                        reason="broker_position_missing_from_local_filled_orders",
                        sanitized_context={"source": "broker_positions"},
                    )
                )
        return issues

    def _stale_position_snapshot_count(
        self,
        db: Session,
        *,
        now_utc: datetime,
        stale_position_minutes: int,
    ) -> int:
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == "position_management_dry_run")
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )
        if row is None or row.created_at is None:
            return 0
        age = _age_minutes(now_utc, row.created_at)
        return 1 if age is not None and age > stale_position_minutes else 0

    def _response(
        self,
        *,
        settings: dict[str, Any],
        provider: str,
        market: str,
        now_utc: datetime,
        local_orders: list[OrderLog],
        open_local: list[OrderLog],
        broker_open_orders: list[dict[str, Any]],
        issues: list[dict[str, Any]],
        broker_read_failed: bool,
        stale_position_snapshot_count: int,
        cash_snapshot_stale: bool,
        last_successful_sync_at: datetime | None,
        last_watchdog_run_at: datetime | None,
    ) -> dict[str, Any]:
        issues = sanitize_kis_payload(issues)
        critical_count = len(
            [item for item in issues if item.get("severity") == "critical"]
        )
        warning_count = len(
            [item for item in issues if item.get("severity") == "warning"]
        )
        if broker_read_failed:
            health = "unknown"
        elif critical_count:
            health = "unsafe"
        elif warning_count:
            health = "warning"
        else:
            health = "healthy"
        pending_sync_count = _count_issue(issues, "pending_sync_order")
        ambiguous_count = _count_issue(issues, "ambiguous_order_state")
        block_on_unsafe = bool(
            settings.get("broker_sync_watchdog_block_automation_on_unsafe", True)
        )
        should_block_auto_buy = bool(
            critical_count
            or pending_sync_count
            or health in {"unsafe", "unknown"}
        )
        should_block_auto_sell = bool(
            critical_count
            or ambiguous_count
            or health in {"unsafe", "unknown"}
        )
        should_block_orchestrator = health in {"unsafe", "unknown"}
        automation_blocked = bool(
            block_on_unsafe
            and (
                should_block_auto_buy
                or should_block_auto_sell
                or should_block_orchestrator
            )
        )
        blocking_reasons = _dedupe(
            [
                str(item.get("issue_type"))
                for item in issues
                if item.get("automation_blocking")
            ]
        )
        warning_reasons = _dedupe(
            [
                str(item.get("issue_type"))
                for item in issues
                if item.get("severity") in {"warning", "info"}
            ]
        )
        risk_flags = _dedupe(
            [
                "broker_sync_health_unknown" if health == "unknown" else "",
                "broker_sync_unsafe" if health == "unsafe" else "",
                "broker_sync_warnings" if health == "warning" else "",
                *blocking_reasons,
            ]
        )
        response = {
            "run_id": None,
            "generated_at": now_utc.isoformat(),
            "provider": provider,
            "market": market,
            "watchdog_enabled": bool(
                settings.get("broker_sync_watchdog_enabled", False)
            ),
            "automation_blocked_by_sync": automation_blocked,
            "sync_health": health,
            "can_run_automation": health not in {"unsafe", "unknown"},
            "should_block_auto_buy": should_block_auto_buy,
            "should_block_auto_sell": should_block_auto_sell,
            "should_block_orchestrator": should_block_orchestrator,
            "local_order_count": len(local_orders),
            "open_local_order_count": len(open_local),
            "broker_open_order_count": len(broker_open_orders),
            "stale_local_order_count": _count_issue(issues, "stale_local_order"),
            "pending_sync_order_count": pending_sync_count,
            "missing_broker_id_count": _count_issue(
                issues,
                "missing_broker_order_id",
            ),
            "missing_kis_odno_count": _count_issue(issues, "missing_kis_odno"),
            "broker_unmatched_order_count": _count_issue(
                issues,
                "broker_order_missing_local_record",
            ),
            "local_unmatched_order_count": _count_issue(
                issues,
                "local_order_missing_broker_record",
            )
            + ambiguous_count,
            "stale_position_snapshot_count": stale_position_snapshot_count,
            "position_mismatch_count": _count_issue(
                issues,
                "position_quantity_mismatch",
            )
            + _count_issue(issues, "position_symbol_mismatch"),
            "cash_snapshot_stale": bool(cash_snapshot_stale),
            "last_successful_sync_at": _iso(last_successful_sync_at),
            "last_watchdog_run_at": _iso(last_watchdog_run_at),
            "issues": issues,
            "summary": _summary(health, len(issues), blocking_reasons),
            "risk_flags": risk_flags,
            "gating_notes": _gating_notes(health, settings),
            "blocking_reasons": blocking_reasons,
            "warning_reasons": warning_reasons,
            "next_safe_action": _next_safe_action(health, issues),
            "safety_flags": {
                "read_only": True,
                "real_order_submitted": False,
                "broker_submit_called": False,
                "manual_submit_called": False,
                "order_cancel_called": False,
                "settings_changed": False,
                "scheduler_changed": False,
                "dry_run_changed": False,
                "kill_switch_changed": False,
                "kis_real_order_enabled_changed": False,
                "automation_mode_changed": False,
                "local_status_updates_allowed": bool(
                    settings.get(
                        "broker_sync_watchdog_allow_local_status_updates",
                        False,
                    )
                ),
                "order_submit_allowed": False,
                "order_cancel_allowed": False,
            },
        }
        return sanitize_kis_payload(response)

    def _issue(
        self,
        *,
        issue_type: str,
        severity: str,
        provider: str,
        market: str,
        detected_at: datetime,
        automation_blocking: bool,
        recommended_action: str,
        reason: str,
        symbol: str | None = None,
        order_id: int | None = None,
        broker_order_id: str | None = None,
        kis_odno: str | None = None,
        age_minutes: float | None = None,
        local_status: str | None = None,
        broker_status: str | None = None,
        local_quantity: float | None = None,
        broker_quantity: float | None = None,
        sanitized_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        core = ":".join(
            [
                issue_type,
                str(order_id or ""),
                str(symbol or ""),
                str(broker_order_id or kis_odno or ""),
                reason,
            ]
        )
        return {
            "issue_id": f"bsw_{uuid.uuid5(uuid.NAMESPACE_URL, core).hex[:16]}",
            "issue_type": issue_type,
            "severity": severity,
            "provider": provider,
            "market": market,
            "symbol": _text(symbol),
            "order_id": order_id,
            "broker_order_id": _text(broker_order_id),
            "kis_odno": _text(kis_odno),
            "detected_at": detected_at.isoformat(),
            "age_minutes": None if age_minutes is None else round(age_minutes, 2),
            "local_status": _text(local_status),
            "broker_status": _text(broker_status),
            "local_quantity": local_quantity,
            "broker_quantity": broker_quantity,
            "automation_blocking": bool(automation_blocking),
            "recommended_action": recommended_action,
            "reason": reason,
            "sanitized_context": sanitize_kis_payload(sanitized_context or {}),
        }

    def _save_run(
        self,
        db: Session,
        *,
        response: dict[str, Any],
        trigger_source: str,
        now_utc: datetime,
    ) -> dict[str, Any]:
        safe_response = sanitize_kis_payload(response)
        row = TradeRunLog(
            run_key=f"broker_sync_watchdog_{uuid.uuid4().hex[:12]}",
            trigger_source=str(trigger_source or "manual_watchdog_run_once")[:40],
            symbol="BROKER_SYNC",
            mode=MODE,
            stage="done",
            result=str(safe_response.get("sync_health") or "unknown")[:40],
            reason=_text(
                (safe_response.get("blocking_reasons") or [""])[0]
                if isinstance(safe_response.get("blocking_reasons"), list)
                else None
            ),
            request_payload=_json(
                {
                    "provider": safe_response.get("provider"),
                    "market": safe_response.get("market"),
                    "trigger_source": trigger_source,
                    "read_only": True,
                    "real_order_submitted": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "order_cancel_called": False,
                }
            ),
            response_payload=_json(safe_response),
            created_at=now_utc.replace(tzinfo=None),
        )
        db.add(row)
        db.flush()
        safe_response["run_id"] = row.id
        safe_response["last_watchdog_run_at"] = now_utc.isoformat()
        row.response_payload = _json(safe_response)
        db.commit()
        return sanitize_kis_payload(safe_response)

    def _last_watchdog_run_at(self, db: Session) -> datetime | None:
        row = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )
        return _utc(row.created_at) if row is not None and row.created_at else None


def _provider(value: str | None) -> str:
    provider = str(value or PROVIDER).strip().lower()
    if provider != "kis":
        raise ValueError("broker sync watchdog supports provider=kis only.")
    return provider


def _market(value: str | None, provider: str) -> str:
    market = str(value or ("KR" if provider == "kis" else "US")).strip().upper()
    if provider == "kis" and market != "KR":
        raise ValueError("broker sync watchdog supports market=KR only.")
    return market


def _utc(value: Any | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        value = datetime.fromisoformat(text)
    if not isinstance(value, datetime):
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _iso(value: Any | None) -> str | None:
    if value is None:
        return None
    return _utc(value).isoformat()


def _status(row: OrderLog) -> str:
    return str(row.internal_status or "").strip().upper()


def _side(row: OrderLog) -> str:
    return str(row.side or "").strip().lower()


def _broker_status(row: OrderLog) -> str | None:
    text = str(row.broker_status or row.broker_order_status or "").strip()
    return text or None


def _broker_text(row: OrderLog) -> str:
    return " ".join(
        [
            str(row.broker_status or ""),
            str(row.broker_order_status or ""),
            str(row.sync_error or ""),
        ]
    ).lower()


def _needs_sync(row: OrderLog) -> bool:
    status = _status(row)
    broker_text = _broker_text(row)
    return (
        status in PENDING_SYNC_STATUSES
        or "sync_required" in broker_text
        or "pending_sync" in broker_text
    )


def _is_open_order(row: OrderLog) -> bool:
    status = _status(row)
    if status in LOCAL_TERMINAL_STATUSES:
        return False
    return status in LOCAL_OPEN_STATUSES or _needs_sync(row)


def _live_order_requiring_identifier(row: OrderLog) -> bool:
    return (
        _status(row) in LIVE_ID_STATUSES
        and _side(row) in {"buy", "sell"}
        and not _is_dry_run_order(row)
    )


def _is_dry_run_order(row: OrderLog) -> bool:
    if _status(row) == InternalOrderStatus.DRY_RUN_SIMULATED.value:
        return True
    text = " ".join(
        [
            str(row.request_payload or ""),
            str(row.response_payload or ""),
            str(row.client_order_id or ""),
        ]
    ).lower()
    return any(token in text for token in ("dry_run", "simulated", "preview_only"))


def _quantity(row: OrderLog) -> float | None:
    for value in (row.remaining_qty, row.requested_qty, row.qty, row.filled_qty):
        parsed = _float_or_none(value)
        if parsed is not None:
            return parsed
    return None


def _filled_quantity(row: OrderLog) -> float:
    for value in (row.filled_qty, row.qty, row.requested_qty):
        parsed = _float_or_none(value)
        if parsed is not None and parsed > 0:
            return parsed
    return 0.0


def _latest_order_time(row: OrderLog) -> datetime | None:
    return _max_dt([row.last_synced_at, row.submitted_at, row.created_at])


def _max_dt(values: list[Any]) -> datetime | None:
    latest: datetime | None = None
    for value in values:
        if value is None:
            continue
        try:
            current = _utc(value)
        except Exception:
            continue
        latest = current if latest is None else max(latest, current)
    return latest


def _age_minutes(now_utc: datetime, value: Any | None) -> float | None:
    if value is None:
        return None
    try:
        return max(0.0, (_utc(now_utc) - _utc(value)).total_seconds() / 60)
    except Exception:
        return None


def _local_order_keys(row: OrderLog) -> list[str]:
    return _dedupe(
        [
            _normalize_key(row.kis_odno),
            _normalize_key(row.broker_order_id),
            _normalize_key(row.client_order_id),
        ]
    )


def _broker_order_key(item: dict[str, Any]) -> str | None:
    for key in ("order_id", "broker_order_id", "kis_odno", "odno", "ODNO"):
        value = _normalize_key(item.get(key))
        if value:
            return value
    return None


def _normalize_key(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _symbol(item: dict[str, Any]) -> str | None:
    text = str(item.get("symbol") or item.get("pdno") or "").strip().upper()
    return text or None


def _broker_item_status(item: dict[str, Any]) -> str | None:
    text = str(item.get("status") or item.get("broker_status") or "").strip()
    return text or None


def _local_positions_from_orders(rows: list[OrderLog]) -> dict[str, float]:
    positions: dict[str, float] = {}
    for row in rows:
        if _is_dry_run_order(row):
            continue
        status = _status(row)
        if status not in {
            InternalOrderStatus.FILLED.value,
            InternalOrderStatus.PARTIALLY_FILLED.value,
        }:
            continue
        symbol = str(row.symbol or "").strip().upper()
        if not symbol:
            continue
        qty = _filled_quantity(row)
        if qty <= 0:
            continue
        if _side(row) == "sell":
            qty = -qty
        positions[symbol] = positions.get(symbol, 0.0) + qty
    return {symbol: qty for symbol, qty in positions.items() if qty > 1e-6}


def _order_context(row: OrderLog) -> dict[str, Any]:
    return {
        "order_id": row.id,
        "symbol": row.symbol,
        "side": row.side,
        "internal_status": row.internal_status,
        "broker_status": row.broker_status or row.broker_order_status,
        "broker_order_id_present": bool(row.broker_order_id),
        "kis_odno_present": bool(row.kis_odno),
        "last_synced_at": _iso(row.last_synced_at),
        "created_at": _iso(row.created_at),
        "updated_at": _iso(row.updated_at),
    }


def _broker_order_context(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "order_id_present": bool(_broker_order_key(item)),
        "symbol": _symbol(item),
        "side": item.get("side"),
        "status": _broker_item_status(item),
        "qty": _float_or_none(item.get("qty")),
        "unfilled_qty": _float_or_none(item.get("unfilled_qty")),
        "submitted_at": item.get("submitted_at"),
    }


def _as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text = str(value).strip().replace(",", "")
        if not text:
            return None
        return float(text)
    except Exception:
        return None


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _json_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 220:
        return f"{exc.__class__.__name__}: {text[:220]}..."
    return text


def _count_issue(issues: list[dict[str, Any]], issue_type: str) -> int:
    return len([item for item in issues if item.get("issue_type") == issue_type])


def _dedupe(values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _summary(health: str, issue_count: int, blocking_reasons: list[str]) -> str:
    if health == "healthy":
        return "Broker/local sync watchdog found no blocking issue."
    if health == "warning":
        return f"Broker/local sync watchdog found {issue_count} warning issue(s)."
    if health == "unsafe":
        reason = blocking_reasons[0] if blocking_reasons else "unsafe_sync_state"
        return f"Broker/local sync watchdog is unsafe due to {reason}."
    return "Broker/local sync watchdog health is unknown; automation must fail closed."


def _gating_notes(health: str, settings: dict[str, Any]) -> list[str]:
    notes = [
        "Watchdog performs read-only broker/local reconciliation.",
        "No live orders or broker order changes are allowed by this watchdog.",
    ]
    if health in {"unsafe", "unknown"} and bool(
        settings.get("broker_sync_watchdog_block_automation_on_unsafe", True)
    ):
        notes.append("Automation is blocked until broker/local state is reviewed.")
    return notes


def _next_safe_action(health: str, issues: list[dict[str, Any]]) -> str:
    if health == "healthy":
        return "continue_monitoring"
    first = issues[0] if issues else {}
    issue_type = str(first.get("issue_type") or "")
    if issue_type == "broker_read_failed":
        return "inspect_broker_app"
    if issue_type in {
        "pending_sync_order",
        "stale_local_order",
        "local_order_missing_broker_record",
    }:
        return "run_sync"
    if issue_type in {
        "missing_kis_odno",
        "missing_broker_order_id",
        "broker_order_missing_local_record",
        "ambiguous_order_state",
        "position_quantity_mismatch",
        "position_symbol_mismatch",
    }:
        return "manual_review"
    return "manual_review"
