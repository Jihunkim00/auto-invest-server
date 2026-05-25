from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.core.enums import InternalOrderStatus
from app.db.models import OrderLog, RuntimeSetting, TradeRunLog
from app.services.kis_limited_auto_buy_execution_review_service import (
    KisLimitedAutoBuyExecutionReviewService,
)
from app.services.kis_limited_auto_buy_service import KisLimitedAutoBuyService
from app.services.kis_limited_auto_sell_service import KisLimitedAutoSellService
from app.services.kis_scheduler_guarded_sell_review_service import (
    KisSchedulerGuardedSellReviewService,
)
from app.services.kis_scheduler_readiness_service import KisSchedulerReadinessService
from app.services.market_session_service import MarketSessionService
from app.services.runtime_setting_service import RuntimeSettingService


MODE = "ops_production_readiness"
PROVIDER = "kis"
MARKET = "KR"
KR_TZ = ZoneInfo("Asia/Seoul")

OPEN_INTERNAL_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}

FAILED_INTERNAL_STATUSES = {
    InternalOrderStatus.FAILED.value,
    InternalOrderStatus.REJECTED.value,
    InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
    InternalOrderStatus.UNKNOWN_STALE.value,
    InternalOrderStatus.SYNC_FAILED.value,
}

LIVE_INTERNAL_STATUSES = {
    InternalOrderStatus.REQUESTED.value,
    InternalOrderStatus.SUBMITTED.value,
    InternalOrderStatus.ACCEPTED.value,
    InternalOrderStatus.PENDING.value,
    InternalOrderStatus.PARTIALLY_FILLED.value,
    InternalOrderStatus.FILLED.value,
}

REQUIRED_ENV_EXAMPLE_KEYS = {
    "DEFAULT_SYMBOL",
    "DEFAULT_US_SYMBOL",
    "DEFAULT_KR_SYMBOL",
    "DRY_RUN",
    "KILL_SWITCH",
    "KIS_ENABLED",
    "KIS_REAL_ORDER_ENABLED",
    "KIS_LIVE_AUTO_SELL_ENABLED",
    "KIS_LIVE_AUTO_BUY_ENABLED",
    "KIS_SCHEDULER_ALLOW_REAL_ORDERS",
    "KIS_SCHEDULER_SELL_ENABLED",
    "KIS_SCHEDULER_BUY_ENABLED",
}


