from __future__ import annotations

"""Read-only outcome labeling for PR120 quant A/B observations.

This module deliberately has no imports from trading, risk, sizing, order, or
broker-submit services.  Its only external market dependency is a read-only
intraday-bar provider supplied by the caller.
"""

import json
import math
import time
from datetime import date, datetime, time as clock_time, timedelta
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from app.db.models import QuantABObservation, QuantABOutcome
from app.services.automation_profile_service import AutomationProfileService
from app.services.market_data_snapshot_service import MarketDataSnapshotService
from app.services.market_session_service import MarketSessionService

KST = ZoneInfo("Asia/Seoul")
TAKE_PROFIT_PCT = 5.0
STOP_LOSS_PCT = -2.0
LABEL_VERSION = "pr120-v1"
SLOT_PRICE_TOLERANCE_MINUTES = 5
DEFAULT_ANALYSIS_TIMES = ("09:10", "11:30", "13:30")


class QuantABOutcomeLabelError(ValueError):
    """Raised for an observation that cannot be safely labeled."""


class QuantABOutcomeLabelService:
    """Label only mature, read-only quant observations.

    ``market_data_snapshot_service`` can be a real
    :class:`MarketDataSnapshotService` or a deterministic fake in tests.  A
    per-service symbol/date cache prevents one cohort from issuing repeated
    KIS requests for the same intraday session.
    """

    def __init__(
        self,
        client=None,
        *,
        market_data_snapshot_service: MarketDataSnapshotService | None = None,
        market_data_service=None,
        session_service: MarketSessionService | None = None,
        automation_profile_service: AutomationProfileService | None = None,
        analysis_times: list[str] | tuple[str, ...] | None = None,
        now_provider=None,
        slot_price_tolerance_minutes: int = SLOT_PRICE_TOLERANCE_MINUTES,
    ) -> None:
        self.client = client
        self.market_data_snapshot_service = market_data_snapshot_service or market_data_service
        if self.market_data_snapshot_service is None and client is not None:
            self.market_data_snapshot_service = MarketDataSnapshotService(client)
        self.session_service = session_service or MarketSessionService()
        self.automation_profile_service = (
            automation_profile_service or AutomationProfileService()
        )
        self.configured_analysis_times = (
            tuple(str(value).strip() for value in analysis_times if str(value).strip())
            if analysis_times is not None
            else None
        )
        self.now_provider = now_provider or (lambda: datetime.now(KST))
        self.slot_price_tolerance_minutes = max(
            0, int(slot_price_tolerance_minutes or SLOT_PRICE_TOLERANCE_MINUTES)
        )
        self._intraday_cache: dict[tuple[str, date], tuple[list[dict[str, Any]], dict[str, Any]]] = {}
        self._stats = self._empty_stats()

    def clear_cache(self) -> None:
        self._intraday_cache.clear()

    def label_mature_observations(
        self,
        db,
        *,
        now: datetime | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Label pending observations whose third decision slot has passed."""
        started = time.perf_counter()
        self._stats = self._empty_stats()
        self.clear_cache()
        now_kst = _as_kst(now or self.now_provider())
        safe_limit = max(1, min(int(limit or 200), 1000))
        observations = (
            db.query(QuantABObservation)
            .filter(QuantABObservation.outcome_status == "pending")
            .order_by(QuantABObservation.observed_at.asc(), QuantABObservation.id.asc())
            .limit(safe_limit)
            .all()
        )
        self._stats["observations_scanned"] = len(observations)
        labeled: list[dict[str, Any]] = []
        for observation in observations:
            try:
                result = self.label_observation(db, observation, now=now_kst)
                labeled.append(result)
                status = result.get("outcome_status")
                if status == "complete":
                    self._stats["outcomes_labeled"] += 1
                elif status == "pending":
                    self._stats["outcomes_pending"] += 1
                else:
                    self._stats["outcomes_invalid"] += 1
            except Exception as exc:  # one bad row must not stop analytics batch
                db.rollback()
                result = self._mark_invalid(
                    db,
                    observation,
                    status="invalid_labeler_error",
                    reason=f"{exc.__class__.__name__}",
                )
                labeled.append(result)
                self._stats["outcomes_invalid"] += 1
        if labeled:
            db.commit()
        self._stats["elapsed_ms"] = round((time.perf_counter() - started) * 1000.0, 2)
        return {
            "status": "ok",
            "label_version": LABEL_VERSION,
            "now": now_kst.isoformat(),
            "items": labeled,
            "count": len(labeled),
            "performance": dict(self._stats),
            "safety": _safety(),
        }

    # Compatibility-friendly aliases for callers that use the shorter names.
    def label_pending_mature(self, db, **kwargs) -> dict[str, Any]:
        return self.label_mature_observations(db, **kwargs)

    def label_pending_observations(self, db, **kwargs) -> dict[str, Any]:
        return self.label_mature_observations(db, **kwargs)

    def label_mature(self, db, **kwargs) -> dict[str, Any]:
        return self.label_mature_observations(db, **kwargs)

    def label_observation(
        self,
        db,
        observation: QuantABObservation,
        *,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now_kst = _as_kst(now or self.now_provider())
        observed_at = _observation_timestamp(observation)
        if observed_at is None:
            return self._mark_invalid(
                db, observation, status="invalid_malformed_observation", reason="missing_observed_at"
            )
        entry_price = _finite(observation.current_price)
        quality = _observation_quality(observation)
        cohort_key = str(
            observation.experiment_cohort_key or observation.run_key or observation.observation_key
        )[:180]
        horizons = self.next_decision_slots(db, observed_at, observation=observation)
        if len(horizons) != 3:
            return self._mark_invalid(
                db, observation, status="invalid_malformed_observation", reason="three_horizons_unavailable"
            )
        base = {
            "observation_id": observation.id,
            "cohort_key": cohort_key,
            "symbol": str(observation.symbol or "").strip().upper(),
            "observed_at": observed_at,
            "entry_price": entry_price,
            "horizon_slot_1_at": horizons[0],
            "horizon_slot_2_at": horizons[1],
            "horizon_slot_3_at": horizons[2],
            "tp_pct": TAKE_PROFIT_PCT,
            "sl_pct": STOP_LOSS_PCT,
            "data_quality": quality,
        }
        if observation.outcome_status != "pending":
            return self._upsert(db, observation, {**base, "outcome_status": observation.outcome_status})
        if quality <= 0:
            return self._upsert(
                db,
                observation,
                {**base, "outcome_status": "invalid_data_quality"},
            )
        if entry_price is None or entry_price <= 0:
            return self._upsert(
                db,
                observation,
                {**base, "outcome_status": "invalid_missing_entry_price"},
            )
        if str(observation.market or "KR").upper() != "KR":
            return self._upsert(
                db,
                observation,
                {**base, "outcome_status": "invalid_session_mismatch"},
            )
        if now_kst < horizons[2]:
            return self._upsert(db, observation, {**base, "outcome_status": "pending"})

        try:
            bars = self._bars_between(
                str(observation.symbol or "").strip().upper(),
                observed_at,
                horizons[2],
                as_of=now_kst,
            )
        except Exception as exc:
            return self._mark_invalid(
                db,
                observation,
                status="invalid_market_data",
                reason=f"{exc.__class__.__name__}",
                base=base,
            )
        if not bars:
            return self._upsert(
                db,
                observation,
                {
                    **base,
                    "outcome_status": "invalid_market_data",
                    "simulated_exit_reason": "no_future_bars",
                },
            )

        slot_values: list[float | None] = []
        fallback_count = 0
        for horizon in horizons:
            selected = _price_at_or_before(
                bars,
                horizon,
                tolerance_minutes=self.slot_price_tolerance_minutes,
            )
            if selected is None:
                slot_values.append(None)
            else:
                slot_values.append(selected[0])
                fallback_count += int(selected[2])
        if any(value is None or value <= 0 for value in slot_values):
            return self._upsert(
                db,
                observation,
                {
                    **base,
                    "outcome_status": "invalid_missing_slot_price",
                    "data_quality": min(quality, 0.5) if fallback_count else quality,
                },
            )

        evaluated = evaluate_virtual_trade(
            bars,
            observed_at=observed_at,
            horizon_end=horizons[2],
            horizon_slots=horizons,
            entry_price=entry_price,
            take_profit_pct=TAKE_PROFIT_PCT,
            stop_loss_pct=STOP_LOSS_PCT,
        )
        if evaluated.get("first_barrier_hit") is None:
            evaluated["simulated_exit_price"] = slot_values[2]
            evaluated["simulated_return_pct"] = _return_pct(entry_price, slot_values[2])
        payload = {
            **base,
            "slot_1_price": slot_values[0],
            "slot_2_price": slot_values[1],
            "slot_3_price": slot_values[2],
            "return_next_slot_pct": _return_pct(entry_price, slot_values[0]),
            "return_second_slot_pct": _return_pct(entry_price, slot_values[1]),
            "return_third_slot_pct": _return_pct(entry_price, slot_values[2]),
            "data_quality": min(quality, 0.5) if fallback_count else quality,
            **evaluated,
            "outcome_status": "complete",
        }
        return self._upsert(db, observation, payload)

    def next_decision_slots(
        self,
        db,
        observed_at: datetime,
        *,
        observation: QuantABObservation | None = None,
    ) -> list[datetime]:
        """Return the next three configured slots across trading days."""
        observed = _as_kst(observed_at)
        configured = self._analysis_times(db, observed, observation=observation)
        parsed: list[clock_time] = []
        for value in configured:
            try:
                hour, minute = (int(part) for part in str(value).split(":", 1))
                parsed.append(clock_time(hour, minute))
            except (TypeError, ValueError):
                continue
        parsed = sorted(set(parsed))
        if not parsed:
            return []
        result: list[datetime] = []
        cursor = observed.date()
        while len(result) < 3 and len(result) < 20:
            if self._is_trading_day(cursor):
                for slot in parsed:
                    candidate = datetime.combine(cursor, slot, tzinfo=KST)
                    if candidate > observed:
                        result.append(candidate)
                        if len(result) == 3:
                            break
            cursor += timedelta(days=1)
        return result

    def _analysis_times(
        self,
        db,
        observed_at: datetime,
        *,
        observation: QuantABObservation | None,
    ) -> tuple[str, ...]:
        if self.configured_analysis_times:
            return self.configured_analysis_times
        try:
            schedule = self.automation_profile_service.selected_profile_schedule(
                db, now=observed_at
            )
            values = schedule.get("analysis_times") if isinstance(schedule, dict) else None
            if values:
                return tuple(str(value).strip() for value in values if str(value).strip())
            profile = (schedule or {}).get("profile") or {}
            settings = (profile or {}).get("effective_settings") or {}
            values = ((settings.get("entry") or {}).get("analysis_times"))
            if values:
                return tuple(str(value).strip() for value in values if str(value).strip())
        except Exception:
            pass
        # Legacy observations can outlive a deleted profile.  The PR119
        # default is used only as a migration fallback, never to override an
        # available active profile configuration.
        return DEFAULT_ANALYSIS_TIMES

    def _is_trading_day(self, value: date) -> bool:
        try:
            return bool(self.session_service.is_trading_day("KR", value))
        except Exception:
            return value.weekday() < 5

    def _bars_between(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        *,
        as_of: datetime | None = None,
    ) -> list[dict[str, Any]]:
        normalized_symbol = str(symbol or "").strip().upper()
        bars: list[dict[str, Any]] = []
        day = start.date()
        while day <= end.date():
            if self._is_trading_day(day):
                day_bars, _metadata = self._get_day_bars(
                    normalized_symbol, day, end=end, as_of=as_of
                )
                bars.extend(day_bars)
            day += timedelta(days=1)
        normalized: list[dict[str, Any]] = []
        for raw in bars:
            if not isinstance(raw, dict):
                continue
            timestamp = _bar_timestamp(raw)
            if timestamp is None or timestamp <= start or timestamp > end:
                continue
            high = _finite(raw.get("high"))
            low = _finite(raw.get("low"))
            close = _finite(raw.get("close"))
            if high is None or low is None or close is None or high <= 0 or low <= 0 or close <= 0:
                continue
            if low > high:
                continue
            normalized.append(
                {
                    "timestamp": timestamp,
                    "open": _finite(raw.get("open")),
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": _finite(raw.get("volume"), default=0.0),
                }
            )
        normalized.sort(key=lambda item: item["timestamp"])
        return normalized

    def _get_day_bars(
        self,
        symbol: str,
        session_date: date,
        *,
        end: datetime,
        as_of: datetime | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        key = (symbol, session_date)
        cached = self._intraday_cache.get(key)
        if cached is not None:
            self._stats["cache_hit_count"] += 1
            return cached
        self._stats["cache_miss_count"] += 1
        self._stats["kis_request_count"] += 1
        close_at = datetime.combine(session_date, clock_time(15, 30), tzinfo=KST)
        # Fetch the broadest read-only session snapshot once; no-lookahead is enforced again when bars are filtered by horizon.
        as_of = min(close_at, _as_kst(as_of or datetime.now(KST)))
        result: Any
        if self.market_data_snapshot_service is not None:
            getter = self.market_data_snapshot_service.get_intraday_bars
            try:
                result = getter(
                    symbol,
                    as_of=as_of,
                    limit=1200,
                    regular_open="09:00",
                    regular_close="15:30",
                )
            except TypeError:
                try:
                    result = getter(symbol, as_of=as_of, limit=1200)
                except TypeError:
                    result = getter(symbol)
        elif self.client is not None:
            getter = getattr(self.client, "get_domestic_intraday_bars", None)
            getter = getter or getattr(self.client, "get_intraday_bars", None)
            if getter is None:
                raise QuantABOutcomeLabelError("read_only_intraday_provider_unavailable")
            result = getter(symbol, as_of=as_of, limit=1200)
        else:
            result = ([], {"validation_status": "unavailable"})
        if isinstance(result, tuple):
            raw_bars, metadata = result
        else:
            raw_bars, metadata = result, {}
        day_bars = [
            raw for raw in (raw_bars or [])
            if isinstance(raw, dict) and _bar_timestamp(raw) is not None
            and _bar_timestamp(raw).date() == session_date
        ]
        metadata = dict(metadata or {})
        metadata.update({"symbol": symbol, "session_date": session_date.isoformat()})
        self._intraday_cache[key] = (day_bars, metadata)
        return day_bars, metadata

    def _upsert(self, db, observation, values: dict[str, Any]) -> dict[str, Any]:
        outcome = (
            db.query(QuantABOutcome)
            .filter(QuantABOutcome.observation_id == observation.id)
            .one_or_none()
        )
        if outcome is None:
            outcome = QuantABOutcome(
                observation_id=observation.id,
                cohort_key=str(values.get("cohort_key") or observation.run_key or "")[:180],
                symbol=str(values.get("symbol") or observation.symbol or "").upper(),
                label_version=LABEL_VERSION,
            )
            db.add(outcome)
        for key, value in values.items():
            if key == "observation_id" or not hasattr(outcome, key):
                continue
            setattr(outcome, key, value)
        outcome.label_version = LABEL_VERSION
        status = str(values.get("outcome_status") or outcome.outcome_status or "pending")
        observation.outcome_status = status
        db.flush()
        return _serialize_outcome(outcome, observation=observation)

    def _mark_invalid(
        self,
        db,
        observation,
        *,
        status: str,
        reason: str,
        base: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(base or {})
        payload.update(
            {
                "outcome_status": status,
                "simulated_exit_reason": reason,
                "tp_pct": TAKE_PROFIT_PCT,
                "sl_pct": STOP_LOSS_PCT,
            }
        )
        return self._upsert(db, observation, payload)

    @staticmethod
    def _empty_stats() -> dict[str, Any]:
        return {
            "observations_scanned": 0,
            "outcomes_labeled": 0,
            "outcomes_pending": 0,
            "outcomes_invalid": 0,
            "kis_request_count": 0,
            "cache_hit_count": 0,
            "cache_miss_count": 0,
            "elapsed_ms": 0.0,
        }


# Short alias used by some integrations.
QuantABOutcomeLabeler = QuantABOutcomeLabelService


def calculate_next_decision_slots(
    observed_at: datetime,
    *,
    analysis_times: list[str] | tuple[str, ...] = DEFAULT_ANALYSIS_TIMES,
    trading_day_fn=None,
) -> list[datetime]:
    """Pure helper for deterministic slot calculations and unit tests."""
    observed = _as_kst(observed_at)
    parsed: list[clock_time] = []
    for value in analysis_times:
        try:
            hour, minute = (int(part) for part in str(value).split(":", 1))
            parsed.append(clock_time(hour, minute))
        except (TypeError, ValueError):
            continue
    if not parsed:
        return []
    result: list[datetime] = []
    cursor = observed.date()
    is_trading_day = trading_day_fn or (lambda value: value.weekday() < 5)
    while len(result) < 3:
        if is_trading_day(cursor):
            for slot in sorted(set(parsed)):
                candidate = datetime.combine(cursor, slot, tzinfo=KST)
                if candidate > observed:
                    result.append(candidate)
                    if len(result) == 3:
                        break
        cursor += timedelta(days=1)
    return result


compute_next_decision_slots = calculate_next_decision_slots


def evaluate_virtual_trade(
    bars: list[dict[str, Any]],
    *,
    observed_at: datetime,
    horizon_end: datetime,
    horizon_slots: list[datetime] | tuple[datetime, ...],
    entry_price: float,
    take_profit_pct: float = TAKE_PROFIT_PCT,
    stop_loss_pct: float = STOP_LOSS_PCT,
) -> dict[str, Any]:
    """Evaluate minute OHLC bars with a conservative same-bar SL-first rule."""
    entry = float(entry_price)
    tp_price = entry * (1.0 + float(take_profit_pct) / 100.0)
    sl_price = entry * (1.0 + float(stop_loss_pct) / 100.0)
    observed = _as_kst(observed_at)
    horizon = _as_kst(horizon_end)
    rows = []
    for raw in bars or []:
        timestamp = _bar_timestamp(raw)
        high = _finite(raw.get("high")) if isinstance(raw, dict) else None
        low = _finite(raw.get("low")) if isinstance(raw, dict) else None
        if timestamp is None or high is None or low is None:
            continue
        if observed < timestamp <= horizon and low <= high:
            rows.append((timestamp, high, low))
    rows.sort(key=lambda item: item[0])
    tp_hit = False
    sl_hit = False
    tp_hit_at = None
    sl_hit_at = None
    first_barrier = None
    exit_reason = "horizon_end"
    exit_at = horizon
    exit_price = None
    exit_index = len(rows)
    for index, (timestamp, high, low) in enumerate(rows):
        hits_tp = high >= tp_price
        hits_sl = low <= sl_price
        if not hits_tp and not hits_sl:
            continue
        tp_hit = hits_tp
        sl_hit = hits_sl
        tp_hit_at = timestamp if hits_tp else None
        sl_hit_at = timestamp if hits_sl else None
        exit_at = timestamp
        exit_index = index + 1
        if hits_tp and hits_sl:
            first_barrier = "stop_loss"
            exit_reason = "stop_loss_same_bar_conservative"
            exit_price = sl_price
        elif hits_sl:
            first_barrier = "stop_loss"
            exit_reason = "stop_loss"
            exit_price = sl_price
        else:
            first_barrier = "take_profit"
            exit_reason = "take_profit"
            exit_price = tp_price
        break
    scan_rows = rows[:exit_index]
    highs = [value[1] for value in scan_rows]
    lows = [value[2] for value in scan_rows]
    if first_barrier is None:
        # The third slot close is the virtual horizon exit.  Its exact value is
        # supplied by the caller's slot-price selection.
        exit_price = None
    return {
        "max_favorable_excursion_pct": _round_pct((max(highs) / entry - 1.0) * 100.0) if highs else 0.0,
        "max_adverse_excursion_pct": _round_pct((min(lows) / entry - 1.0) * 100.0) if lows else 0.0,
        "tp_hit": bool(tp_hit),
        "sl_hit": bool(sl_hit),
        "tp_hit_at": tp_hit_at,
        "sl_hit_at": sl_hit_at,
        "first_barrier_hit": first_barrier,
        "simulated_exit_reason": exit_reason,
        "simulated_exit_at": exit_at,
        "simulated_exit_price": exit_price,
        "simulated_return_pct": (
            _round_pct(float(take_profit_pct))
            if first_barrier == "take_profit"
            else _round_pct(float(stop_loss_pct))
            if first_barrier == "stop_loss"
            else None
        ),
        "holding_minutes": round(max(0.0, (exit_at - observed).total_seconds() / 60.0), 6),
        "holding_decision_slots": sum(
            1 for slot in horizon_slots if _as_kst(slot) <= exit_at
        ),
    }


def _price_at_or_before(
    bars: list[dict[str, Any]],
    target: datetime,
    *,
    tolerance_minutes: int,
) -> tuple[float, datetime, bool] | None:
    target_kst = _as_kst(target)
    candidates: list[tuple[datetime, float]] = []
    for raw in bars or []:
        timestamp = _bar_timestamp(raw)
        close = _finite(raw.get("close")) if isinstance(raw, dict) else None
        if timestamp is None or close is None or close <= 0:
            continue
        if timestamp.replace(second=0, microsecond=0) == target_kst.replace(second=0, microsecond=0):
            candidates.append((timestamp, close))
    if candidates:
        timestamp, close = max(candidates, key=lambda item: item[0])
        return close, timestamp, False
    previous = []
    for raw in bars or []:
        timestamp = _bar_timestamp(raw)
        close = _finite(raw.get("close")) if isinstance(raw, dict) else None
        if timestamp is None or close is None or close <= 0 or timestamp > target_kst:
            continue
        delta = (target_kst - timestamp).total_seconds() / 60.0
        if 0 <= delta <= tolerance_minutes:
            previous.append((timestamp, close))
    if not previous:
        return None
    timestamp, close = max(previous, key=lambda item: item[0])
    return close, timestamp, True


def _observation_timestamp(observation: QuantABObservation) -> datetime | None:
    value = observation.observed_at
    if value is None:
        text = str(observation.decision_slot or "").strip()
        if text:
            try:
                value = datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None
    return _as_kst(value) if value is not None else None


def _observation_quality(observation: QuantABObservation) -> float:
    value = _finite(observation.data_quality_b)
    if value is None:
        return 0.0
    return max(0.0, min(1.0, value))


def _bar_timestamp(raw: Any) -> datetime | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("timestamp") or raw.get("datetime")
    if value is not None:
        if isinstance(value, datetime):
            return _as_kst(value)
        try:
            return _as_kst(datetime.fromisoformat(str(value).replace("Z", "+00:00")))
        except ValueError:
            pass
    session_date = str(raw.get("session_date") or "").strip()
    text = str(raw.get("time") or raw.get("source_time") or "").strip()
    if session_date and text:
        try:
            parts = text.split(":")
            return datetime.combine(
                date.fromisoformat(session_date),
                clock_time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0),
                tzinfo=KST,
            )
        except (TypeError, ValueError):
            return None
    return None


def _as_kst(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=KST)
    return value.astimezone(KST)


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if math.isfinite(parsed) else default


def _return_pct(entry: float, future: float | None) -> float | None:
    if future is None or entry <= 0:
        return None
    return _round_pct((float(future) / float(entry) - 1.0) * 100.0)


def _round_pct(value: float | None) -> float | None:
    return round(float(value), 6) if value is not None else None


def _serialize_outcome(outcome: QuantABOutcome, *, observation=None) -> dict[str, Any]:
    fields = (
        "id", "observation_id", "cohort_key", "symbol", "observed_at",
        "entry_price", "horizon_slot_1_at", "horizon_slot_2_at", "horizon_slot_3_at",
        "slot_1_price", "slot_2_price", "slot_3_price", "return_next_slot_pct",
        "return_second_slot_pct", "return_third_slot_pct", "max_favorable_excursion_pct",
        "max_adverse_excursion_pct", "tp_pct", "sl_pct", "tp_hit", "sl_hit", "tp_hit_at",
        "sl_hit_at", "first_barrier_hit", "simulated_exit_reason", "simulated_exit_at",
        "simulated_exit_price", "simulated_return_pct", "holding_minutes",
        "holding_decision_slots", "outcome_status", "data_quality", "label_version",
        "created_at", "updated_at",
    )
    payload = {field: _json_value(getattr(outcome, field, None)) for field in fields}
    if observation is not None:
        payload.update(
            {
                "trigger_source": observation.trigger_source,
                "decision_slot": observation.decision_slot,
                "a_rank": observation.a_rank,
                "a_quant_buy_score": observation.a_quant_buy_score,
                "a_final_score": observation.a_final_score,
                "b_rank_within_shadow_pool": observation.b_rank_within_shadow_pool,
                "b_entry_score": observation.b_entry_score,
                "b_future_up_score": observation.b_future_up_score,
                "b_future_down_score": observation.b_future_down_score,
                "confidence_b": observation.confidence_b,
                "data_quality_b": observation.data_quality_b,
                "authoritative_variant": observation.authoritative_variant,
                "shadow_variant": observation.shadow_variant,
                "experiment_cohort_key": observation.experiment_cohort_key,
            }
        )
    return payload


def _json_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _safety() -> dict[str, Any]:
    return {
        "analytics_only": True,
        "read_only_market_data": True,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "real_order_submitted": False,
        "risk_engine_called": False,
        "order_service_called": False,
    }
