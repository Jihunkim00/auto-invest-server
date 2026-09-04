from __future__ import annotations

"""Descriptive A/B evaluation over immutable observations and mutable outcomes."""

from datetime import date, datetime, time as clock_time
from statistics import median
from typing import Any
from zoneinfo import ZoneInfo

from app.db.models import QuantABObservation, QuantABOutcome


class QuantABEvaluationService:
    """Build read-only cohort comparisons and B score calibration buckets."""

    def recent(
        self,
        db,
        *,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        min_data_quality: float = 0.0,
        trigger_source: str | None = None,
        decision_slot: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        records = self._records(
            db,
            start_date=start_date,
            end_date=end_date,
            min_data_quality=min_data_quality,
            trigger_source=trigger_source,
            decision_slot=decision_slot,
            include_pending=True,
            limit=limit,
        )
        return {
            "status": "ok",
            "count": len(records),
            "items": [self._serialize_record(observation, outcome) for observation, outcome in records],
            "filters": _filters(
                start_date=start_date,
                end_date=end_date,
                min_data_quality=min_data_quality,
                trigger_source=trigger_source,
                decision_slot=decision_slot,
            ),
            "safety": _safety(),
        }

    def summary(
        self,
        db,
        *,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        min_data_quality: float = 0.0,
        trigger_source: str | None = None,
        decision_slot: str | None = None,
    ) -> dict[str, Any]:
        records = self._records(
            db,
            start_date=start_date,
            end_date=end_date,
            min_data_quality=min_data_quality,
            trigger_source=trigger_source,
            decision_slot=decision_slot,
            include_pending=False,
            limit=10000,
        )
        comparisons = self._comparisons(records)
        a_values = [item["a_outcome"] for item in comparisons]
        b_values = [item["b_outcome"] for item in comparisons]
        b_wins = sum(1 for item in comparisons if item["winner"] == "B")
        a_wins = sum(1 for item in comparisons if item["winner"] == "A")
        ties = sum(1 for item in comparisons if item["winner"] == "tie")
        evaluated = len(comparisons)
        return {
            "status": "ok",
            "label_version": "pr120-v1",
            "filters": _filters(
                start_date=start_date,
                end_date=end_date,
                min_data_quality=min_data_quality,
                trigger_source=trigger_source,
                decision_slot=decision_slot,
            ),
            "evaluated_cohort_count": evaluated,
            "same_candidate_count": sum(1 for item in comparisons if item["same_candidate"]),
            "different_candidate_count": sum(1 for item in comparisons if not item["same_candidate"]),
            "a": _metric_summary(a_values),
            "b": _metric_summary(b_values),
            "difference": {
                "avg_return_b_minus_a_pct": _difference_average(a_values, b_values),
                "b_wins_count": b_wins,
                "b_wins_rate": _rate(b_wins, evaluated),
                "a_wins_count": a_wins,
                "a_wins_rate": _rate(a_wins, evaluated),
                "ties": ties,
                "tie_rate": _rate(ties, evaluated),
            },
            "comparisons": [item["payload"] for item in comparisons],
            "safety": _safety(),
        }

    def score_buckets(
        self,
        db,
        *,
        start_date: str | date | None = None,
        end_date: str | date | None = None,
        min_data_quality: float = 0.0,
        trigger_source: str | None = None,
        decision_slot: str | None = None,
    ) -> dict[str, Any]:
        records = self._records(
            db,
            start_date=start_date,
            end_date=end_date,
            min_data_quality=min_data_quality,
            trigger_source=trigger_source,
            decision_slot=decision_slot,
            include_pending=False,
            limit=10000,
        )
        buckets = {
            label: [] for label, _lower, _upper in _BUCKETS
        }
        for observation, outcome in records:
            score = _finite(observation.b_entry_score)
            if score is None:
                continue
            bucket = _bucket_for(score)
            if bucket is not None:
                buckets[bucket[0]].append((observation, outcome))
        items = []
        for label, lower, upper in _BUCKETS:
            values = buckets[label]
            returns = [float(outcome.simulated_return_pct) for _obs, outcome in values if _finite(outcome.simulated_return_pct) is not None]
            items.append(
                {
                    "bucket": label,
                    "min_score": lower,
                    "max_score": upper,
                    "sample_count": len(values),
                    "avg_simulated_return_pct": _average(returns),
                    "median_simulated_return_pct": _median(returns),
                    "tp_rate": _rate(sum(bool(outcome.tp_hit) for _obs, outcome in values), len(values)),
                    "sl_rate": _rate(sum(bool(outcome.sl_hit) for _obs, outcome in values), len(values)),
                    "avg_mfe_pct": _average([outcome.max_favorable_excursion_pct for _obs, outcome in values]),
                    "avg_mae_pct": _average([outcome.max_adverse_excursion_pct for _obs, outcome in values]),
                }
            )
        return {
            "status": "ok",
            "score": "b_entry_score",
            "bucket_count": len(items),
            "items": items,
            "total_sample_count": sum(item["sample_count"] for item in items),
            "filters": _filters(
                start_date=start_date,
                end_date=end_date,
                min_data_quality=min_data_quality,
                trigger_source=trigger_source,
                decision_slot=decision_slot,
            ),
            "safety": _safety(),
        }

    # Readability aliases used by API adapters and scripts.
    evaluation_summary = summary
    get_summary = summary
    get_score_buckets = score_buckets

    def _records(
        self,
        db,
        *,
        start_date: str | date | None,
        end_date: str | date | None,
        min_data_quality: float,
        trigger_source: str | None,
        decision_slot: str | None,
        include_pending: bool,
        limit: int,
    ) -> list[tuple[QuantABObservation, QuantABOutcome]]:
        query = (
            db.query(QuantABObservation, QuantABOutcome)
            .join(
                QuantABOutcome,
                QuantABOutcome.observation_id == QuantABObservation.id,
            )
            .order_by(QuantABObservation.observed_at.desc(), QuantABOutcome.id.desc())
            .limit(max(1, min(int(limit or 100), 20000)))
        )
        rows = query.all()
        start = _date_value(start_date)
        end = _date_value(end_date)
        min_quality = max(0.0, float(min_data_quality or 0.0))
        filtered = []
        for observation, outcome in rows:
            observed = _aware(observation.observed_at)
            if start is not None and (observed is None or observed.date() < start):
                continue
            if end is not None and (observed is None or observed.date() > end):
                continue
            if trigger_source and observation.trigger_source != trigger_source:
                continue
            if decision_slot and observation.decision_slot != decision_slot:
                continue
            if _finite(outcome.data_quality, default=0.0) < min_quality:
                continue
            if not include_pending and outcome.outcome_status != "complete":
                continue
            filtered.append((observation, outcome))
        return filtered

    def _comparisons(self, records):
        cohorts: dict[str, list[tuple[QuantABObservation, QuantABOutcome]]] = {}
        for observation, outcome in records:
            key = str(
                outcome.cohort_key
                or observation.experiment_cohort_key
                or observation.run_key
                or observation.observation_key
            )
            cohorts.setdefault(key, []).append((observation, outcome))
        comparisons = []
        for cohort_key, rows in cohorts.items():
            a_rows = [
                pair for pair in rows
                if pair[0].a_rank == 1 and pair[1].outcome_status == "complete"
            ]
            b_rows = [
                pair for pair in rows
                if pair[0].b_rank_within_shadow_pool == 1
                and pair[1].outcome_status == "complete"
            ]
            if not a_rows or not b_rows:
                continue
            a_observation, a_outcome = sorted(a_rows, key=lambda pair: pair[0].id)[0]
            b_observation, b_outcome = sorted(b_rows, key=lambda pair: pair[0].id)[0]
            a_return = _finite(a_outcome.simulated_return_pct)
            b_return = _finite(b_outcome.simulated_return_pct)
            if a_return is None or b_return is None:
                continue
            delta = b_return - a_return
            winner = "B" if delta > 1e-9 else "A" if delta < -1e-9 else "tie"
            payload = {
                "cohort_key": cohort_key,
                "a_winner_symbol": a_observation.symbol,
                "b_winner_symbol": b_observation.symbol,
                "same_winner": a_observation.symbol == b_observation.symbol,
                "a_simulated_return_pct": a_return,
                "b_simulated_return_pct": b_return,
                "return_diff_b_minus_a_pct": round(delta, 6),
                "winner": winner,
                "a_tp_hit": bool(a_outcome.tp_hit),
                "b_tp_hit": bool(b_outcome.tp_hit),
                "a_sl_hit": bool(a_outcome.sl_hit),
                "b_sl_hit": bool(b_outcome.sl_hit),
                "a_observation_id": a_observation.id,
                "b_observation_id": b_observation.id,
            }
            comparisons.append(
                {
                    "payload": payload,
                    "same_candidate": payload["same_winner"],
                    "winner": winner,
                    "a_outcome": a_outcome,
                    "b_outcome": b_outcome,
                }
            )
        return comparisons

    @staticmethod
    def _serialize_record(observation, outcome) -> dict[str, Any]:
        fields = (
            "id", "observation_id", "cohort_key", "symbol", "observed_at", "entry_price",
            "horizon_slot_1_at", "horizon_slot_2_at", "horizon_slot_3_at", "slot_1_price",
            "slot_2_price", "slot_3_price", "return_next_slot_pct", "return_second_slot_pct",
            "return_third_slot_pct", "max_favorable_excursion_pct", "max_adverse_excursion_pct",
            "tp_pct", "sl_pct", "tp_hit", "sl_hit", "tp_hit_at", "sl_hit_at",
            "first_barrier_hit", "simulated_exit_reason", "simulated_exit_at",
            "simulated_exit_price", "simulated_return_pct", "holding_minutes",
            "holding_decision_slots", "outcome_status", "data_quality", "label_version",
            "created_at", "updated_at",
        )
        payload = {
            "outcome": {
                field: _json_value(getattr(outcome, field, None)) for field in fields
            },
            "observation": {
                "id": observation.id,
                "observation_key": observation.observation_key,
                "run_key": observation.run_key,
                "experiment_cohort_key": observation.experiment_cohort_key,
                "trade_run_id": observation.trade_run_id,
                "trigger_source": observation.trigger_source,
                "symbol": observation.symbol,
                "observed_at": _json_value(observation.observed_at),
                "decision_slot": observation.decision_slot,
                "a_rank": observation.a_rank,
                "a_quant_buy_score": observation.a_quant_buy_score,
                "a_final_score": observation.a_final_score,
                "b_rank_within_shadow_pool": observation.b_rank_within_shadow_pool,
                "b_entry_score": observation.b_entry_score,
                "entry_score_b": observation.b_entry_score,
                "b_future_up_score": observation.b_future_up_score,
                "future_up_score_b": observation.b_future_up_score,
                "b_future_down_score": observation.b_future_down_score,
                "future_down_score_b": observation.b_future_down_score,
                "confidence_b": observation.confidence_b,
                "data_quality_b": observation.data_quality_b,
                "authoritative_variant": observation.authoritative_variant,
                "shadow_variant": observation.shadow_variant,
                "outcome_status": observation.outcome_status,
            },
        }
        payload.update(payload["outcome"])
        payload["confidence_b"] = observation.confidence_b
        return payload


# Alternative name retained for callers that use the report terminology.
QuantABReportService = QuantABEvaluationService

_BUCKETS = (
    ("0-39", 0.0, 39.999999),
    ("40-49", 40.0, 49.999999),
    ("50-59", 50.0, 59.999999),
    ("60-69", 60.0, 69.999999),
    ("70-79", 70.0, 79.999999),
    ("80-100", 80.0, 100.0),
)


def _bucket_for(score: float):
    for bucket in _BUCKETS:
        if bucket[1] <= score <= bucket[2]:
            return bucket
    return None


def _metric_summary(values) -> dict[str, Any]:
    returns = [_finite(value.simulated_return_pct) for value in values]
    returns = [value for value in returns if value is not None]
    return {
        "sample_count": len(values),
        "avg_return": _average(returns),
        "avg_simulated_return_pct": _average(returns),
        "median_return": _median(returns),
        "median_simulated_return_pct": _median(returns),
        "tp_rate": _rate(sum(bool(value.tp_hit) for value in values), len(values)),
        "sl_rate": _rate(sum(bool(value.sl_hit) for value in values), len(values)),
        "avg_mfe": _average([value.max_favorable_excursion_pct for value in values]),
        "avg_mfe_pct": _average([value.max_favorable_excursion_pct for value in values]),
        "avg_mae": _average([value.max_adverse_excursion_pct for value in values]),
        "avg_mae_pct": _average([value.max_adverse_excursion_pct for value in values]),
    }


def _difference_average(a_values, b_values):
    differences = []
    for a, b in zip(a_values, b_values):
        av = _finite(a.simulated_return_pct)
        bv = _finite(b.simulated_return_pct)
        if av is not None and bv is not None:
            differences.append(bv - av)
    return _average(differences)


def _average(values) -> float | None:
    numbers = [_finite(value) for value in values]
    numbers = [value for value in numbers if value is not None]
    return round(sum(numbers) / len(numbers), 6) if numbers else None


def _median(values) -> float | None:
    numbers = [_finite(value) for value in values]
    numbers = [value for value in numbers if value is not None]
    return round(float(median(numbers)), 6) if numbers else None


def _rate(count: int, total: int) -> float:
    return round(count / total, 6) if total else 0.0


def _finite(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if result == result and abs(result) != float("inf") else default


def _date_value(value: str | date | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=ZoneInfo("Asia/Seoul"))


def _json_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, datetime) else value


def _filters(**kwargs) -> dict[str, Any]:
    values = dict(kwargs)
    for key in ("start_date", "end_date"):
        if isinstance(values.get(key), date):
            values[key] = values[key].isoformat()
    return values


def _safety() -> dict[str, Any]:
    return {
        "analytics_only": True,
        "read_only": True,
        "broker_submit_called": False,
        "manual_submit_called": False,
        "real_order_submitted": False,
        "risk_engine_called": False,
        "order_service_called": False,
    }