class OpsProductionReadinessService:
    """Read-only production and operator safety readiness report."""

    def __init__(
        self,
        client: KisClient,
        *,
        runtime_settings: RuntimeSettingService | None = None,
        session_service: MarketSessionService | None = None,
        repo_root: Path | None = None,
        limited_auto_buy_service: Any | None = None,
        limited_auto_sell_service: Any | None = None,
        scheduler_readiness_service: Any | None = None,
        scheduler_sell_review_service: Any | None = None,
        limited_buy_review_service: Any | None = None,
    ):
        self.client = client
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.session_service = session_service or MarketSessionService()
        self.repo_root = repo_root or Path(__file__).resolve().parents[2]
        self._limited_auto_buy_service = limited_auto_buy_service
        self._limited_auto_sell_service = limited_auto_sell_service
        self._scheduler_readiness_service = scheduler_readiness_service
        self._scheduler_sell_review_service = scheduler_sell_review_service
        self._limited_buy_review_service = limited_buy_review_service

    def readiness(
        self,
        db: Session,
        *,
        include_raw: bool = False,
        days: int = 7,
        include_recent: bool = True,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_utc = _utc_now(now)
        safe_days = min(max(int(days or 7), 1), 365)
        start_utc, end_utc = _kr_day_bounds_utc(now_utc)
        cutoff_utc = _naive_utc(now_utc - timedelta(days=safe_days))

        runtime, runtime_source = self._runtime_snapshot(db)
        app_settings = get_settings()
        docs = self._documentation_status()
        db_check = _db_writable_check(db)
        watchlist = self._watchlist_baseline()
        market_session = self._market_session(now_utc)
        account_state = self._account_state()

        limited_buy_status = self._safe_module(
            "limited_auto_buy_status",
            lambda: self._limited_auto_buy().status(db),
        )
        limited_sell_status = self._safe_module(
            "limited_auto_sell_status",
            lambda: self._limited_auto_sell().status(db),
        )
        scheduler_readiness = self._safe_module(
            "scheduler_readiness",
            lambda: self._scheduler_readiness().readiness(
                db,
                include_modules=True,
                include_recent_runs=True,
                include_raw=False,
            ),
        )
        guarded_sell_review = self._safe_module(
            "scheduler_guarded_sell_review",
            lambda: self._scheduler_sell_review().review(
                db,
                limit=20,
                days=safe_days,
                include_raw=False,
            ),
        )
        limited_buy_review = self._safe_module(
            "limited_auto_buy_execution_review",
            lambda: self._limited_buy_review().review(
                db,
                limit=20,
                days=safe_days,
                include_raw=False,
            ),
        )

        today = _today_summary(
            db,
            runtime=runtime,
            start_utc=start_utc,
            end_utc=end_utc,
            now_utc=now_utc,
        )
        recent_activity = (
            _recent_activity(db, cutoff_utc=cutoff_utc, limit=30)
            if include_recent
            else []
        )
        risk = _risk_summary(
            db,
            runtime=runtime,
            today=today,
            start_utc=start_utc,
            end_utc=end_utc,
            now_utc=now_utc,
        )
        safety_violation_count = _safety_violation_count(
            guarded_sell_review=guarded_sell_review,
            limited_buy_review=limited_buy_review,
        )
        risk["safety_violation_count"] = safety_violation_count
        scheduler = _scheduler_section(
            runtime=runtime,
            settings=self.client.settings,
            scheduler_readiness=scheduler_readiness,
            recent_activity=recent_activity,
        )
        kis = _kis_section(
            settings=self.client.settings,
            account_state=account_state,
            market_session=market_session,
            runtime=runtime,
        )
        runtime_section = _runtime_section(runtime, app_settings, self.client.settings)

        blocking_issues = _blocking_issues(
            runtime=runtime,
            kis=kis,
            scheduler=scheduler,
            risk=risk,
            docs=docs,
            db_check=db_check,
            watchlist=watchlist,
            safety_violation_count=safety_violation_count,
        )
        warnings = _warnings(
            runtime=runtime,
            today=today,
            risk=risk,
            docs=docs,
            scheduler=scheduler,
            recent_activity=recent_activity,
        )
        safety_checks = _safety_checks(
            runtime=runtime,
            kis=kis,
            scheduler=scheduler,
            risk=risk,
            today=today,
            docs=docs,
            db_check=db_check,
            watchlist=watchlist,
            safety_violation_count=safety_violation_count,
        )
        recommended_actions = _recommended_actions(
            runtime=runtime,
            blocking_issues=blocking_issues,
            warnings=warnings,
            recent_activity=recent_activity,
        )

        live_trading_ready = _live_trading_ready(
            runtime=runtime,
            kis=kis,
            scheduler=scheduler,
            db_check=db_check,
            watchlist=watchlist,
            docs=docs,
            safety_violation_count=safety_violation_count,
        )
        hard_blocked = _hard_blocked(
            runtime=runtime,
            db_check=db_check,
            watchlist=watchlist,
            risk=risk,
            safety_violation_count=safety_violation_count,
        )
        paper_or_dry_run_ready = bool(
            runtime.get("dry_run", True)
            and not runtime.get("kill_switch", False)
            and db_check["writable"]
            and watchlist["valid"]
        )
        production_ready = bool(live_trading_ready)
        overall_status = _overall_status(
            runtime=runtime,
            live_trading_ready=live_trading_ready,
            hard_blocked=hard_blocked,
        )
        latest_activity_at = _latest_activity_at(recent_activity)
        latest_block_reason = (
            today["top_block_reasons"][0]["reason"]
            if today.get("top_block_reasons")
            else None
        )
        summary = {
            "overall_status": overall_status,
            "production_ready": production_ready,
            "live_trading_ready": live_trading_ready,
            "paper_or_dry_run_ready": paper_or_dry_run_ready,
            "dry_run": bool(runtime.get("dry_run", True)),
            "kill_switch": bool(runtime.get("kill_switch", False)),
            "kis_enabled": bool(getattr(self.client.settings, "kis_enabled", False)),
            "kis_real_order_enabled": bool(
                getattr(self.client.settings, "kis_real_order_enabled", False)
            ),
            "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
            "kis_scheduler_enabled": bool(runtime.get("kis_scheduler_enabled", False)),
            "kis_scheduler_allow_real_orders": bool(
                runtime.get("kis_scheduler_allow_real_orders", False)
            ),
            "kis_scheduler_sell_enabled": bool(
                runtime.get("kis_scheduler_sell_enabled", False)
            ),
            "kis_scheduler_buy_enabled": bool(
                runtime.get("kis_scheduler_buy_enabled", False)
            ),
            "kis_live_auto_sell_enabled": bool(
                runtime.get("kis_live_auto_sell_enabled", False)
            ),
            "kis_live_auto_buy_enabled": bool(
                runtime.get("kis_live_auto_buy_enabled", False)
            ),
            "kis_limited_auto_sell_enabled": bool(
                runtime.get("kis_limited_auto_sell_enabled", False)
            ),
            "kis_limited_auto_buy_enabled": bool(
                runtime.get("kis_limited_auto_buy_enabled", False)
            ),
            "latest_activity_at": latest_activity_at,
            "latest_block_reason": latest_block_reason,
            "critical_issue_count": _critical_issue_count(safety_checks),
            "warning_count": sum(1 for item in safety_checks if item["status"] == "WARN")
            + len(warnings),
        }

        diagnostics: dict[str, Any] = {
            "checked_at": now_utc.isoformat(),
            "days": safe_days,
            "include_recent": bool(include_recent),
            "runtime_source": runtime_source,
            "module_status": {
                "limited_auto_buy_status": _module_summary(limited_buy_status),
                "limited_auto_sell_status": _module_summary(limited_sell_status),
                "scheduler_readiness": _module_summary(scheduler_readiness),
                "scheduler_guarded_sell_review": _module_summary(
                    guarded_sell_review
                ),
                "limited_auto_buy_execution_review": _module_summary(
                    limited_buy_review
                ),
            },
            "review_safety_violations": {
                "scheduler_guarded_sell": len(
                    _list_value(guarded_sell_review.get("safety_violations"))
                ),
                "limited_auto_buy": len(
                    _list_value(limited_buy_review.get("safety_violations"))
                ),
            },
            "read_only": True,
        }
        if include_raw:
            diagnostics["raw"] = {
                "limited_auto_buy_status": limited_buy_status,
                "limited_auto_sell_status": limited_sell_status,
                "scheduler_readiness": scheduler_readiness,
                "scheduler_guarded_sell_review": guarded_sell_review,
                "limited_auto_buy_execution_review": limited_buy_review,
            }

        return {
            "mode": MODE,
            "readiness_only": True,
            "production_ready": production_ready,
            "live_trading_ready": live_trading_ready,
            "paper_or_dry_run_ready": paper_or_dry_run_ready,
            "summary": summary,
            "runtime": runtime_section,
            "kis": kis,
            "scheduler": scheduler,
            "risk": risk,
            "today": today,
            "recent_activity": recent_activity,
            "safety_checks": safety_checks,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "recommended_actions": recommended_actions,
            "documentation": docs,
            "diagnostics": diagnostics,
        }

    def _runtime_snapshot(self, db: Session) -> tuple[dict[str, Any], str]:
        defaults = dict(self.runtime_settings._defaults())
        row = db.query(RuntimeSetting).first()
        runtime = dict(defaults)
        source = "defaults_no_runtime_row"
        if row is not None:
            source = "runtime_row"
            for key, default in defaults.items():
                value = getattr(row, key, None)
                if value is not None:
                    runtime[key] = _coerce_like(value, default)
            runtime["updated_at"] = row.updated_at
        runtime["trade_limits"] = self.runtime_settings._trade_limits(runtime)
        runtime["kis_limited_auto_stop_loss_enabled"] = bool(
            runtime.get("kis_limited_auto_sell_stop_loss_enabled", False)
        )
        runtime["kis_limited_auto_take_profit_enabled"] = bool(
            runtime.get("kis_limited_auto_sell_take_profit_enabled", False)
        )
        runtime["kis_scheduler_enabled"] = bool(
            getattr(self.client.settings, "kis_scheduler_enabled", False)
            or getattr(self.client.settings, "kr_scheduler_enabled", False)
        )
        runtime["kis_scheduler_dry_run"] = bool(
            getattr(self.client.settings, "kis_scheduler_dry_run", True)
        )
        runtime["kis_scheduler_configured_allow_real_orders"] = bool(
            getattr(self.client.settings, "kis_scheduler_allow_real_orders", False)
            or getattr(self.client.settings, "kr_scheduler_allow_real_orders", False)
        )
        return runtime, source

    def _limited_auto_buy(self) -> Any:
        return self._limited_auto_buy_service or KisLimitedAutoBuyService(self.client)

    def _limited_auto_sell(self) -> Any:
        return self._limited_auto_sell_service or KisLimitedAutoSellService(self.client)

    def _scheduler_readiness(self) -> Any:
        return self._scheduler_readiness_service or KisSchedulerReadinessService(
            self.client
        )

    def _scheduler_sell_review(self) -> Any:
        return self._scheduler_sell_review_service or KisSchedulerGuardedSellReviewService()

    def _limited_buy_review(self) -> Any:
        return self._limited_buy_review_service or KisLimitedAutoBuyExecutionReviewService()

    def _safe_module(self, module: str, fn: Any) -> dict[str, Any]:
        try:
            payload = fn()
            return payload if isinstance(payload, dict) else {"value": payload}
        except Exception as exc:
            return {
                "available": False,
                "module": module,
                "error": _safe_error(exc),
                "block_reasons": [f"{module}_unavailable"],
            }

    def _market_session(self, now_utc: datetime) -> dict[str, Any]:
        try:
            return self.session_service.get_session_status(MARKET, now=now_utc)
        except Exception as exc:
            return {
                "market": MARKET,
                "timezone": "Asia/Seoul",
                "is_market_open": False,
                "is_entry_allowed_now": False,
                "error": _safe_error(exc),
            }

    def _account_state(self) -> dict[str, Any]:
        state: dict[str, Any] = {
            "balance": None,
            "positions": [],
            "open_orders": [],
            "errors": [],
        }
        try:
            state["balance"] = self.client.get_account_balance()
        except Exception as exc:
            state["errors"].append({"key": "balance", "error": _safe_error(exc)})
        try:
            positions = self.client.list_positions()
            state["positions"] = positions if isinstance(positions, list) else []
        except Exception as exc:
            state["errors"].append({"key": "positions", "error": _safe_error(exc)})
        try:
            open_orders = self.client.list_open_orders()
            state["open_orders"] = open_orders if isinstance(open_orders, list) else []
        except Exception as exc:
            state["errors"].append({"key": "open_orders", "error": _safe_error(exc)})
        return state

    def _watchlist_baseline(self) -> dict[str, Any]:
        path = self.repo_root / "config" / "watchlist_kr.yaml"
        symbols: list[str] = []
        error = None
        if not path.exists():
            error = "watchlist_kr_yaml_missing"
        else:
            try:
                payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                raw_symbols = payload.get("symbols") if isinstance(payload, dict) else []
                if isinstance(raw_symbols, list):
                    for item in raw_symbols:
                        if isinstance(item, dict):
                            symbol = _normalize_symbol(item.get("symbol"))
                        else:
                            symbol = _normalize_symbol(item)
                        if symbol:
                            symbols.append(symbol)
            except Exception as exc:
                error = _safe_error(exc)
        unique_symbols = sorted(set(symbols))
        required_present = {
            "005930": "005930" in unique_symbols,
            "035420": "035420" in unique_symbols,
        }
        valid = (
            error is None
            and len(unique_symbols) == 50
            and all(required_present.values())
        )
        return {
            "path": str(path.relative_to(self.repo_root)),
            "exists": path.exists(),
            "symbol_count": len(unique_symbols),
            "required_symbols": required_present,
            "valid": valid,
            "error": error,
        }

    def _documentation_status(self) -> dict[str, Any]:
        files = {
            "README.md": self.repo_root / "README.md",
            "docs/OPERATIONS.md": self.repo_root / "docs" / "OPERATIONS.md",
            "docs/PRODUCTION_CHECKLIST.md": self.repo_root
            / "docs"
            / "PRODUCTION_CHECKLIST.md",
            ".env.example": self.repo_root / ".env.example",
        }
        file_status = {
            name: {"present": path.exists(), "path": name}
            for name, path in files.items()
        }
        env_keys = _env_example_keys(files[".env.example"])
        missing_env_keys = sorted(REQUIRED_ENV_EXAMPLE_KEYS - env_keys)
        docs_present = all(
            file_status[name]["present"]
            for name in (
                "README.md",
                "docs/OPERATIONS.md",
                "docs/PRODUCTION_CHECKLIST.md",
            )
        )
        env_example_present = file_status[".env.example"]["present"]
        return {
            "docs_present": docs_present,
            "env_example_present": env_example_present,
            "required_env_vars_documented": not missing_env_keys,
            "files": file_status,
            "required_env_vars": sorted(REQUIRED_ENV_EXAMPLE_KEYS),
            "missing_env_vars": missing_env_keys,
        }


def _runtime_section(
    runtime: dict[str, Any],
    app_settings: Any,
    kis_settings: Any,
) -> dict[str, Any]:
    live_keys = {
        key: bool(runtime.get(key, False))
        for key in (
            "kis_live_auto_enabled",
            "kis_live_auto_buy_enabled",
            "kis_live_auto_sell_enabled",
            "kis_limited_auto_sell_enabled",
            "kis_limited_auto_sell_stop_loss_enabled",
            "kis_limited_auto_sell_take_profit_enabled",
            "kis_limited_auto_buy_enabled",
            "kis_limited_auto_buy_readiness_enabled",
            "kis_scheduler_live_enabled",
            "kis_scheduler_allow_real_orders",
            "kis_scheduler_buy_enabled",
            "kis_scheduler_sell_enabled",
            "kis_scheduler_allow_limited_auto_buy",
            "kis_scheduler_allow_limited_auto_sell",
        )
    }
    scheduler_keys = {
        key: runtime.get(key)
        for key in (
            "scheduler_enabled",
            "kis_scheduler_enabled",
            "kis_scheduler_dry_run",
            "kis_scheduler_configured_allow_real_orders",
            "kis_scheduler_max_live_orders_per_day",
            "kis_scheduler_live_requires_dry_run_false",
            "kis_scheduler_live_respect_kill_switch",
        )
    }
    limited_keys = {
        key: runtime.get(key)
        for key in (
            "kis_limited_auto_sell_max_orders_per_day",
            "kis_limited_auto_sell_max_notional_pct",
            "kis_limited_auto_buy_max_orders_per_day",
            "kis_limited_auto_buy_max_notional_pct",
            "kis_limited_auto_buy_min_cash_buffer_krw",
            "kis_limited_auto_buy_min_final_score",
            "kis_limited_auto_buy_min_confidence",
            "kis_limited_auto_buy_max_positions",
            "kis_limited_auto_buy_no_new_entry_after",
        )
    }
    return {
        "dry_run": bool(runtime.get("dry_run", True)),
        "kill_switch": bool(runtime.get("kill_switch", False)),
        "bot_enabled": bool(runtime.get("bot_enabled", True)),
        "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
        "kis_enabled": bool(getattr(kis_settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(kis_settings, "kis_real_order_enabled", False)
        ),
        "alpaca_paper_enabled": "paper" in str(
            getattr(app_settings, "alpaca_base_url", "")
        ).lower(),
        "default_gate_level": runtime.get("default_gate_level"),
        "default_symbol": runtime.get("default_symbol"),
        "default_us_symbol": getattr(app_settings, "default_us_symbol", "AAPL"),
        "default_kr_symbol": getattr(app_settings, "default_kr_symbol", "005930"),
        "live_settings": live_keys,
        "scheduler_settings": scheduler_keys,
        "limited_auto_settings": limited_keys,
        "trade_limits": runtime.get("trade_limits", {}),
    }


def _kis_section(
    *,
    settings: Any,
    account_state: dict[str, Any],
    market_session: dict[str, Any],
    runtime: dict[str, Any],
) -> dict[str, Any]:
    balance = _dict_value(account_state.get("balance"))
    positions = _list_value(account_state.get("positions"))
    open_orders = _list_value(account_state.get("open_orders"))
    config_present = {
        "app_key": bool(getattr(settings, "kis_app_key", None)),
        "app_secret": bool(getattr(settings, "kis_app_secret", None)),
        "account_no": bool(getattr(settings, "kis_account_no", None)),
        "account_product_code": bool(
            getattr(settings, "kis_account_product_code", None)
        ),
        "base_url": bool(getattr(settings, "kis_base_url", None)),
    }
    errors = _list_value(account_state.get("errors"))
    block_reasons: list[str] = []
    if not bool(getattr(settings, "kis_enabled", False)):
        block_reasons.append("kis_disabled")
    if not bool(getattr(settings, "kis_real_order_enabled", False)):
        block_reasons.append("kis_real_order_disabled")
    missing = [key for key, present in config_present.items() if not present]
    if missing:
        block_reasons.append("missing_kis_config")
    if bool(runtime.get("dry_run", True)):
        block_reasons.append("dry_run_enabled")
    if bool(runtime.get("kill_switch", False)):
        block_reasons.append("kill_switch_enabled")
    return {
        "provider": PROVIDER,
        "market": MARKET,
        "environment": getattr(settings, "kis_env", "paper"),
        "kis_enabled": bool(getattr(settings, "kis_enabled", False)),
        "kis_real_order_enabled": bool(
            getattr(settings, "kis_real_order_enabled", False)
        ),
        "config_present": config_present,
        "account_connectivity": {
            "balance_available": bool(balance),
            "positions_available": not any(
                _dict_value(item).get("key") == "positions" for item in errors
            ),
            "open_orders_available": not any(
                _dict_value(item).get("key") == "open_orders" for item in errors
            ),
            "errors": errors,
        },
        "market_session": _market_session_public(market_session),
        "available_cash": _first_float(
            balance,
            "cash",
            "available_cash",
            "buying_power",
            "dnca_tot_amt",
        ),
        "positions_count": len(positions),
        "open_orders_count": len(open_orders),
        "last_kis_api_error": errors[0]["error"] if errors else None,
        "real_order_possible": not block_reasons,
        "real_order_block_reasons": _dedupe(block_reasons),
    }


def _scheduler_section(
    *,
    runtime: dict[str, Any],
    settings: Any,
    scheduler_readiness: dict[str, Any],
    recent_activity: list[dict[str, Any]],
) -> dict[str, Any]:
    configured_allow = bool(
        runtime.get("kis_scheduler_configured_allow_real_orders", False)
        or getattr(settings, "kis_scheduler_allow_real_orders", False)
        or getattr(settings, "kr_scheduler_allow_real_orders", False)
    )
    runtime_allow = bool(runtime.get("kis_scheduler_allow_real_orders", False))
    real_orders_allowed = bool(configured_allow and runtime_allow)
    summary = _dict_value(scheduler_readiness.get("summary"))
    schedule = _list_value(scheduler_readiness.get("schedule"))
    latest = _latest_by_mode(recent_activity)
    block_reasons: list[str] = []
    if not bool(runtime.get("scheduler_enabled", False)):
        block_reasons.append("scheduler_disabled")
    if not bool(runtime.get("kis_scheduler_enabled", False)):
        block_reasons.append("kis_scheduler_disabled")
    if not real_orders_allowed:
        block_reasons.append("scheduler_real_orders_disabled")
    if bool(runtime.get("kis_scheduler_dry_run", True)):
        block_reasons.append("scheduler_dry_run_enabled")
    return {
        "readiness": summary.get("readiness_status")
        or scheduler_readiness.get("readiness_status")
        or "unknown",
        "next_scheduled_slot": summary.get("next_scheduled_slot"),
        "schedule_timezone": _schedule_timezone(schedule),
        "last_scheduler_run": latest.get("scheduler"),
        "last_dry_run_orchestration": latest.get("scheduler_dry_run"),
        "last_guarded_sell": latest.get("scheduler_guarded_sell"),
        "last_guarded_buy": latest.get("scheduler_guarded_buy"),
        "scheduler_real_orders_allowed": real_orders_allowed,
        "scheduler_real_orders_configured": configured_allow,
        "scheduler_real_orders_runtime_allowed": runtime_allow,
        "scheduler_sell_enabled": bool(
            runtime.get("kis_scheduler_sell_enabled", False)
        ),
        "scheduler_buy_enabled": bool(runtime.get("kis_scheduler_buy_enabled", False)),
        "scheduler_dry_run": bool(runtime.get("kis_scheduler_dry_run", True)),
        "scheduler_enabled": bool(runtime.get("scheduler_enabled", False)),
        "kis_scheduler_enabled": bool(runtime.get("kis_scheduler_enabled", False)),
        "sell_priority_required": True,
        "sell_review_before_buy": True,
        "block_reasons": _dedupe(block_reasons),
    }


def _risk_summary(
    db: Session,
    *,
    runtime: dict[str, Any],
    today: dict[str, Any],
    start_utc: datetime,
    end_utc: datetime,
    now_utc: datetime,
) -> dict[str, Any]:
    daily_max_order_limit = int(
        runtime.get("kis_scheduler_max_live_orders_per_day")
        or runtime.get("kis_live_auto_max_orders_per_day")
        or 1
    )
    open_orders = _open_order_rows(db)
    duplicates = _duplicate_open_orders(open_orders)
    stale_orders = [
        _serialize_order(row)
        for row in open_orders
        if _is_stale(row, now_utc=now_utc)
    ]
    failed_count = _count_orders_by_status(
        db,
        statuses=FAILED_INTERNAL_STATUSES,
        start_utc=start_utc,
        end_utc=end_utc,
    )
    rejected_count = _count_orders_by_status(
        db,
        statuses={
            InternalOrderStatus.REJECTED.value,
            InternalOrderStatus.REJECTED_BY_SAFETY_GATE.value,
        },
        start_utc=start_utc,
        end_utc=end_utc,
    )
    buy_limit = int(runtime.get("kis_limited_auto_buy_max_orders_per_day", 1) or 1)
    sell_limit = int(runtime.get("kis_limited_auto_sell_max_orders_per_day", 1) or 1)
    return {
        "daily_max_order_limit": daily_max_order_limit,
        "today_order_count": int(today.get("order_logs_created", 0)),
        "today_broker_submit_count": int(today.get("broker_submits", 0)),
        "today_manual_submit_count": int(today.get("manual_submit_count", 0)),
        "today_auto_buy_count": int(today.get("today_auto_buy_count", 0)),
        "today_auto_sell_count": int(today.get("today_auto_sell_count", 0)),
        "daily_sell_limit_remaining": max(
            0,
            sell_limit - int(today.get("today_auto_sell_count", 0)),
        ),
        "daily_buy_limit_remaining": max(
            0,
            buy_limit - int(today.get("today_auto_buy_count", 0)),
        ),
        "duplicate_open_order_warnings": duplicates,
        "unresolved_stale_orders": stale_orders,
        "failed_order_count": failed_count,
        "rejected_order_count": rejected_count,
        "safety_violation_count": 0,
        "estimated_max_notional_pct": runtime.get(
            "kis_limited_auto_buy_max_notional_pct"
        ),
        "cash_buffer_status": {
            "min_cash_buffer_krw": runtime.get(
                "kis_limited_auto_buy_min_cash_buffer_krw"
            ),
            "status": "configured",
        },
        "mdd_drawdown": {
            "status": "not_available",
            "message": "MDD/drawdown calculation is not implemented yet.",
        },
        "daily_loss": {
            "status": "not_available",
            "message": "Daily loss calculation is not implemented yet.",
        },
    }


def _today_summary(
    db: Session,
    *,
    runtime: dict[str, Any],
    start_utc: datetime,
    end_utc: datetime,
    now_utc: datetime,
) -> dict[str, Any]:
    run_rows = (
        db.query(TradeRunLog)
        .filter(TradeRunLog.created_at >= start_utc)
        .filter(TradeRunLog.created_at < end_utc)
        .all()
    )
    order_rows = (
        db.query(OrderLog)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .all()
    )
    block_counter: Counter[str] = Counter()
    for row in run_rows:
        payload = _json_dict(row.response_payload)
        reasons = _string_list(payload.get("block_reasons"))
        if row.reason and str(row.result or "").lower() in {"blocked", "skipped"}:
            reasons.append(str(row.reason))
        block_counter.update(reason for reason in reasons if reason)

    return {
        "date": now_utc.astimezone(KR_TZ).date().isoformat(),
        "total_runs": len(run_rows),
        "buy_readiness_runs": _count_runs(run_rows, "limited_auto_buy"),
        "sell_readiness_runs": _count_runs_multi(
            run_rows,
            ["limited_auto_sell", "limited_auto_stop_loss", "limited_auto_take_profit"],
        ),
        "scheduler_dry_run_runs": _count_runs_multi(
            run_rows,
            ["scheduler_dry_run", "dry_run_orchestration"],
        ),
        "scheduler_guarded_sell_runs": _count_runs(
            run_rows,
            "kis_scheduler_guarded_sell",
        ),
        "scheduler_guarded_buy_runs": _count_runs(
            run_rows,
            "kis_scheduler_guarded_buy",
        ),
        "order_logs_created": len(order_rows),
        "broker_submits": sum(1 for row in order_rows if _order_has_broker_submit(row)),
        "real_order_submitted_count": sum(
            1 for row in order_rows if _order_real_submitted(row)
        ),
        "manual_submit_count": sum(
            1 for row in order_rows if _order_payload_flag(row, "manual_submit_called")
        ),
        "today_auto_buy_count": sum(
            1
            for row in order_rows
            if str(row.side or "").lower() == "buy"
            and _payload_contains(row, "limited_auto_buy")
        ),
        "today_auto_sell_count": sum(
            1
            for row in order_rows
            if str(row.side or "").lower() == "sell"
            and _payload_contains(row, "limited_auto")
        ),
        "blocked_count": sum(
            1 for row in run_rows if str(row.result or "").lower() == "blocked"
        ),
        "failed_count": sum(
            1 for row in run_rows if str(row.result or "").lower() == "failed"
        ),
        "top_block_reasons": [
            {"reason": reason, "count": count}
            for reason, count in block_counter.most_common(10)
        ],
        "daily_limit": {
            "max_orders": int(runtime.get("kis_scheduler_max_live_orders_per_day", 2) or 2),
            "remaining": max(
                0,
                int(runtime.get("kis_scheduler_max_live_orders_per_day", 2) or 2)
                - len(order_rows),
            ),
        },
    }


def _recent_activity(
    db: Session,
    *,
    cutoff_utc: datetime,
    limit: int,
) -> list[dict[str, Any]]:
    runs = (
        db.query(TradeRunLog)
        .filter(TradeRunLog.created_at >= cutoff_utc)
        .order_by(TradeRunLog.created_at.desc(), TradeRunLog.id.desc())
        .limit(limit)
        .all()
    )
    orders = (
        db.query(OrderLog)
        .filter(OrderLog.created_at >= cutoff_utc)
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .limit(limit)
        .all()
    )
    items = [_serialize_run(row) for row in runs] + [
        _serialize_order_activity(row) for row in orders
    ]
    items.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return items[:limit]


def _safety_checks(
    *,
    runtime: dict[str, Any],
    kis: dict[str, Any],
    scheduler: dict[str, Any],
    risk: dict[str, Any],
    today: dict[str, Any],
    docs: dict[str, Any],
    db_check: dict[str, Any],
    watchlist: dict[str, Any],
    safety_violation_count: int,
) -> list[dict[str, Any]]:
    return [
        _check(
            "dry_run",
            "Dry-run mode",
            "PASS" if runtime.get("dry_run", True) else "WARN",
            bool(runtime.get("dry_run", True)),
            "Dry-run is enabled; real orders are blocked."
            if runtime.get("dry_run", True)
            else "Dry-run is disabled; live gates require review.",
            "Keep dry-run enabled until final live checks pass.",
        ),
        _check(
            "kill_switch",
            "Kill switch",
            "FAIL" if runtime.get("kill_switch", False) else "PASS",
            bool(runtime.get("kill_switch", False)),
            "Kill switch is enabled."
            if runtime.get("kill_switch", False)
            else "Kill switch is clear.",
            "Disable trading paths or investigate before clearing kill switch."
            if runtime.get("kill_switch", False)
            else "Keep kill switch available for emergency stop.",
        ),
        _check(
            "kis_enabled",
            "KIS enabled",
            "PASS" if kis.get("kis_enabled") else "INFO",
            kis.get("kis_enabled") is True,
            "KIS integration is enabled."
            if kis.get("kis_enabled")
            else "KIS integration is disabled.",
            "Enable KIS only after credentials and dry-run checks are complete.",
        ),
        _check(
            "kis_real_order_enabled",
            "KIS real orders",
            "WARN" if kis.get("kis_real_order_enabled") else "PASS",
            kis.get("kis_real_order_enabled") is True,
            "KIS real orders are enabled."
            if kis.get("kis_real_order_enabled")
            else "KIS real orders are disabled.",
            "Keep real orders disabled until live verification starts.",
        ),
        _check(
            "live_auto_sell_enabled",
            "Live auto sell",
            "WARN" if runtime.get("kis_live_auto_sell_enabled") else "PASS",
            bool(runtime.get("kis_live_auto_sell_enabled", False)),
            "Live auto sell is enabled."
            if runtime.get("kis_live_auto_sell_enabled")
            else "Live auto sell is disabled.",
            "Start live verification with sell-only and small notional.",
        ),
        _check(
            "live_auto_buy_enabled",
            "Live auto buy",
            "WARN" if runtime.get("kis_live_auto_buy_enabled") else "PASS",
            bool(runtime.get("kis_live_auto_buy_enabled", False)),
            "Live auto buy is enabled."
            if runtime.get("kis_live_auto_buy_enabled")
            else "Live auto buy is disabled.",
            "Keep scheduler buy disabled until sell path is verified.",
        ),
        _check(
            "scheduler_enabled",
            "Scheduler enabled",
            "INFO" if runtime.get("scheduler_enabled") else "PASS",
            bool(runtime.get("scheduler_enabled", False)),
            "Scheduler is enabled."
            if runtime.get("scheduler_enabled")
            else "Scheduler is disabled.",
            "Run scheduler dry-run orchestration before enabling scheduler live paths.",
        ),
        _check(
            "scheduler_real_orders_allowed",
            "Scheduler real orders",
            "WARN" if scheduler.get("scheduler_real_orders_allowed") else "PASS",
            scheduler.get("scheduler_real_orders_allowed") is True,
            "Scheduler real orders are allowed."
            if scheduler.get("scheduler_real_orders_allowed")
            else "Scheduler real orders are disabled.",
            "Keep scheduler real orders disabled until all reviews pass.",
        ),
        _check(
            "scheduler_sell_enabled",
            "Scheduler sell",
            "WARN" if scheduler.get("scheduler_sell_enabled") else "PASS",
            scheduler.get("scheduler_sell_enabled") is True,
            "Scheduler sell execution is enabled."
            if scheduler.get("scheduler_sell_enabled")
            else "Scheduler sell execution is disabled.",
            "Enable sell-only first when moving toward live scheduler operation.",
        ),
        _check(
            "scheduler_buy_enabled",
            "Scheduler buy",
            "WARN" if scheduler.get("scheduler_buy_enabled") else "PASS",
            scheduler.get("scheduler_buy_enabled") is True,
            "Scheduler buy execution is enabled."
            if scheduler.get("scheduler_buy_enabled")
            else "Scheduler buy execution is disabled.",
            "Keep scheduler buy disabled until sell reviews are verified.",
        ),
        _check(
            "daily_order_limit",
            "Daily order limit",
            "WARN"
            if int(today.get("order_logs_created", 0))
            >= int(today.get("daily_limit", {}).get("max_orders", 1))
            else "PASS",
            today.get("daily_limit", {}),
            "Daily order count is within configured limit.",
            "Keep daily live limits low during live verification.",
        ),
        _check(
            "duplicate_open_orders",
            "Duplicate open orders",
            "WARN" if risk.get("duplicate_open_order_warnings") else "PASS",
            risk.get("duplicate_open_order_warnings"),
            "Duplicate open orders were detected."
            if risk.get("duplicate_open_order_warnings")
            else "No duplicate open orders detected.",
            "Clear duplicate or stale orders before enabling live automation.",
        ),
        _check(
            "failed_rejected_orders",
            "Failed/rejected orders",
            "WARN"
            if int(risk.get("failed_order_count", 0))
            or int(risk.get("rejected_order_count", 0))
            else "PASS",
            {
                "failed": risk.get("failed_order_count", 0),
                "rejected": risk.get("rejected_order_count", 0),
            },
            "Failed or rejected orders exist today."
            if int(risk.get("failed_order_count", 0))
            or int(risk.get("rejected_order_count", 0))
            else "No failed or rejected orders today.",
            "Review failed/rejected orders before continuing.",
        ),
        _check(
            "stale_orders",
            "Stale orders",
            "FAIL" if risk.get("unresolved_stale_orders") else "PASS",
            risk.get("unresolved_stale_orders"),
            "Unresolved stale orders exist."
            if risk.get("unresolved_stale_orders")
            else "No stale open orders detected.",
            "Sync or resolve stale orders before enabling live automation.",
        ),
        _check(
            "db_writable",
            "DB writable",
            "PASS" if db_check.get("writable") else "FAIL",
            db_check.get("writable") is True,
            "Database writable check passed."
            if db_check.get("writable")
            else "Database writable check failed.",
            "Fix database permissions or DATABASE_URL before running automation.",
        ),
        _check(
            "kr_watchlist_baseline",
            "KR watchlist baseline",
            "PASS" if watchlist.get("valid") else "FAIL",
            watchlist,
            "KR watchlist baseline is valid."
            if watchlist.get("valid")
            else "KR watchlist baseline is invalid.",
            "Restore 50-symbol KR watchlist including 005930 and 035420.",
        ),
        _check(
            "review_only_no_submit_invariant",
            "Review-only no-submit invariant",
            "PASS" if safety_violation_count == 0 else "FAIL",
            safety_violation_count,
            "No review safety violations detected."
            if safety_violation_count == 0
            else "Review/audit services reported safety violations.",
            "Review guarded sell/buy audits before live operation.",
        ),
        _check(
            "scheduler_sell_priority",
            "Scheduler sell priority",
            "PASS",
            scheduler.get("sell_review_before_buy") is True,
            "Scheduler buy requires sell review first.",
            "Preserve sell-priority review before scheduler buy.",
        ),
        _check(
            "recent_safety_violations",
            "Recent safety violations",
            "PASS" if safety_violation_count == 0 else "FAIL",
            safety_violation_count,
            "No recent safety violations detected."
            if safety_violation_count == 0
            else "Recent safety violations were detected.",
            "Investigate safety violations before enabling live orders.",
        ),
        _check(
            "production_docs_present",
            "Production docs",
            "PASS" if docs.get("docs_present") else "FAIL",
            docs.get("docs_present") is True,
            "Production documentation is present."
            if docs.get("docs_present")
            else "Production documentation is missing.",
            "Review README and docs production checklist.",
        ),
        _check(
            "env_example_present",
            ".env.example",
            "PASS" if docs.get("env_example_present") else "FAIL",
            docs.get("env_example_present") is True,
            ".env.example is present."
            if docs.get("env_example_present")
            else ".env.example is missing.",
            "Create .env.example with safe defaults and no secrets.",
        ),
        _check(
            "required_env_vars_documented",
            "Required env vars",
            "PASS" if docs.get("required_env_vars_documented") else "FAIL",
            {
                "missing": docs.get("missing_env_vars", []),
            },
            "Required env vars are documented."
            if docs.get("required_env_vars_documented")
            else "Some required env vars are missing from .env.example.",
            "Document required env vars with safe defaults.",
        ),
    ]


def _blocking_issues(
    *,
    runtime: dict[str, Any],
    kis: dict[str, Any],
    scheduler: dict[str, Any],
    risk: dict[str, Any],
    docs: dict[str, Any],
    db_check: dict[str, Any],
    watchlist: dict[str, Any],
    safety_violation_count: int,
) -> list[str]:
    issues: list[str] = []
    if runtime.get("kill_switch", False):
        issues.append("kill_switch_enabled")
    if runtime.get("dry_run", True):
        issues.append("dry_run_enabled")
    if not kis.get("kis_enabled"):
        issues.append("kis_disabled")
    if not kis.get("kis_real_order_enabled"):
        issues.append("kis_real_order_disabled")
    if "missing_kis_config" in kis.get("real_order_block_reasons", []):
        issues.append("missing_kis_config")
    if not scheduler.get("scheduler_real_orders_allowed"):
        issues.append("scheduler_real_orders_disabled")
    if not db_check.get("writable"):
        issues.append("db_not_writable")
    if not watchlist.get("valid"):
        issues.append("watchlist_baseline_invalid")
    if risk.get("unresolved_stale_orders"):
        issues.append("stale_open_orders")
    if safety_violation_count:
        issues.append("safety_violations_detected")
    if not docs.get("docs_present"):
        issues.append("documentation_missing")
    if not docs.get("env_example_present"):
        issues.append("env_example_missing")
    return _dedupe(issues)


def _warnings(
    *,
    runtime: dict[str, Any],
    today: dict[str, Any],
    risk: dict[str, Any],
    docs: dict[str, Any],
    scheduler: dict[str, Any],
    recent_activity: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if runtime.get("kis_live_auto_buy_enabled", False):
        warnings.append("live_auto_buy_enabled")
    if runtime.get("kis_scheduler_buy_enabled", False):
        warnings.append("scheduler_buy_enabled")
    if int(today.get("order_logs_created", 0)) >= int(
        today.get("daily_limit", {}).get("max_orders", 1)
    ):
        warnings.append("high_order_count_today")
    if not _has_recent_mode(recent_activity, "scheduler_dry_run"):
        warnings.append("no_recent_dry_run")
    if not (
        _has_recent_mode(recent_activity, "scheduler_guarded_sell")
        or _has_recent_mode(recent_activity, "scheduler_guarded_buy")
    ):
        warnings.append("no_recent_scheduler_review")
    if risk.get("mdd_drawdown", {}).get("status") == "not_available":
        warnings.append("missing_mdd_calculation")
    if not recent_activity:
        warnings.append("insufficient_recent_history")
    if not docs.get("docs_present"):
        warnings.append("documentation_missing")
    if not docs.get("env_example_present"):
        warnings.append("env_example_missing")
    if scheduler.get("scheduler_buy_enabled"):
        warnings.append("scheduler_buy_requires_sell_path_verified")
    return _dedupe(warnings)


def _recommended_actions(
    *,
    runtime: dict[str, Any],
    blocking_issues: list[str],
    warnings: list[str],
    recent_activity: list[dict[str, Any]],
) -> list[str]:
    actions = ["Keep dry_run=true for verification."]
    if "no_recent_dry_run" in warnings or not _has_recent_mode(
        recent_activity,
        "scheduler_dry_run",
    ):
        actions.append("Run scheduler dry-run orchestration once.")
    actions.append("Review guarded sell/buy audits.")
    if "stale_open_orders" in blocking_issues:
        actions.append("Clear stale orders.")
    if "missing_kis_config" in blocking_issues:
        actions.append("Confirm KIS credentials.")
    actions.append("Review .env settings before live trading.")
    if runtime.get("kis_scheduler_buy_enabled", False):
        actions.append("Do not enable scheduler buy until sell path has been verified.")
    actions.append("Start live verification with sell-only and very small notional.")
    return _dedupe(actions)


def _live_trading_ready(
    *,
    runtime: dict[str, Any],
    kis: dict[str, Any],
    scheduler: dict[str, Any],
    db_check: dict[str, Any],
    watchlist: dict[str, Any],
    docs: dict[str, Any],
    safety_violation_count: int,
) -> bool:
    return bool(
        not runtime.get("dry_run", True)
        and not runtime.get("kill_switch", False)
        and kis.get("kis_enabled")
        and kis.get("kis_real_order_enabled")
        and kis.get("real_order_possible")
        and scheduler.get("scheduler_real_orders_allowed")
        and db_check.get("writable")
        and watchlist.get("valid")
        and docs.get("docs_present")
        and docs.get("env_example_present")
        and docs.get("required_env_vars_documented")
        and safety_violation_count == 0
    )


def _hard_blocked(
    *,
    runtime: dict[str, Any],
    db_check: dict[str, Any],
    watchlist: dict[str, Any],
    risk: dict[str, Any],
    safety_violation_count: int,
) -> bool:
    return bool(
        runtime.get("kill_switch", False)
        or not db_check.get("writable")
        or not watchlist.get("valid")
        or risk.get("unresolved_stale_orders")
        or safety_violation_count
    )


def _overall_status(
    *,
    runtime: dict[str, Any],
    live_trading_ready: bool,
    hard_blocked: bool,
) -> str:
    if hard_blocked:
        return "BLOCKED"
    if live_trading_ready:
        return "LIVE_ENABLED"
    if runtime.get("dry_run", True):
        return "SAFE_DRY_RUN"
    return "REVIEW_REQUIRED"


def _db_writable_check(db: Session) -> dict[str, Any]:
    try:
        db.execute(text("CREATE TEMP TABLE IF NOT EXISTS ops_readiness_write_check (id INTEGER)"))
        db.execute(text("INSERT INTO ops_readiness_write_check (id) VALUES (1)"))
        db.execute(text("DELETE FROM ops_readiness_write_check"))
        return {"writable": True, "method": "temp_table_write"}
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        return {
            "writable": False,
            "method": "temp_table_write",
            "error": _safe_error(exc),
        }


def _env_example_keys(path: Path) -> set[str]:
    if not path.exists():
        return set()
    keys: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def _check(
    key: str,
    label: str,
    status: str,
    value: Any,
    message: str,
    recommended_action: str,
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "status": status,
        "value": value,
        "message": message,
        "recommended_action": recommended_action,
    }


def _count_orders_by_status(
    db: Session,
    *,
    statuses: set[str],
    start_utc: datetime,
    end_utc: datetime,
) -> int:
    return int(
        db.query(OrderLog)
        .filter(OrderLog.created_at >= start_utc)
        .filter(OrderLog.created_at < end_utc)
        .filter(OrderLog.internal_status.in_(sorted(statuses)))
        .count()
        or 0
    )


def _open_order_rows(db: Session) -> list[OrderLog]:
    return (
        db.query(OrderLog)
        .filter(OrderLog.internal_status.in_(sorted(OPEN_INTERNAL_STATUSES)))
        .order_by(OrderLog.created_at.desc(), OrderLog.id.desc())
        .all()
    )


def _duplicate_open_orders(rows: list[OrderLog]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[OrderLog]] = {}
    for row in rows:
        key = (str(row.symbol or "").upper(), str(row.side or "").lower())
        grouped.setdefault(key, []).append(row)
    return [
        {
            "symbol": symbol,
            "side": side,
            "count": len(items),
            "order_ids": [item.id for item in items],
        }
        for (symbol, side), items in grouped.items()
        if symbol and side and len(items) > 1
    ]


def _is_stale(row: OrderLog, *, now_utc: datetime) -> bool:
    created = _as_utc(row.created_at)
    if created is None:
        return False
    return now_utc - created > timedelta(days=1)


def _serialize_order(row: OrderLog) -> dict[str, Any]:
    return {
        "order_id": row.id,
        "broker": row.broker,
        "market": row.market,
        "symbol": row.symbol,
        "side": row.side,
        "internal_status": row.internal_status,
        "broker_status": row.broker_status,
        "broker_order_id": row.broker_order_id,
        "kis_odno": row.kis_odno,
        "created_at": _iso_datetime(row.created_at),
    }


def _serialize_order_activity(row: OrderLog) -> dict[str, Any]:
    return {
        **_serialize_order(row),
        "type": "order",
        "result": row.internal_status,
        "real_order_submitted": _order_real_submitted(row),
        "broker_submit_called": _order_has_broker_submit(row),
    }


def _serialize_run(row: TradeRunLog) -> dict[str, Any]:
    payload = _json_dict(row.response_payload)
    return {
        "type": "trade_run",
        "run_id": row.id,
        "created_at": _iso_datetime(row.created_at),
        "trigger_source": row.trigger_source,
        "mode": row.mode,
        "symbol": row.symbol,
        "result": row.result,
        "reason": row.reason,
        "action": payload.get("action"),
        "real_order_submitted": payload.get("real_order_submitted") is True,
        "broker_submit_called": payload.get("broker_submit_called") is True,
        "manual_submit_called": payload.get("manual_submit_called") is True,
        "block_reasons": _string_list(payload.get("block_reasons")),
    }


def _count_runs(rows: list[TradeRunLog], needle: str) -> int:
    needle_lower = needle.lower()
    return sum(1 for row in rows if needle_lower in _run_text(row))


def _count_runs_multi(rows: list[TradeRunLog], needles: list[str]) -> int:
    lowered = [needle.lower() for needle in needles]
    return sum(1 for row in rows if any(needle in _run_text(row) for needle in lowered))


def _run_text(row: TradeRunLog) -> str:
    return " ".join(
        [
            str(row.mode or ""),
            str(row.trigger_source or ""),
            str(row.request_payload or ""),
            str(row.response_payload or ""),
        ]
    ).lower()


def _order_has_broker_submit(row: OrderLog) -> bool:
    return bool(
        row.broker_order_id
        or row.kis_odno
        or str(row.internal_status or "").upper() in LIVE_INTERNAL_STATUSES
        or _order_payload_flag(row, "broker_submit_called")
        or _order_payload_flag(row, "real_order_submitted")
    )


def _order_real_submitted(row: OrderLog) -> bool:
    return bool(
        row.broker_order_id
        or row.kis_odno
        or _order_payload_flag(row, "real_order_submitted")
    )


def _order_payload_flag(row: OrderLog, key: str) -> bool:
    for raw in (row.request_payload, row.response_payload, row.last_sync_payload):
        payload = _json_dict(raw)
        if payload.get(key) is True:
            return True
    return False


def _payload_contains(row: OrderLog, needle: str) -> bool:
    value = " ".join(
        [
            str(row.request_payload or ""),
            str(row.response_payload or ""),
            str(row.last_sync_payload or ""),
        ]
    ).lower()
    return needle.lower() in value


def _safety_violation_count(
    *,
    guarded_sell_review: dict[str, Any],
    limited_buy_review: dict[str, Any],
) -> int:
    return len(_list_value(guarded_sell_review.get("safety_violations"))) + len(
        _list_value(limited_buy_review.get("safety_violations"))
    )


def _module_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = _dict_value(payload.get("summary"))
    return {
        "available": payload.get("available", True) is not False,
        "mode": payload.get("mode"),
        "result": payload.get("result") or summary.get("result"),
        "primary_block_reason": payload.get("primary_block_reason")
        or summary.get("primary_block_reason"),
        "error": payload.get("error"),
    }


def _latest_by_mode(recent_activity: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for item in recent_activity:
        mode = str(item.get("mode") or "").lower()
        trigger = str(item.get("trigger_source") or "").lower()
        if "scheduler" in mode or "scheduler" in trigger:
            result.setdefault("scheduler", item)
        if "dry_run" in mode or "dry_run" in trigger:
            result.setdefault("scheduler_dry_run", item)
        if "guarded_sell" in mode or "guarded_sell" in trigger:
            result.setdefault("scheduler_guarded_sell", item)
        if "guarded_buy" in mode or "guarded_buy" in trigger:
            result.setdefault("scheduler_guarded_buy", item)
    return result


def _schedule_timezone(schedule: list[Any]) -> str:
    for item in schedule:
        if isinstance(item, dict) and item.get("timezone"):
            return str(item["timezone"])
    return "Asia/Seoul"


def _has_recent_mode(recent_activity: list[dict[str, Any]], needle: str) -> bool:
    lowered = needle.lower()
    return any(
        lowered
        in " ".join(
            [
                str(item.get("mode") or ""),
                str(item.get("trigger_source") or ""),
            ]
        ).lower()
        for item in recent_activity
    )


def _latest_activity_at(recent_activity: list[dict[str, Any]]) -> str | None:
    if not recent_activity:
        return None
    return str(recent_activity[0].get("created_at") or "") or None


def _critical_issue_count(safety_checks: list[dict[str, Any]]) -> int:
    return sum(1 for item in safety_checks if item.get("status") == "FAIL")


def _market_session_public(market_session: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "market",
        "timezone",
        "is_market_open",
        "is_entry_allowed_now",
        "is_near_close",
        "closure_reason",
        "closure_name",
        "effective_close",
        "no_new_entry_after",
        "local_time",
        "error",
    ]
    return {key: market_session.get(key) for key in keys if key in market_session}


def _env_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value or "").strip().lower() in {"1", "true", "yes", "y"}


def _first_float(payload: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = _float_or_none(payload.get(key))
        if value is not None:
            return value
    return None


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        text_value = str(value).replace(",", "").strip()
        if not text_value:
            return None
        return float(text_value)
    except (TypeError, ValueError):
        return None


def _json_dict(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _list_value(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text_value = value.strip()
        return [text_value] if text_value else []
    if isinstance(value, (list, tuple, set)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _coerce_like(value: Any, default: Any) -> Any:
    if isinstance(default, bool):
        return _env_bool(value)
    if isinstance(default, int) and not isinstance(default, bool):
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    if isinstance(default, float):
        try:
            return float(value)
        except (TypeError, ValueError):
            return default
    return str(value) if isinstance(default, str) else value


def _normalize_symbol(value: Any) -> str | None:
    text_value = str(value or "").strip().upper()
    if not text_value or text_value in {"NONE", "NULL"}:
        return None
    if text_value.isdigit() and len(text_value) < 6:
        text_value = text_value.zfill(6)
    return text_value


def _kr_day_bounds_utc(now_utc: datetime) -> tuple[datetime, datetime]:
    local_now = now_utc.astimezone(KR_TZ)
    start_local = datetime.combine(local_now.date(), time.min, tzinfo=KR_TZ)
    end_local = start_local + timedelta(days=1)
    return _naive_utc(start_local), _naive_utc(end_local)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _utc_now(value: datetime | None = None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _naive_utc(value: datetime) -> datetime:
    return _utc_now(value).replace(tzinfo=None)


def _iso_datetime(value: datetime | None) -> str | None:
    parsed = _as_utc(value)
    return parsed.isoformat() if parsed is not None else None


def _safe_error(exc: Exception) -> str:
    text_value = str(exc).strip() or exc.__class__.__name__
    if len(text_value) > 180:
        text_value = f"{text_value[:180]}..."
    return f"{exc.__class__.__name__}: {text_value}"
