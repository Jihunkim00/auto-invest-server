from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.db.models import OrderLog
from app.services.runtime_setting_service import RuntimeSettingService
from app.services.strategy_performance_service import StrategyPerformanceService
from app.services.strategy_profile_service import StrategyProfileService


PositionLoader = Callable[[Session, str, str], list[dict[str, Any]]]
BalanceLoader = Callable[[Session, str, str], dict[str, Any]]
_KST = ZoneInfo("Asia/Seoul")
_IGNORED_ORDER_STATUSES = {
    "CANCELLED",
    "CANCELED",
    "DRY_RUN_SIMULATED",
    "REJECTED",
    "REJECTED_BY_SAFETY_GATE",
    "FAILED",
}


class StrategyRiskBudgetService:
    def __init__(
        self,
        *,
        strategy_profiles: StrategyProfileService | None = None,
        runtime_settings: RuntimeSettingService | None = None,
        performance_service: StrategyPerformanceService | None = None,
        position_loader: PositionLoader | None = None,
        balance_loader: BalanceLoader | None = None,
    ) -> None:
        self.strategy_profiles = strategy_profiles or StrategyProfileService()
        self.runtime_settings = runtime_settings or RuntimeSettingService()
        self.position_loader = position_loader
        self.balance_loader = balance_loader
        self.performance_service = performance_service or StrategyPerformanceService(
            position_loader=position_loader,
            strategy_profiles=self.strategy_profiles,
        )

    def calculate(
        self,
        db: Session,
        *,
        provider: str = "kis",
        market: str = "KR",
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        normalized_provider = str(provider or "kis").strip().lower() or "kis"
        normalized_market = str(market or "KR").strip().upper() or "KR"
        active = (
            self.strategy_profiles.get_profile(db, profile_name)
            if profile_name
            else self.strategy_profiles.active_profile(db)
        )
        profile = self.strategy_profiles.serialize_profile(active)
        monthly_kwargs = {
            "provider": normalized_provider,
            "market": normalized_market,
        }
        if profile_name:
            monthly_kwargs["profile_name"] = profile_name
        monthly = self.performance_service.monthly(db, **monthly_kwargs)
        daily = self.performance_service.daily(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        trades = self.performance_service.trades(
            db,
            provider=normalized_provider,
            market=normalized_market,
            limit=100,
        )
        settings = self.runtime_settings.get_settings_read_only(db)
        positions, position_notes = self._positions(
            db,
            normalized_provider,
            normalized_market,
        )
        balance, balance_notes = self._balance(
            db,
            normalized_provider,
            normalized_market,
        )

        monthly_return = _float(monthly.get("current_month_return_pct"))
        daily_return = _float(daily.get("pnl_pct"))
        monthly_max_loss = _float(profile.get("monthly_max_loss_pct"))
        daily_max_loss = _float(profile.get("daily_max_loss_pct"))
        target_progress = _float(monthly.get("target_progress_pct"))
        target_hit = bool(monthly.get("target_hit"))
        monthly_loss_hit = monthly_max_loss < 0 and monthly_return <= monthly_max_loss
        daily_loss_hit = daily_max_loss < 0 and daily_return <= daily_max_loss
        trades_used = self._trades_used_today(
            db,
            provider=normalized_provider,
            market=normalized_market,
        )
        max_trades = max(0, int(profile.get("max_trades_per_day") or 0))
        current_positions = self._position_count(positions)
        max_positions = max(0, int(profile.get("max_positions") or 0))
        consecutive_losses = self._consecutive_losses(trades.get("items"))
        total_assets = self._total_assets(balance, positions)
        max_order_pct = max(0.0, _float(profile.get("max_order_notional_pct")))
        profile_max_krw = max(0.0, _float(profile.get("max_order_notional_krw")))
        pct_cap_krw = total_assets * max_order_pct if total_assets and total_assets > 0 else None
        effective_max_krw = (
            min(profile_max_krw, pct_cap_krw)
            if pct_cap_krw is not None and profile_max_krw > 0
            else profile_max_krw
        )

        quality_notes = _dedupe(
            [
                *_quality_notes(monthly.get("data_quality")),
                *_quality_notes(daily.get("data_quality")),
                *_quality_notes(trades.get("data_quality")),
                *position_notes,
                *balance_notes,
            ]
        )
        if total_assets is None or total_assets <= 0:
            quality_notes.append("total_assets_unavailable")
        quality_limited = any(
            note.startswith(
                (
                    "positions_not_loaded",
                    "positions_unavailable",
                    "balance_not_loaded",
                    "balance_unavailable",
                    "average_price_missing",
                    "unmatched_sell",
                    "insufficient_cost_basis",
                    "total_assets_unavailable",
                )
            )
            for note in quality_notes
        )

        risk_flags: list[str] = []
        gating_notes: list[str] = []
        block_reason = None

        def block(flag: str, note: str) -> None:
            nonlocal block_reason
            risk_flags.append(flag)
            gating_notes.append(note)
            if block_reason is None:
                block_reason = flag

        if bool(settings.get("kill_switch")):
            block("kill_switch_active", "Kill switch가 활성화되어 신규 진입을 차단합니다.")
        if monthly_loss_hit:
            block(
                "monthly_loss_limit_hit",
                f"월 추정 수익률 {monthly_return:.2%}가 월 손실 한도 {monthly_max_loss:.2%}에 도달했습니다.",
            )
        if daily_loss_hit:
            block(
                "daily_loss_limit_hit",
                f"일간 추정 수익률 {daily_return:.2%}가 일일 손실 한도 {daily_max_loss:.2%}에 도달했습니다.",
            )
        if target_hit and bool(profile.get("stop_after_monthly_target")):
            block(
                "monthly_target_hit_entry_blocked",
                "월 목표를 달성했고 현재 전략은 목표 달성 후 신규 진입을 중단합니다.",
            )
        if max_trades <= 0 or trades_used >= max_trades:
            block(
                "daily_trade_limit_hit",
                f"오늘 거래 사용 횟수는 {trades_used}/{max_trades}회입니다.",
            )
        if max_positions <= 0 or current_positions >= max_positions:
            block(
                "max_positions_hit",
                f"현재 보유 종목 수는 {current_positions}/{max_positions}개입니다.",
            )

        sizing_multiplier = 1.0
        if target_hit and not bool(profile.get("stop_after_monthly_target")):
            sizing_multiplier = 0.5
            risk_flags.append("monthly_target_hit_size_reduced")
            gating_notes.append("월 목표 달성 후 추가 진입은 권장 주문 크기를 50%로 축소합니다.")
        elif target_progress >= 80:
            sizing_multiplier = 0.5
            risk_flags.append("near_monthly_target_size_reduced")
            gating_notes.append("월 목표 진행률이 80% 이상이어서 권장 주문 크기를 50%로 축소합니다.")

        threshold = max(
            0,
            int(profile.get("consecutive_loss_reduce_threshold") or 0),
        )
        if (
            bool(profile.get("reduce_size_after_loss"))
            and threshold > 0
            and consecutive_losses >= threshold
        ):
            sizing_multiplier = min(sizing_multiplier, 0.5)
            risk_flags.append("consecutive_loss_size_reduced")
            gating_notes.append(
                f"최근 연속 손실 {consecutive_losses}회로 권장 주문 크기를 50%로 축소합니다."
            )

        if quality_limited:
            sizing_multiplier = min(sizing_multiplier, 0.5)
            risk_flags.append("performance_data_quality_limited")
            gating_notes.append(
                "성과 데이터 품질이 제한되어 보수적인 주문 크기를 권장합니다."
            )

        recommended_pct = max_order_pct * sizing_multiplier
        recommended_krw = max(0.0, effective_max_krw * sizing_multiplier)
        data_quality = {
            "mode": "conservative" if quality_limited else "best_effort",
            "limited": quality_limited,
            "notes": quality_notes,
            "total_assets_available": bool(total_assets and total_assets > 0),
            "positions_available": not any(
                note.startswith(("positions_not_loaded", "positions_unavailable"))
                for note in position_notes
            ),
        }
        return {
            "provider": normalized_provider,
            "market": normalized_market,
            "active_profile": str(profile.get("profile_name") or "safe"),
            "monthly_target_return_pct": _float(profile.get("monthly_target_return_pct")),
            "monthly_target_min_pct": _float(profile.get("monthly_target_min_pct")),
            "monthly_target_max_pct": _float(profile.get("monthly_target_max_pct")),
            "current_month_return_pct": monthly_return,
            "target_progress_pct": target_progress,
            "target_hit": target_hit,
            "monthly_max_loss_pct": monthly_max_loss,
            "loss_budget_used_pct": _float(monthly.get("loss_budget_used_pct")),
            "monthly_loss_limit_hit": monthly_loss_hit,
            "daily_max_loss_pct": daily_max_loss,
            "current_daily_return_pct": daily_return,
            "daily_loss_limit_hit": daily_loss_hit,
            "max_order_notional_pct": max_order_pct,
            "max_order_notional_krw": profile_max_krw,
            "recommended_order_notional_pct": recommended_pct,
            "recommended_order_notional_krw": recommended_krw,
            "max_trades_per_day": max_trades,
            "trades_used_today": trades_used,
            "trades_remaining_today": max(0, max_trades - trades_used),
            "max_positions": max_positions,
            "current_positions_count": current_positions,
            "new_entries_allowed": block_reason is None,
            "primary_block_reason": block_reason,
            "risk_flags": _dedupe(risk_flags),
            "gating_notes": _dedupe(gating_notes),
            "data_quality": data_quality,
            "safety": _safety(),
            "_profile": profile,
            "_monthly": monthly,
            "_daily": daily,
            "_trades": trades,
            "_settings": settings,
            "_positions": positions,
            "_balance": balance,
            "_total_assets": total_assets,
            "_effective_max_order_notional_krw": effective_max_krw,
            "_sizing_multiplier": sizing_multiplier,
            "_consecutive_losses": consecutive_losses,
        }

    def state(
        self,
        db: Session,
        *,
        provider: str = "kis",
        market: str = "KR",
        profile_name: str | None = None,
    ) -> dict[str, Any]:
        return {
            key: value
            for key, value in self.calculate(
                db,
                provider=provider,
                market=market,
                profile_name=profile_name,
            ).items()
            if not key.startswith("_")
        }

    def _positions(
        self,
        db: Session,
        provider: str,
        market: str,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        loader = self.position_loader or getattr(
            self.performance_service,
            "position_loader",
            None,
        )
        if loader is None:
            return [], ["positions_not_loaded"]
        try:
            rows = loader(db, provider, market)
            return [dict(item) for item in rows if isinstance(item, dict)], []
        except Exception as exc:
            return [], [f"positions_unavailable:{exc.__class__.__name__}"]

    def _balance(
        self,
        db: Session,
        provider: str,
        market: str,
    ) -> tuple[dict[str, Any], list[str]]:
        if self.balance_loader is None:
            return {}, ["balance_not_loaded"]
        try:
            payload = self.balance_loader(db, provider, market)
            return (dict(payload) if isinstance(payload, dict) else {}), []
        except Exception as exc:
            return {}, [f"balance_unavailable:{exc.__class__.__name__}"]

    def _position_count(self, positions: list[dict[str, Any]]) -> int:
        symbols = {
            str(item.get("symbol") or "").strip().upper()
            for item in positions
            if str(item.get("symbol") or "").strip()
            and _float(item.get("qty") or item.get("quantity")) > 0
        }
        return len(symbols)

    def _total_assets(
        self,
        balance: dict[str, Any],
        positions: list[dict[str, Any]],
    ) -> float | None:
        for key in (
            "total_asset_value",
            "total_assets",
            "equity",
            "asset_value",
            "total_evaluation_amount",
        ):
            value = _optional_float(balance.get(key))
            if value is not None and value > 0:
                return value
        cash = _optional_float(
            balance.get("cash")
            or balance.get("available_cash")
            or balance.get("orderable_cash")
        )
        market_value = sum(
            max(
                0.0,
                _float(
                    item.get("market_value")
                    or item.get("current_value")
                    or item.get("evaluation_amount")
                ),
            )
            for item in positions
        )
        fallback = (cash or 0.0) + market_value
        return fallback if fallback > 0 else None

    def _trades_used_today(
        self,
        db: Session,
        *,
        provider: str,
        market: str,
    ) -> int:
        today = datetime.now(_KST).date()
        start = datetime.combine(today, time.min, tzinfo=_KST).astimezone(UTC)
        end = start + timedelta(days=1)
        rows = (
            db.query(OrderLog)
            .filter(OrderLog.broker == provider)
            .filter(OrderLog.side == "buy")
            .all()
        )
        count = 0
        for row in rows:
            row_market = str(row.market or ("KR" if row.broker == "kis" else "US")).upper()
            created = row.submitted_at or row.created_at
            if created is None:
                continue
            aware = created if created.tzinfo is not None else created.replace(tzinfo=UTC)
            status = str(row.internal_status or "").upper()
            if row_market == market and start <= aware < end and status not in _IGNORED_ORDER_STATUSES:
                count += 1
        return count

    def _consecutive_losses(self, items: Any) -> int:
        if not isinstance(items, list):
            return 0
        count = 0
        for item in items:
            if not isinstance(item, dict) or item.get("realized_pnl") is None:
                continue
            pnl = _float(item.get("realized_pnl"))
            if pnl < 0:
                count += 1
                continue
            break
        return count


def _quality_notes(value: Any) -> list[str]:
    if not isinstance(value, dict):
        return []
    notes = value.get("notes")
    return [str(item) for item in notes] if isinstance(notes, list) else []


def _optional_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(str(value).replace(",", ""))
    except Exception:
        return None


def _float(value: Any) -> float:
    return _optional_float(value) or 0.0


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def _safety() -> dict[str, Any]:
    return {
        "read_only": True,
        "safe_execution_only": True,
        "real_order_submitted": False,
        "validation_called": False,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "setting_changed": False,
        "scheduler_changed": False,
        "broker_api_called": False,
        "mutation": False,
    }
