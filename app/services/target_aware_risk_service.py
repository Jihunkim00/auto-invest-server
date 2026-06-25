from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.schemas.strategy_risk import StrategyEntryRiskEvaluationRequest
from app.services.strategy_risk_budget_service import StrategyRiskBudgetService


class TargetAwareRiskService:
    def __init__(
        self,
        *,
        budget_service: StrategyRiskBudgetService | None = None,
    ) -> None:
        self.budget_service = budget_service or StrategyRiskBudgetService()

    def risk_state(
        self,
        db: Session,
        *,
        provider: str = "kis",
        market: str = "KR",
    ) -> dict[str, Any]:
        return self.budget_service.state(
            db,
            provider=provider,
            market=market,
        )

    def evaluate_entry(
        self,
        db: Session,
        request: StrategyEntryRiskEvaluationRequest | dict[str, Any],
    ) -> dict[str, Any]:
        payload = (
            request
            if isinstance(request, StrategyEntryRiskEvaluationRequest)
            else StrategyEntryRiskEvaluationRequest.model_validate(request)
        )
        snapshot = self.budget_service.calculate(
            db,
            provider=payload.provider,
            market=payload.market,
        )
        profile = snapshot["_profile"]
        flags = list(snapshot["risk_flags"])
        notes = list(snapshot["gating_notes"])
        checks = self._base_checks(snapshot)
        block_reason = snapshot["primary_block_reason"]
        side = str(payload.side or "").strip().lower()
        total_assets = snapshot.get("_total_assets")
        requested_krw = payload.requested_notional_krw
        if requested_krw is None and payload.requested_notional_pct is not None:
            if total_assets and total_assets > 0:
                requested_krw = float(total_assets) * float(payload.requested_notional_pct)
            else:
                flags.append("requested_notional_pct_unresolved")
                notes.append("총자산 데이터가 없어 요청 주문 비중을 원화로 환산하지 못했습니다.")

        if side not in {"buy", "sell"}:
            block_reason = block_reason or "invalid_side"
            flags.append("invalid_side")
            notes.append("side는 buy 또는 sell이어야 합니다.")

        threshold = _float(profile.get("buy_score_threshold"))
        if side == "buy" and payload.buy_score is not None:
            score_ok = float(payload.buy_score) >= threshold
            checks.append(
                _check(
                    "profile_buy_score",
                    score_ok,
                    (
                        f"{snapshot['active_profile']} 매수 기준 {threshold:g}점 대비 "
                        f"현재 buy score는 {float(payload.buy_score):g}점입니다."
                    ),
                    severity="block" if not score_ok else "ok",
                )
            )
            if not score_ok:
                block_reason = block_reason or "below_profile_buy_threshold"
                flags.append("below_profile_buy_threshold")
                notes.append(
                    f"{snapshot['active_profile']} 매수 기준은 {threshold:g}점인데 현재 buy score는 {float(payload.buy_score):g}점입니다."
                )
        elif side == "buy":
            checks.append(
                _check(
                    "profile_buy_score",
                    True,
                    "buy score가 제공되지 않아 profile 점수 기준은 실제 confirm gate에서 다시 확인해야 합니다.",
                    severity="warning",
                )
            )

        if requested_krw is not None and requested_krw <= 0:
            block_reason = block_reason or "invalid_requested_notional"
            flags.append("invalid_requested_notional")
            notes.append("요청 주문금액은 0보다 커야 합니다.")
            checks.append(
                _check(
                    "requested_notional",
                    False,
                    "요청 주문금액이 0 이하입니다.",
                    severity="block",
                )
            )

        cap = max(0.0, _float(snapshot.get("_effective_max_order_notional_krw")))
        multiplier = max(0.0, min(1.0, _float(snapshot.get("_sizing_multiplier"))))
        recommended = max(0.0, cap * multiplier)
        base_notional = cap if requested_krw is None else min(max(requested_krw, 0.0), cap)
        approved_notional = max(0.0, base_notional * multiplier)
        if requested_krw is not None and cap > 0 and requested_krw > cap:
            flags.append("notional_capped_by_profile")
            notes.append(
                f"요청 주문금액을 profile 한도 {cap:,.0f}원으로 제한했습니다."
            )
            checks.append(
                _check(
                    "profile_notional_cap",
                    True,
                    f"요청금액이 profile 한도를 초과해 {cap:,.0f}원으로 축소됩니다.",
                    severity="warning",
                )
            )
        else:
            checks.append(
                _check(
                    "profile_notional_cap",
                    True,
                    f"profile 기준 유효 주문 한도는 {cap:,.0f}원입니다.",
                )
            )

        approved = block_reason is None
        if not approved:
            approved_notional = 0.0
        reduction_flags = {
            "monthly_target_hit_size_reduced",
            "near_monthly_target_size_reduced",
            "consecutive_loss_size_reduced",
            "performance_data_quality_limited",
            "notional_capped_by_profile",
        }
        reduced = bool(reduction_flags.intersection(flags))
        action = "block" if not approved else ("reduce" if reduced else "approve")
        return {
            "approved": approved,
            "action": action,
            "symbol": str(payload.symbol or "").strip().upper(),
            "active_profile": snapshot["active_profile"],
            "requested_notional_krw": (
                None if requested_krw is None else round(float(requested_krw), 2)
            ),
            "approved_notional_krw": round(approved_notional, 2),
            "recommended_notional_krw": round(recommended, 2),
            "sizing_multiplier": round(multiplier, 4),
            "block_reason": block_reason,
            "risk_flags": _dedupe(flags),
            "gating_notes": _dedupe(notes),
            "checks": checks,
            "monthly_progress": {
                "current_month_return_pct": snapshot["current_month_return_pct"],
                "target_progress_pct": snapshot["target_progress_pct"],
                "target_hit": snapshot["target_hit"],
                "monthly_max_loss_pct": snapshot["monthly_max_loss_pct"],
                "monthly_loss_limit_hit": snapshot["monthly_loss_limit_hit"],
                "loss_budget_used_pct": snapshot["loss_budget_used_pct"],
            },
            "daily_progress": {
                "current_daily_return_pct": snapshot["current_daily_return_pct"],
                "daily_max_loss_pct": snapshot["daily_max_loss_pct"],
                "daily_loss_limit_hit": snapshot["daily_loss_limit_hit"],
                "trades_used_today": snapshot["trades_used_today"],
                "trades_remaining_today": snapshot["trades_remaining_today"],
            },
            "profile_thresholds": {
                "buy_score_threshold": threshold,
                "sell_score_threshold": _float(profile.get("sell_score_threshold")),
                "max_order_notional_pct": snapshot["max_order_notional_pct"],
                "max_order_notional_krw": snapshot["max_order_notional_krw"],
                "effective_max_order_notional_krw": cap,
                "max_trades_per_day": snapshot["max_trades_per_day"],
                "max_positions": snapshot["max_positions"],
                "consecutive_loss_reduce_threshold": int(
                    profile.get("consecutive_loss_reduce_threshold") or 0
                ),
                "consecutive_losses": int(snapshot.get("_consecutive_losses") or 0),
            },
            "safety": {
                **snapshot["safety"],
                "dry_run_requested": bool(payload.dry_run),
            },
        }

    def _base_checks(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            _check(
                "kill_switch",
                "kill_switch_active" not in snapshot["risk_flags"],
                (
                    "Kill switch가 비활성화되어 있습니다."
                    if "kill_switch_active" not in snapshot["risk_flags"]
                    else "Kill switch가 활성화되어 있습니다."
                ),
                severity=(
                    "ok"
                    if "kill_switch_active" not in snapshot["risk_flags"]
                    else "block"
                ),
            ),
            _check(
                "monthly_loss_limit",
                not snapshot["monthly_loss_limit_hit"],
                "월 손실 한도에 도달하지 않았습니다."
                if not snapshot["monthly_loss_limit_hit"]
                else "월 손실 한도에 도달했습니다.",
                severity="ok" if not snapshot["monthly_loss_limit_hit"] else "block",
            ),
            _check(
                "daily_loss_limit",
                not snapshot["daily_loss_limit_hit"],
                "일일 손실 한도에 도달하지 않았습니다."
                if not snapshot["daily_loss_limit_hit"]
                else "일일 손실 한도에 도달했습니다.",
                severity="ok" if not snapshot["daily_loss_limit_hit"] else "block",
            ),
            _check(
                "daily_trade_limit",
                snapshot["trades_remaining_today"] > 0,
                f"오늘 거래 가능 횟수는 {snapshot['trades_remaining_today']}회 남았습니다.",
                severity="ok" if snapshot["trades_remaining_today"] > 0 else "block",
            ),
            _check(
                "max_positions",
                snapshot["current_positions_count"] < snapshot["max_positions"],
                (
                    f"현재 보유 종목은 {snapshot['current_positions_count']}/"
                    f"{snapshot['max_positions']}개입니다."
                ),
                severity=(
                    "ok"
                    if snapshot["current_positions_count"] < snapshot["max_positions"]
                    else "block"
                ),
            ),
        ]


def _check(
    key: str,
    ok: bool,
    message: str,
    *,
    severity: str = "ok",
) -> dict[str, Any]:
    return {
        "key": key,
        "ok": bool(ok),
        "severity": severity,
        "message": message,
    }


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except Exception:
        return 0.0


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result
