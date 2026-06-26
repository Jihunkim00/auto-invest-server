from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.schemas.strategy_auto_buy_operations import (
    StrategyAutoBuyOperationsDryRunStatus,
    StrategyAutoBuyOperationsLiveAttemptsStatus,
    StrategyAutoBuyOperationsLiveReadinessStatus,
    StrategyAutoBuyOperationsPromotionsStatus,
    StrategyAutoBuyOperationsRiskStatus,
    StrategyAutoBuyOperationsSchedulerStatus,
    StrategyAutoBuyOperationsSafetyStatus,
    StrategyAutoBuyOperationsStatusResponse,
)
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.profile_aware_guarded_live_auto_buy_service import (
    ProfileAwareGuardedLiveAutoBuyService,
)
from app.services.strategy_auto_buy_promotion_service import (
    StrategyAutoBuyPromotionService,
)
from app.services.strategy_auto_buy_scheduler_service import (
    StrategyAutoBuySchedulerService,
)
from app.services.target_aware_risk_service import TargetAwareRiskService


KST = ZoneInfo("Asia/Seoul")
SYNC_REQUIRED_STATUSES = {"sync_required"}
SUBMITTED_STATUSES = {"submitted", "filled", "partially_filled", "sync_required"}
BLOCKED_STATUSES = {"blocked", "validation_failed", "failed", "rejected"}


