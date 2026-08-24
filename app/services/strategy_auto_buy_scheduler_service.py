from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import TradeRunLog
from app.schemas.strategy_dry_run_auto_buy import ProfileAwareDryRunAutoBuyRequest
from app.schemas.strategy_auto_buy_scheduler import StrategyAutoBuySchedulerRunRequest
from app.services.kis_payload_sanitizer import sanitize_kis_payload
from app.services.market_session_service import MarketSessionService
from app.services.profile_aware_dry_run_auto_buy_service import (
    ProfileAwareDryRunAutoBuyService,
)
from app.services.profile_aware_dry_run_auto_buy_factory import (
    build_profile_aware_dry_run_auto_buy_service,
)
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_auto_buy_promotion_service import (
    StrategyAutoBuyPromotionService,
)
from app.services.strategy_profile_service import StrategyProfileService


MODE = "strategy_auto_buy_scheduler_dry_run"
TRIGGER_SOURCE = "strategy_auto_buy_dry_run"
PROVIDER = "kis"
MARKET = "KR"
KST = ZoneInfo("Asia/Seoul")
SCHEDULE_SLOTS = ["09:10", "11:30", "13:30"]


class StrategyAutoBuySchedulerService:
    """PR78 scheduler discovery flow: dry-run only, no validation or submit."""

    def __init__(
        self,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        strategy_profiles: StrategyProfileService | None = None,
        market_sessions: MarketSessionService | None = None,
        dry_run_service: ProfileAwareDryRunAutoBuyService | None = None,
        promotion_service: StrategyAutoBuyPromotionService | None = None,
    ) -> None:
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.strategy_profiles = strategy_profiles or StrategyProfileService()
        self.market_sessions = market_sessions or MarketSessionService()
        self.dry_run_service = dry_run_service
        self.promotion_service = promotion_service or StrategyAutoBuyPromotionService()

    def status(
        self,
        db: Session,
        *,
        provider: str = PROVIDER,
        market: str = MARKET,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _aware_utc(now)
        settings = self.runtime_settings.get_settings_read_only(db)
        profile = self._active_profile(db)
        latest = self._latest_run(db)
        metrics = self._run_metrics(db, now_utc=now_utc)
        current_scheduler_slot = self._current_profile_scheduler_slot(
            profile,
            now_utc=now_utc,
        )
        current_slot_key = self._scheduled_slot_key(
            profile,
            current_scheduler_slot,
            now_utc=now_utc,
        )
        market_session = self._market_session(now_utc)
        pending_promotions = self.promotion_service.summary(
            db,
            provider=provider,
            market=market,
            now=now_utc,
        ).get("pending_count", 0)
        slot_block_reason = self._scheduled_slot_block_reason(
            db,
            profile=profile,
            scheduler_slot=current_scheduler_slot,
            scheduled_slot_key=current_slot_key,
            now_utc=now_utc,
        )
        primary = slot_block_reason or self._primary_block_reason(
            settings=settings,
            profile=profile,
            market_session=market_session,
            completed_analysis_count=metrics["completed_analysis_count"],
            latest_run=self._latest_rate_run(
                db,
                scheduled=current_slot_key is not None,
            ),
            now_utc=now_utc,
            scheduled_slot_key=current_slot_key,
        )
        next_allowed = self._next_allowed_run_at(
            settings=settings,
            latest_run=self._latest_rate_run(
                db,
                scheduled=current_slot_key is not None,
            ),
            now_utc=now_utc,
        )
        return sanitize_kis_payload(
            {
                "provider": provider,
                "market": market,
                "enabled": bool(settings.get("strategy_auto_buy_scheduler_enabled") or settings.get("automation_profile_scheduler_enabled")),
                "dry_run_only": True,
                "promotion_queue_only": True,
                "allow_live_orders": False,
                "real_order_submit_allowed": False,
                **self._profile_context(db, profile),
                "allowed_profiles": _allowed_profiles(settings),
                **metrics,
                "scheduled_slot_key": current_slot_key,
                "max_runs_per_day": _int(
                    settings.get("strategy_auto_buy_scheduler_max_runs_per_day"),
                    3,
                ),
                "next_allowed_run_at": _iso(next_allowed),
                "min_minutes_between_runs": _int(
                    settings.get(
                        "strategy_auto_buy_scheduler_min_minutes_between_runs"
                    ),
                    60,
                ),
                "market_open": market_session.get("is_market_open"),
                "after_no_new_entry_time": self._after_no_new_entry_time(
                    settings=settings,
                    profile=profile,
                    now_utc=now_utc,
                ),
                "primary_block_reason": primary,
                "pending_promotion_count": int(pending_promotions or 0),
                "latest_scheduler_run": self._run_item(latest) if latest else None,
                "schedule_slots": list(((profile.get("automation_settings") or {}).get("entry") or {}).get("analysis_times") or SCHEDULE_SLOTS),
                "safety": _safety(read_only=True),
            }
        )

    def run_dry_run_once(
        self,
        db: Session,
        request: StrategyAutoBuySchedulerRunRequest | dict[str, Any] | None = None,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, StrategyAutoBuySchedulerRunRequest)
            else StrategyAutoBuySchedulerRunRequest.model_validate(request or {})
        )
        now_utc = _aware_utc(now)
        settings = self.runtime_settings.get_settings(db)
        profile = self._active_profile(db)
        metrics = self._run_metrics(db, now_utc=now_utc)
        market_session = self._market_session(now_utc)
        scheduled_slot_key = self._scheduled_slot_key(
            profile,
            payload.scheduler_slot,
            now_utc=now_utc,
        )
        latest_rate_run = self._latest_rate_run(
            db,
            scheduled=scheduled_slot_key is not None,
        )
        slot_block_reason = self._scheduled_slot_block_reason(
            db,
            profile=profile,
            scheduler_slot=payload.scheduler_slot,
            scheduled_slot_key=scheduled_slot_key,
            now_utc=now_utc,
        )
        block_reason = slot_block_reason or self._primary_block_reason(
            settings=settings,
            profile=profile,
            market_session=market_session,
            completed_analysis_count=metrics["completed_analysis_count"],
            latest_run=latest_rate_run,
            now_utc=now_utc,
            scheduled_slot_key=scheduled_slot_key,
        )
        profile_context = self._profile_context(db, profile)
        request_payload = {
            **payload.model_dump(mode="json"),
            **profile_context,
            "scheduled_slot_key": scheduled_slot_key,
            "scheduled_analysis": scheduled_slot_key is not None,
        }
        if block_reason is not None:
            response = self._blocked_response(
                block_reason=block_reason,
                request_payload=request_payload,
                profile_context=profile_context,
                scheduled_slot_key=scheduled_slot_key,
            )
            run = self._save_scheduler_run(
                db,
                request_payload=request_payload,
                response=response,
                result="blocked",
                reason=block_reason,
                symbol=payload.symbol or "WATCHLIST",
                now_utc=now_utc,
            )
            response["scheduler_run_id"] = run.id
            response.update(self._run_metrics(db, now_utc=now_utc))
            run.response_payload = _json(response)
            db.commit()
            return sanitize_kis_payload(response)

        dry_request = ProfileAwareDryRunAutoBuyRequest(
            provider=payload.provider,
            market=payload.market,
            profile_name=profile_context["legacy_profile_name"],
            automation_profile_key=profile_context["automation_profile_key"],
            automation_profile_name=profile_context["automation_profile_name"],
            symbol=payload.symbol,
            max_candidates=5,
            trigger_source=TRIGGER_SOURCE,
            use_watchlist=True,
            save_logs=True,
        )
        dry_run_service = self.dry_run_service or build_profile_aware_dry_run_auto_buy_service(db)
        dry_result = dry_run_service.run_once(db, dry_request)
        promotion = None
        created_promotion = False
        if (
            dry_result.get("action") == "would_buy"
            and settings.get("strategy_auto_buy_scheduler_create_promotion_on_would_buy")
        ):
            promotion = self.promotion_service.create_from_dry_run(
                db,
                dry_run_result=dry_result,
                request_payload={
                    **request_payload,
                    "scheduler_mode": MODE,
                    "trigger_source": TRIGGER_SOURCE,
                },
                ttl_minutes=_int(
                    settings.get("strategy_auto_buy_scheduler_promotion_ttl_minutes"),
                    45,
                ),
                now=now_utc,
            )
            created_promotion = True

        response = {
            "status": "ok",
            "action": str(dry_result.get("action") or "hold"),
            "provider": payload.provider,
            "market": payload.market,
            **profile_context,
            "scheduled_slot_key": scheduled_slot_key,
            "analysis_completed": True,
            "scheduled_analysis_counted": scheduled_slot_key is not None,
            **_scheduler_analysis_observability(dry_result),
            "dry_run_result": dry_result,
            "promotion": promotion,
            "created_promotion": created_promotion,
            "block_reason": None
            if dry_result.get("action") == "would_buy"
            else dry_result.get("reason"),
            "scheduler_run_id": None,
            "real_order_submitted": False,
            "validation_called": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "real_order_submit_allowed": False,
            "safety": _safety(read_only=False),
        }
        run = self._save_scheduler_run(
            db,
            request_payload=request_payload,
            response=response,
            result=str(dry_result.get("action") or "hold"),
            reason=str(dry_result.get("reason") or ""),
            symbol=str(dry_result.get("selected_symbol") or payload.symbol or "WATCHLIST"),
            now_utc=now_utc,
        )
        response["scheduler_run_id"] = run.id
        response.update(self._run_metrics(db, now_utc=now_utc))
        run.response_payload = _json(response)
        db.commit()
        return sanitize_kis_payload(response)

    def _primary_block_reason(
        self,
        *,
        settings: dict[str, Any],
        profile: dict[str, Any],
        market_session: dict[str, Any],
        completed_analysis_count: int,
        latest_run: TradeRunLog | None,
        now_utc: datetime,
        scheduled_slot_key: str | None = None,
    ) -> str | None:
        custom_profile = bool(profile.get("profile_key"))
        profile_status = str(profile.get("status") or "")
        if custom_profile:
            if not bool(settings.get("automation_profile_scheduler_enabled")):
                return "profile_scheduler_disabled"
            if profile_status == "scheduled":
                return "profile_not_started"
            if profile_status == "ended":
                return "profile_period_ended"
            if profile_status != "active":
                return "profile_status_not_active"
        elif not bool(settings.get("strategy_auto_buy_scheduler_enabled")):
            return "scheduler_disabled"
        if not bool(settings.get("strategy_auto_buy_scheduler_dry_run_only")):
            return "scheduler_dry_run_only_disabled"
        if bool(settings.get("strategy_auto_buy_scheduler_allow_live_orders")):
            return "scheduler_live_orders_forbidden"
        if (
            bool(settings.get("strategy_auto_buy_scheduler_block_when_kill_switch"))
            and bool(settings.get("kill_switch"))
        ):
            return "kill_switch_enabled"
        if (
            bool(settings.get("strategy_auto_buy_scheduler_block_when_market_closed"))
            and market_session.get("is_market_open") is False
        ):
            return "market_closed"
        if (
            bool(settings.get("strategy_auto_buy_scheduler_block_after_no_new_entry_time"))
            and self._after_no_new_entry_time(
                settings=settings, profile=profile, now_utc=now_utc
            )
        ):
            return "after_no_new_entry_time"
        profile_name = str(profile.get("profile_name") or "")
        if not custom_profile and profile_name == "aggressive" and not bool(
            settings.get("strategy_auto_buy_scheduler_allow_aggressive")
        ):
            return "aggressive_profile_blocked"
        if not custom_profile and profile_name not in _allowed_profiles(settings):
            return "active_profile_not_allowed"

        max_runs = _int(settings.get("strategy_auto_buy_scheduler_max_runs_per_day"), 3)
        if scheduled_slot_key is not None and completed_analysis_count >= max_runs:
            return "max_runs_per_day_reached"
        next_allowed = self._next_allowed_run_at(
            settings=settings,
            latest_run=latest_run,
            now_utc=now_utc,
        )
        if next_allowed is not None and next_allowed > now_utc:
            return "min_interval_not_elapsed"
        return None

    def _next_allowed_run_at(
        self,
        *,
        settings: dict[str, Any],
        latest_run: TradeRunLog | None,
        now_utc: datetime,
    ) -> datetime | None:
        if latest_run is None or latest_run.created_at is None:
            return None
        min_minutes = _int(
            settings.get("strategy_auto_buy_scheduler_min_minutes_between_runs"),
            60,
        )
        latest = _aware_utc(latest_run.created_at)
        next_allowed = latest + timedelta(minutes=max(0, min_minutes))
        return next_allowed if next_allowed > now_utc else None

    def _after_no_new_entry_time(
        self,
        *,
        settings: dict[str, Any],
        profile: dict[str, Any] | None = None,
        now_utc: datetime,
    ) -> bool:
        cutoff = _parse_hhmm(
            str(((profile or {}).get("automation_settings") or {}).get("entry", {}).get("no_new_entry_after") or settings.get("strategy_auto_buy_scheduler_no_new_entry_after") or "15:00")
        )
        local = now_utc.astimezone(KST)
        return local.time() >= cutoff

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            result = self.market_sessions.get_session_status(MARKET, now=now_utc)
            return dict(result) if isinstance(result, dict) else {}
        except Exception as exc:
            return {
                "market": MARKET,
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": exc.__class__.__name__,
            }

    def _active_profile(self, db: Session) -> dict[str, Any]:
        row = self.strategy_profiles.selected_profile(db)
        if row is None:
            row = self.strategy_profiles.active_profile(db)
        return self.strategy_profiles.serialize_profile(row)

    def _current_profile_scheduler_slot(
        self,
        profile: dict[str, Any],
        *,
        now_utc: datetime,
    ) -> str | None:
        if not profile.get("profile_key"):
            return None
        local_slot = _aware_utc(now_utc).astimezone(KST).strftime("%H:%M")
        configured = {
            str(value).strip()
            for value in (
                ((profile.get("automation_settings") or {}).get("entry") or {}).get(
                    "analysis_times"
                )
                or []
            )
            if str(value).strip()
        }
        return f"profile:{local_slot}" if local_slot in configured else None

    def _latest_rate_run(
        self,
        db: Session,
        *,
        scheduled: bool,
    ) -> TradeRunLog | None:
        rows = (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .limit(200)
            .all()
        )
        for row in rows:
            _, row_scheduled = _run_analysis_metadata(row)
            if row_scheduled is scheduled:
                return row
        return None

    def _profile_context(
        self,
        db: Session,
        profile: dict[str, Any],
    ) -> dict[str, Any]:
        automation_profile_key = profile.get("profile_key")
        legacy_profile_name = (
            self.strategy_profiles.legacy_active_profile(db).profile_name
            if automation_profile_key
            else profile.get("profile_name")
        )
        return {
            "active_profile": profile.get("profile_name"),
            "profile_key": automation_profile_key or profile.get("profile_name"),
            "profile_name": legacy_profile_name,
            "automation_profile_key": automation_profile_key,
            "automation_profile_name": (
                profile.get("display_name") if automation_profile_key else None
            ),
            "legacy_profile_name": legacy_profile_name,
        }

    def _scheduled_slot_key(
        self,
        profile: dict[str, Any],
        scheduler_slot: str | None,
        *,
        now_utc: datetime,
    ) -> str | None:
        raw_slot = str(scheduler_slot or "").strip()
        if not raw_slot:
            return None
        profile_identity = str(
            profile.get("profile_key") or profile.get("profile_name") or "unknown"
        )
        slot = _profile_slot_value(raw_slot)
        local_date = _aware_utc(now_utc).astimezone(KST).date().isoformat()
        return f"{profile_identity}:{local_date}:{slot}"

    def _scheduled_slot_block_reason(
        self,
        db: Session,
        *,
        profile: dict[str, Any],
        scheduler_slot: str | None,
        scheduled_slot_key: str | None,
        now_utc: datetime,
    ) -> str | None:
        if scheduled_slot_key is None:
            return None
        raw_slot = str(scheduler_slot or "").strip()
        if self._scheduled_slot_attempted(
            db,
            scheduler_slot=scheduler_slot,
            scheduled_slot_key=scheduled_slot_key,
            now_utc=now_utc,
        ):
            return "scheduled_slot_already_attempted"
        if raw_slot.lower().startswith("profile:"):
            slot = _profile_slot_value(raw_slot)
            configured = {
                str(value).strip()
                for value in (
                    ((profile.get("automation_settings") or {}).get("entry") or {}).get(
                        "analysis_times"
                    )
                    or SCHEDULE_SLOTS
                )
                if str(value).strip()
            }
            if slot not in configured:
                return "scheduled_slot_not_configured"
            local = _aware_utc(now_utc).astimezone(KST)
            if local.strftime("%H:%M") != slot:
                return "missed_slot_replay_forbidden"
        return None

    def _scheduled_slot_attempted(
        self,
        db: Session,
        *,
        scheduler_slot: str | None,
        scheduled_slot_key: str,
        now_utc: datetime,
    ) -> bool:
        raw_slot = str(scheduler_slot or "").strip()
        profile_identity = scheduled_slot_key.rsplit(":", 2)[0]
        for row in self._today_run_rows(db, now_utc=now_utc):
            request = _parse_object(row.request_payload)
            response = _parse_object(row.response_payload)
            if response.get("block_reason") in {
                "missed_slot_replay_forbidden",
                "scheduled_slot_not_configured",
            }:
                continue
            stored_key = str(
                response.get("scheduled_slot_key")
                or request.get("scheduled_slot_key")
                or ""
            ).strip()
            if stored_key == scheduled_slot_key:
                return True
            stored_slot = str(request.get("scheduler_slot") or "").strip()
            stored_profile = str(
                request.get("automation_profile_key")
                or request.get("profile_key")
                or ""
            ).strip()
            if (
                raw_slot
                and stored_slot == raw_slot
                and (not stored_profile or stored_profile == profile_identity)
            ):
                return True
        return False

    def _latest_run(self, db: Session) -> TradeRunLog | None:
        return (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
            .first()
        )

    def _runs_today(self, db: Session, *, now_utc: datetime) -> int:
        return len(self._today_run_rows(db, now_utc=now_utc))

    def _run_metrics(self, db: Session, *, now_utc: datetime) -> dict[str, int]:
        rows = self._today_run_rows(db, now_utc=now_utc)
        completed_scheduled = 0
        blocked_attempts = 0
        for row in rows:
            completed, scheduled = _run_analysis_metadata(row)
            if completed and scheduled:
                completed_scheduled += 1
            if not completed:
                blocked_attempts += 1
        return {
            "runs_today": len(rows),
            "completed_analysis_count": completed_scheduled,
            "blocked_attempt_count": blocked_attempts,
            "scheduled_analysis_count": completed_scheduled,
        }

    def _today_run_rows(
        self,
        db: Session,
        *,
        now_utc: datetime,
    ) -> list[TradeRunLog]:
        start_utc, end_utc = _kr_day_bounds_utc(now_utc)
        return (
            db.query(TradeRunLog)
            .filter(TradeRunLog.mode == MODE)
            .filter(TradeRunLog.created_at >= start_utc)
            .filter(TradeRunLog.created_at < end_utc)
            .order_by(TradeRunLog.created_at.asc(), TradeRunLog.id.asc())
            .all()
        )

    def _save_scheduler_run(
        self,
        db: Session,
        *,
        request_payload: dict[str, Any],
        response: dict[str, Any],
        result: str,
        reason: str,
        symbol: str,
        now_utc: datetime,
    ) -> TradeRunLog:
        row = TradeRunLog(
            run_key=f"strategy_auto_buy_scheduler_{uuid.uuid4().hex[:12]}",
            trigger_source=TRIGGER_SOURCE,
            symbol=symbol,
            mode=MODE,
            stage="done",
            result=result,
            reason=reason,
            request_payload=_json(
                {
                    **request_payload,
                    "mode": MODE,
                    "job_name": TRIGGER_SOURCE,
                    "real_order_submitted": False,
                    "validation_called": False,
                    "broker_submit_called": False,
                    "manual_submit_called": False,
                    "analysis_completed": response.get("analysis_completed") is True,
                    "scheduled_analysis_counted": response.get(
                        "scheduled_analysis_counted"
                    ) is True,
                    "scheduled_slot_key": response.get("scheduled_slot_key"),
                }
            ),
            response_payload=_json(response),
            created_at=_naive_utc(now_utc),
        )
        db.add(row)
        db.flush()
        return row

    def _blocked_response(
        self,
        *,
        block_reason: str,
        request_payload: dict[str, Any],
        profile_context: dict[str, Any],
        scheduled_slot_key: str | None,
    ) -> dict[str, Any]:
        return {
            "status": "blocked",
            "action": "blocked",
            "provider": request_payload.get("provider", PROVIDER),
            "market": request_payload.get("market", MARKET),
            **profile_context,
            "scheduled_slot_key": scheduled_slot_key,
            "analysis_completed": False,
            "scheduled_analysis_counted": False,
            "dry_run_result": None,
            "promotion": None,
            "created_promotion": False,
            "block_reason": block_reason,
            "scheduler_run_id": None,
            "real_order_submitted": False,
            "validation_called": False,
            "broker_submit_called": False,
            "manual_submit_called": False,
            "real_order_submit_allowed": False,
            "safety": _safety(read_only=False),
        }

    def _run_item(self, row: TradeRunLog) -> dict[str, Any]:
        payload = _parse_object(row.response_payload)
        return {
            "id": row.id,
            "run_key": row.run_key,
            "trigger_source": row.trigger_source,
            "mode": row.mode,
            "symbol": row.symbol,
            "result": row.result,
            "reason": row.reason,
            "created_at": _iso(row.created_at),
            "action": payload.get("action"),
            "block_reason": payload.get("block_reason"),
            "created_promotion": payload.get("created_promotion") is True,
        }


