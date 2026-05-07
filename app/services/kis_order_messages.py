from __future__ import annotations

from typing import Any


def concise_order_block(reason_codes: list[str], *, detail_source: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return one prioritized, user-facing block reason/message."""
    reasons = [str(reason) for reason in reason_codes if reason]
    source = detail_source or {}

    def has(*codes: str) -> bool:
        return any(code in reasons for code in codes)

    def session_detail() -> dict[str, Any]:
        session = source.get("market_session") if isinstance(source.get("market_session"), dict) else source
        return {
            "market_open": session.get("is_market_open"),
            "near_close": session.get("is_near_close"),
            "no_new_entry_after": session.get("no_new_entry_after"),
            "regular_close": session.get("regular_close"),
            "effective_close": session.get("effective_close"),
            "closure_reason": session.get("closure_reason"),
            "closure_name": session.get("closure_name"),
        }

    if has("kill_switch_enabled"):
        return {"primary_block_reason": "kill_switch_enabled", "message": "Kill switch is ON."}
    if has("dry_run_must_be_false"):
        return {
            "primary_block_reason": "dry_run_must_be_false",
            "message": "Backend dry-run is ON, so live KIS orders are blocked.",
        }
    if has("kis_enabled_false", "kis_disabled"):
        return {"primary_block_reason": "kis_disabled", "message": "KIS trading is disabled."}
    if has("kis_real_order_enabled_false", "kis_real_order_disabled"):
        return {
            "primary_block_reason": "kis_real_order_disabled",
            "message": "KIS real-order submission is disabled.",
        }
    if has("recent_dry_run_validation_missing"):
        return {
            "primary_block_reason": "recent_dry_run_validation_missing",
            "message": "A successful validation within the last 5 minutes is required.",
        }
    if has("confirm_live_required", "confirmation_required", "manual_confirmation_missing_or_invalid"):
        return {"primary_block_reason": "confirmation_required", "message": "Live confirmation is required."}
    if has("after_no_new_entry_time", "buy_entry_not_allowed_now"):
        detail = session_detail()
        cutoff = detail.get("no_new_entry_after")
        return {
            "primary_block_reason": "buy_entry_not_allowed_now",
            "message": f"New buy entries are blocked after {cutoff}." if cutoff else "New buy entries are blocked now.",
            "detail": detail,
        }
    if has("near_close"):
        return {
            "primary_block_reason": "near_close",
            "message": "Orders are blocked near market close.",
            "detail": session_detail(),
        }
    if has("market_closed", "today_is_holiday"):
        detail = session_detail()
        closure_name = detail.get("closure_name")
        if has("today_is_holiday") and closure_name:
            message = f"Market is closed for {closure_name}."
        else:
            message = "Market is closed."
        return {"primary_block_reason": "market_closed", "message": message, "detail": detail}
    if has("insufficient_cash", "available_cash_unavailable"):
        return {"primary_block_reason": "insufficient_cash", "message": "Insufficient available cash."}
    if has("qty_must_be_positive_integer", "symbol_must_be_6_digit_kr_code", "invalid_kr_symbol", "market_must_be_KR", "side_must_be_buy_or_sell", "order_type_must_be_market", "current_price_unavailable"):
        return {"primary_block_reason": "invalid_order", "message": "Invalid quantity or symbol."}

    primary = reasons[0] if reasons else "risk_block"
    return {"primary_block_reason": primary, "message": "Order blocked by risk controls."}
