from __future__ import annotations

from datetime import timedelta

from app.services.kis_stop_loss_aware_feature_service import MINUTE, minute_bars, number, timestamp

LABEL_VERSION = "stop-loss-path-v1"


def _return(price, entry):
    return round(price / entry - 1, 8)


def evaluate_horizon(rows, *, decision, minutes, session_close, now, entry, sl, tp,
                     monitoring_checks=(), cost_bps=0):
    horizon = decision + timedelta(minutes=minutes)
    result = {"configured_minutes": minutes, "horizon_at": horizon.isoformat(), "label_version": LABEL_VERSION}
    if horizon > session_close:
        return {**result, "status": "insufficient_regular_session"}
    if now < horizon:
        return {**result, "status": "pending"}

    # An entry inside a minute cannot use that candle's pre-entry high or low.
    start = decision.replace(second=0, microsecond=0)
    if start < decision:
        start += MINUTE
    bars = minute_bars(rows, start, horizon)
    expected = int((horizon - start) / MINUTE)
    if not expected or len(bars) != expected:
        return {**result, "status": "incomplete_path", "completed_minutes": len(bars),
                "expected_minutes": expected}
    first = None
    sl_at = tp_at = gap_at = None
    conservative_price = None
    recovered = False
    # A scheduled check samples a price. This approximation uses the last
    # completed minute close and records the convention next to the exit.
    monitor_prices = {}
    for check in monitoring_checks:
        label = check.replace(second=0, microsecond=0) - MINUTE
        if decision < check <= horizon and label in bars:
            monitor_prices[check] = bars[label]["close"]
    monitored = None
    for check, price in sorted(monitor_prices.items()):
        side = "sl" if sl is not None and price <= sl else "tp" if tp is not None and price >= tp else None
        if side:
            monitored = {"barrier": side, "at": check.isoformat(), "price": price,
                         "price_reference": "prior_completed_minute_close"}
            break
    for at, bar in bars.items():
        if sl_at and bar["high"] >= entry:
            recovered = True
        hits_sl = sl is not None and bar["low"] <= sl
        hits_tp = tp is not None and bar["high"] >= tp
        if hits_sl and sl_at is None:
            sl_at = at
            gap_at = at if bar["open"] < sl else None
        if hits_tp and tp_at is None:
            tp_at = at
        if first is None and (hits_sl or hits_tp):
            open_sl = hits_sl and bar["open"] <= sl
            open_tp = hits_tp and bar["open"] >= tp
            if open_sl or open_tp:
                first = "sl_first" if open_sl else "tp_first"
                conservative_price = bar["open"]
            elif hits_sl and hits_tp:
                first, conservative_price = "ambiguous_same_bar", sl
            else:
                first, conservative_price = ("sl_first", sl) if hits_sl else ("tp_first", tp)
    close = next(reversed(bars.values()))["close"]
    cost = max(0, cost_bps) / 10_000
    return {
        **result, "status": "complete",
        "first_intrabar_barrier": first or "neither",
        "sl_first_sensitivity": ("sl_first" if first == "ambiguous_same_bar" else first or "neither"),
        "stop_loss_survived": sl_at is None if sl is not None else None,
        "time_to_sl_minutes": (sl_at - decision) / MINUTE if sl_at else None,
        "time_to_tp_minutes": (tp_at - decision) / MINUTE if tp_at else None,
        "gap_through_stop": gap_at is not None if sl is not None else None,
        "recovered_above_entry_after_sl": recovered if sl_at else None,
        "horizon_return": _return(close, entry),
        "mfe": max(0, _return(max(b["high"] for b in bars.values()), entry)),
        "mae": min(0, _return(min(b["low"] for b in bars.values()), entry)),
        "conservative_intrabar_net_return": round(_return(conservative_price or close, entry) - cost, 8),
        "estimated_cost_bps": cost_bps,
        "simulated_monitor_exit": monitored,
        "simulated_monitor_net_return": round(_return(monitored["price"], entry) - cost, 8) if monitored else None,
        "actual_broker_execution": None,
    }


def outcome_checkpoints(analysis, decision, now, bars, cost_bps):
    schedule = analysis["effective_schedule_snapshot"]
    entry = number(analysis.get("estimated_entry_price"))
    session_close = timestamp(schedule.get("session_close"))
    if not session_close or not schedule.get("regular_session"):
        return {"status": "outside_regular_session", "label_version": LABEL_VERSION}
    if not entry or entry <= 0:
        return {"status": "missing_entry_reference", "label_version": LABEL_VERSION}
    checks = [at for raw in schedule.get("position_management_checkpoints", []) if (at := timestamp(raw))]
    if schedule.get("stop_loss_monitoring_mode") == "per_position_30m_due_check":
        checks = [decision + timedelta(minutes=minutes) for minutes in range(30, 121, 30)]
    values = {
        horizon: evaluate_horizon(
            bars, decision=decision, minutes=schedule[f"gpt_{horizon}_horizon_minutes"],
            session_close=session_close, now=now, entry=entry,
            sl=analysis.get("estimated_stop_loss_price"), tp=analysis.get("estimated_take_profit_price"),
            monitoring_checks=checks, cost_bps=cost_bps,
        )
        for horizon in ("short", "long")
    }
    return {"status": "pending" if any(item["status"] == "pending" for item in values.values())
            else "labeled", "label_version": LABEL_VERSION, **values}