class StrategyAutoBuyOperationsService:
    """Read-only operator snapshot for the profile-aware auto-buy workflow."""

    def __init__(
        self,
        *,
        dry_run_service: Any | None = None,
        live_auto_buy_service: Any | None = None,
        scheduler_service: Any | None = None,
        promotion_service: Any | None = None,
        target_risk_service: Any | None = None,
    ) -> None:
        self.dry_run_service = dry_run_service or ProfileAwareDryRunAutoBuyService()
        self.live_auto_buy_service = (
            live_auto_buy_service or ProfileAwareGuardedLiveAutoBuyService()
        )
        self.promotion_service = promotion_service or StrategyAutoBuyPromotionService()
        self.scheduler_service = scheduler_service or StrategyAutoBuySchedulerService(
            dry_run_service=self.dry_run_service,
            promotion_service=self.promotion_service,
        )
        self.target_risk_service = target_risk_service or TargetAwareRiskService()

    def status(
        self,
        db: Session,
        *,
        provider: str = "kis",
        market: str = "KR",
    ) -> dict[str, Any]:
        normalized_provider = str(provider or "kis").strip().lower() or "kis"
        normalized_market = str(market or "KR").strip().upper() or "KR"
        dry_recent = self._dry_recent(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        dry_summary = self._dry_summary(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        live_readiness = self._live_readiness(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        live_recent = self._live_recent(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        scheduler_raw = self._scheduler_status(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        promotions_raw = self._promotion_summary(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        risk_state = self._risk_state(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )

        dry_status = self._dry_run_status(dry_recent, dry_summary)
        scheduler_status = self._scheduler_summary_status(scheduler_raw)
        promotions_status = self._promotions_status(promotions_raw)
        readiness_status = self._live_readiness_status(live_readiness)
        attempts_status = self._live_attempts_status(live_recent)
        risk_status = self._risk_status(risk_state, readiness_status)
        stage = self._stage(
            dry_status=dry_status,
            scheduler_status=scheduler_status,
            promotions_status=promotions_status,
            readiness_status=readiness_status,
            attempts_status=attempts_status,
        )
        next_action = self._next_action(stage)
        dry_items = _dict_items(dry_recent.get("items"))
        active_profile = (
            _text(live_readiness.get("active_profile"))
            or _text(risk_state.get("active_profile"))
            or _text((dry_items[0] if dry_items else {}).get("active_profile"))
        )
        response = StrategyAutoBuyOperationsStatusResponse(
            provider=normalized_provider,
            market=normalized_market,
            active_profile=active_profile,
            auto_buy_stage=stage,
            next_operator_action=next_action,
            dry_run=dry_status,
            scheduler=scheduler_status,
            promotions=promotions_status,
            live_readiness=readiness_status,
            live_attempts=attempts_status,
            risk=risk_status,
            safety=StrategyAutoBuyOperationsSafetyStatus(),
        )
        return response.model_dump(mode="json")

    def _dry_recent(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            result = self.dry_run_service.recent(
                db,
                provider=provider,
                market=market,
                limit=100,
            )
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "provider": provider,
                "market": market,
                "count": 0,
                "items": [],
                "error": _safe_error(exc),
                "safety": _read_only_safety(),
            }

    def _dry_summary(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            result = self.dry_run_service.summary(
                db,
                provider=provider,
                market=market,
            )
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "provider": provider,
                "market": market,
                "today": {},
                "month": {},
                "profiles": {},
                "error": _safe_error(exc),
                "safety": _read_only_safety(),
            }

    def _live_readiness(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            result = self.live_auto_buy_service.readiness(
                db,
                provider=provider,
                market=market,
            )
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "enabled": False,
                "ready": False,
                "provider": provider,
                "market": market,
                "primary_block_reason": f"live_readiness_unavailable:{exc.__class__.__name__}",
                "recent_dry_run_required": True,
                "recent_dry_run_found": False,
                "dry_run": True,
                "kill_switch": False,
                "kis_real_order_enabled": False,
                "orders_remaining_today": 0,
                "checks": [],
                "safety": _read_only_safety(),
            }

    def _live_recent(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            result = self.live_auto_buy_service.recent(
                db,
                provider=provider,
                market=market,
                limit=100,
            )
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "provider": provider,
                "market": market,
                "count": 0,
                "items": [],
                "error": _safe_error(exc),
                "safety": _read_only_safety(),
            }

    def _scheduler_status(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            result = self.scheduler_service.status(
                db,
                provider=provider,
                market=market,
            )
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "enabled": False,
                "dry_run_only": True,
                "allow_live_orders": False,
                "runs_today": 0,
                "max_runs_per_day": 0,
                "latest_scheduler_run": None,
                "next_allowed_run_at": None,
                "primary_block_reason": f"scheduler_status_unavailable:{exc.__class__.__name__}",
                "safety": _read_only_safety(),
            }

    def _promotion_summary(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            result = self.promotion_service.summary(
                db,
                provider=provider,
                market=market,
            )
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "pending_count": 0,
                "latest_symbol": None,
                "latest_status": f"promotion_summary_unavailable:{exc.__class__.__name__}",
                "latest_expires_at": None,
                "acknowledged_count_today": 0,
                "dismissed_count_today": 0,
                "safety": _read_only_safety(),
            }

    def _risk_state(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> dict[str, Any]:
        try:
            result = self.target_risk_service.risk_state(
                db,
                provider=provider,
                market=market,
            )
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "new_entries_allowed": False,
                "primary_block_reason": f"risk_state_unavailable:{exc.__class__.__name__}",
                "safety": _read_only_safety(),
            }

    def _dry_run_status(
        self,
        recent: dict[str, Any],
        summary: dict[str, Any],
    ) -> StrategyAutoBuyOperationsDryRunStatus:
        items = _dict_items(recent.get("items"))
        latest = items[0] if items else {}
        today_items = [item for item in items if _is_today(item.get("created_at"))]
        return StrategyAutoBuyOperationsDryRunStatus(
            recent_found=bool(items),
            latest_action=_text(latest.get("action")),
            latest_symbol=_text(latest.get("selected_symbol") or latest.get("symbol")),
            latest_score=_first_float(
                latest.get("final_score"),
                latest.get("buy_score"),
                latest.get("score"),
            ),
            latest_time=_text(latest.get("created_at")),
            would_buy_count_today=sum(
                1 for item in today_items if _text(item.get("action")) == "would_buy"
            ),
            blocked_count_today=sum(
                1
                for item in today_items
                if _text(item.get("action")) in {"blocked", "hold", "skip", "skipped"}
            ),
            summary=dict(summary.get("today") or {}),
        )

    def _scheduler_summary_status(
        self,
        payload: dict[str, Any],
    ) -> StrategyAutoBuyOperationsSchedulerStatus:
        latest = (
            payload.get("latest_scheduler_run")
            if isinstance(payload.get("latest_scheduler_run"), dict)
            else {}
        )
        return StrategyAutoBuyOperationsSchedulerStatus(
            enabled=payload.get("enabled") is True,
            dry_run_only=payload.get("dry_run_only") is not False,
            allow_live_orders=False,
            runs_today=_int(payload.get("runs_today")),
            max_runs_per_day=_int(payload.get("max_runs_per_day")),
            latest_run_status=_text(latest.get("result") or latest.get("action")),
            next_allowed_run_at=_text(payload.get("next_allowed_run_at")),
        )

    def _promotions_status(
        self,
        payload: dict[str, Any],
    ) -> StrategyAutoBuyOperationsPromotionsStatus:
        return StrategyAutoBuyOperationsPromotionsStatus(
            pending_count=_int(payload.get("pending_count")),
            latest_symbol=_text(payload.get("latest_symbol")),
            latest_status=_text(payload.get("latest_status")),
            latest_expires_at=_text(payload.get("latest_expires_at")),
            acknowledged_count_today=_int(payload.get("acknowledged_count_today")),
            dismissed_count_today=_int(payload.get("dismissed_count_today")),
        )

    def _live_readiness_status(
        self,
        readiness: dict[str, Any],
    ) -> StrategyAutoBuyOperationsLiveReadinessStatus:
        ready = readiness.get("ready") is True
        target_risk_ready = _check_ok(readiness, "target_aware_risk")
        if target_risk_ready is None:
            target_risk_ready = ready
        dry_status = "would_buy" if readiness.get("recent_dry_run_found") else "missing"
        if readiness.get("primary_block_reason") in {
            "recent_dry_run_expired",
            "source_dry_run_not_would_buy",
            "symbol_mismatch_recent_dry_run",
        }:
            dry_status = str(readiness["primary_block_reason"])
        return StrategyAutoBuyOperationsLiveReadinessStatus(
            ready=ready,
            enabled=readiness.get("enabled") is True,
            primary_block_reason=_text(readiness.get("primary_block_reason")),
            recent_dry_run_required=readiness.get("recent_dry_run_required") is True,
            recent_dry_run_found=readiness.get("recent_dry_run_found") is True,
            dry_run_status=dry_status,
            kill_switch=readiness.get("kill_switch") is True,
            kis_real_order_enabled=readiness.get("kis_real_order_enabled") is True,
            target_risk_ready=bool(target_risk_ready),
            orders_remaining_today=max(0, _int(readiness.get("orders_remaining_today"))),
        )

    def _live_attempts_status(
        self,
        recent: dict[str, Any],
    ) -> StrategyAutoBuyOperationsLiveAttemptsStatus:
        items = _dict_items(recent.get("items"))
        today_items = [
            item
            for item in items
            if _is_today(item.get("submitted_at") or item.get("created_at"))
        ]
        latest = items[0] if items else {}
        return StrategyAutoBuyOperationsLiveAttemptsStatus(
            latest_status=_text(latest.get("status")),
            submitted_count_today=sum(
                1
                for item in today_items
                if _text(item.get("status")) in SUBMITTED_STATUSES
                or item.get("submitted") is True
            ),
            blocked_count_today=sum(
                1
                for item in today_items
                if _text(item.get("status")) in BLOCKED_STATUSES
                or _text(item.get("action")) == "blocked"
            ),
            sync_required_count=sum(
                1
                for item in today_items
                if _text(item.get("status")) in SYNC_REQUIRED_STATUSES
                or _text(item.get("action")) == "sync_required"
            ),
            recent=items[:5],
        )

    def _risk_status(
        self,
        risk_state: dict[str, Any],
        readiness: StrategyAutoBuyOperationsLiveReadinessStatus,
    ) -> StrategyAutoBuyOperationsRiskStatus:
        return StrategyAutoBuyOperationsRiskStatus(
            entry_allowed=risk_state.get("new_entries_allowed") is True
            and readiness.target_risk_ready,
            size_multiplier=_first_float(
                risk_state.get("sizing_multiplier"),
                risk_state.get("recommended_order_notional_pct"),
            ),
            target_progress_pct=_first_float(risk_state.get("target_progress_pct")),
            daily_loss_limit_hit=risk_state.get("daily_loss_limit_hit") is True,
            monthly_loss_limit_hit=risk_state.get("monthly_loss_limit_hit") is True,
        )

    def _stage(
        self,
        *,
        dry_status: StrategyAutoBuyOperationsDryRunStatus,
        scheduler_status: StrategyAutoBuyOperationsSchedulerStatus,
        promotions_status: StrategyAutoBuyOperationsPromotionsStatus,
        readiness_status: StrategyAutoBuyOperationsLiveReadinessStatus,
        attempts_status: StrategyAutoBuyOperationsLiveAttemptsStatus,
    ) -> str:
        if attempts_status.sync_required_count > 0:
            return "sync_required"
        if attempts_status.submitted_count_today > 0:
            return "submitted_today"
        if promotions_status.pending_count > 0:
            return "promotion_pending"
        if promotions_status.latest_status == "expired":
            return "promotion_expired"
        if dry_status.recent_found:
            if dry_status.latest_action != "would_buy":
                return "dry_run_blocked"
            if not readiness_status.enabled:
                return "dry_run_would_buy"
            if not readiness_status.ready:
                return "live_readiness_blocked"
            return "ready_for_operator_confirm"
        if not scheduler_status.enabled:
            return "scheduler_disabled"
        if scheduler_status.latest_run_status == "blocked":
            return "scheduled_dry_run_blocked"
        return "scheduled_dry_run_waiting"

    def _next_action(self, stage: str) -> str:
        return {
            "scheduler_disabled": "enable_dry_run_scheduler_if_desired",
            "scheduled_dry_run_waiting": "wait_for_scheduled_dry_run",
            "scheduled_dry_run_blocked": "wait_for_scheduled_dry_run",
            "promotion_pending": "review_promotion",
            "promotion_expired": "acknowledge_or_dismiss_promotion",
            "no_dry_run": "run_dry_run",
            "dry_run_blocked": "review_block_reason",
            "dry_run_would_buy": "enable_prerequisites_manually",
            "live_readiness_blocked": "enable_prerequisites_manually",
            "ready_for_operator_confirm": "confirm_guarded_live_buy",
            "submitted_today": "wait",
            "sync_required": "sync_latest_attempt",
            "disabled": "no_action",
        }.get(stage, "no_action")


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _check_ok(payload: dict[str, Any], key: str) -> bool | None:
    checks = payload.get("checks")
    if not isinstance(checks, list):
        return None
    for item in checks:
        if isinstance(item, dict) and item.get("key") == key:
            return item.get("ok") is True
    return None


def _is_today(value: Any) -> bool:
    parsed = _parse_datetime(value)
    if parsed is None:
        return False
    return parsed.astimezone(KST).date() == datetime.now(KST).date()


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _first_float(*values: Any) -> float | None:
    for value in values:
        try:
            if value is None:
                continue
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _safe_error(exc: Exception) -> str:
    text = str(exc).strip() or exc.__class__.__name__
    if len(text) > 200:
        text = f"{text[:200]}..."
    return text


def _read_only_safety() -> dict[str, Any]:
    return {
        "read_only": True,
        "validation_called": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
    }