def _allowed_profiles(settings: dict[str, Any]) -> list[str]:
    value = settings.get("strategy_auto_buy_scheduler_allowed_profiles")
    if isinstance(value, list):
        profiles = [str(item).strip() for item in value if str(item).strip()]
    else:
        profiles = []
    return profiles or ["safe", "balanced"]


def _safety(*, read_only: bool) -> dict[str, Any]:
    return {
        "read_only": read_only,
        "dry_run_only": True,
        "promotion_queue_only": True,
        "allow_live_orders": False,
        "real_order_submit_allowed": False,
        "scheduler_real_orders_enabled": False,
        "real_order_submitted": False,
        "validation_called": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "dry_run_changed": False,
        "kill_switch_changed": False,
        "kis_real_order_changed": False,
        "live_order_action_created": False,
    }


def _json(value: Any) -> str:
    return json.dumps(sanitize_kis_payload(value), ensure_ascii=False, default=str)


def _parse_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if not value:
        return {}
    try:
        parsed = json.loads(str(value))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _profile_slot_value(value: str) -> str:
    text = str(value or "").strip()
    if text.lower().startswith("profile:"):
        return text.split(":", 1)[1].strip()
    return text


def _run_analysis_metadata(row: TradeRunLog) -> tuple[bool, bool]:
    request = _parse_object(row.request_payload)
    response = _parse_object(row.response_payload)
    completed_marker = response.get("analysis_completed")
    if completed_marker is None:
        completed_marker = request.get("analysis_completed")
    completed = (
        bool(completed_marker)
        if completed_marker is not None
        else response.get("dry_run_result") is not None
    )
    scheduled = bool(
        response.get("scheduled_slot_key")
        or request.get("scheduled_slot_key")
        or request.get("scheduler_slot")
    )
    return completed, scheduled


def _scheduler_analysis_observability(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "selected_symbol": result.get("selected_symbol"),
        "final_buy_score": result.get("final_buy_score")
        if result.get("final_buy_score") is not None
        else result.get("final_score"),
        "required_entry_score": float(result.get("required_entry_score") or 0),
        "reason": result.get("reason"),
        "configured_symbol_count": int(result.get("configured_symbol_count") or 0),
        "analyzed_symbol_count": int(result.get("analyzed_symbol_count") or 0),
        "quant_candidate_count": int(result.get("quant_candidate_count") or 0),
        "gpt_candidate_count": int(result.get("gpt_candidate_count") or 0),
        "final_candidate_count": int(result.get("final_candidate_count") or 0),
        "preview_status": str(result.get("preview_status") or "unknown"),
        "preview_error": result.get("preview_error"),
    }


def _parse_hhmm(value: str) -> time:
    try:
        hour, minute = [int(part) for part in str(value or "15:00").split(":", 1)]
        return time(hour=max(0, min(hour, 23)), minute=max(0, min(minute, 59)))
    except Exception:
        return time(15, 0)


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local = _aware_utc(now_utc).astimezone(KST)
    start_local = datetime.combine(local.date(), time.min, tzinfo=KST)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _int(value: Any, fallback: int) -> int:
    try:
        return int(value)
    except Exception:
        return fallback


def _aware_utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        value = value.astimezone(UTC)
    return value.replace(tzinfo=None)


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return _aware_utc(value).isoformat()

