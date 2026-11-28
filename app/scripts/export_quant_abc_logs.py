"""Export persisted ABC observations and outcomes without API calls or DB writes.

Examples:
    python -m app.scripts.export_quant_abc_logs --month 2026-10 --format both
    python -m app.scripts.export_quant_abc_logs --database auto_invest.db --official-only

All observations are included by default, including partial/pending records. Dates
are inclusive Korea dates (naive persisted timestamps are interpreted as KST).
Outcome columns keep their names except collisions with observation columns, which
receive an outcome_ prefix; the label status is named outcome_label_status.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import sys
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from statistics import fmean, median
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import Float, MetaData, Table, create_engine, inspect, literal, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

KST = ZoneInfo("Asia/Seoul")
FRONT_COLUMNS = (
    "observed_at", "decision_slot", "run_key", "experiment_cohort_key",
    "trigger_source", "symbol", "a_rank", "a_quant_buy_score", "c_reversal_score",
    "a_gpt_buy_score", "a_final_score", "gpt_selected_by_a", "gpt_score_available",
    "selected_by_a", "selected_by_b_shadow", "selected_by_c_shadow",
    "entry_funnel_pass", "official_quality",
    "market_regime_snapshot_id",
    "market_regime_calculation_date",
    "market_regime_calculated_at",
    "market_regime_stage",
    "market_regime_key",
    "market_regime_label",
    "market_regime_status",
    "market_regime_confirmed",
    "market_regime_score",
    "market_regime_kospi_score",
    "market_regime_nasdaq_score",
    "market_regime_score_change_3w",
    "market_regime_new_bullish_reversal",
    "market_regime_new_bearish_reversal",
    "market_regime_policy_version",
    "base_c_min",
    "shadow_regime_c_min",
    "shadow_regime_size_multiplier",
    "shadow_regime_policy_active",
    "shadow_regime_policy_reason",
    "base_c_pass",
    "shadow_regime_c_pass",
    "base_entry_funnel_pass",
    "shadow_regime_entry_funnel_pass",
    "shadow_regime_notional",
)
DETAIL_COLUMNS = (
    "id", "observation_key", "provider", "market", "gate_level", "trade_run_id",
    "authoritative_variant", "shadow_variant", "current_price", "a_quant_sell_score",
    "b_rank_within_shadow_pool", "b_entry_score", "b_future_up_score", "b_future_down_score",
    "b_entry_timing_score", "b_trend_context_score", "b_momentum_score", "b_volume_score",
    "b_volatility_fit_score", "confidence_b", "trend_state_b", "direction_b",
    "c_rank_within_shadow_pool", "c_oversold_score", "c_macd_reversal_score",
    "c_price_stabilization_score", "c_intraday_reversal_score", "c_volume_confirmation_score",
    "c_downtrend_continuation_risk", "confidence_c", "reversal_state_c", "direction_c",
    "data_quality_b", "data_quality_c", "indicator_snapshot_json",
    "intraday_snapshot_metadata_json", "b_reason", "b_notes_json", "c_reason", "c_notes_json",
    "outcome_status", "created_at",
)


def create_read_only_engine(database: Path):
    """Use SQLite's filesystem read-only mode and also reject SQL writes."""
    database = database.expanduser().resolve()
    if not database.is_file():
        raise ValueError(f"Database file does not exist: {database}")
    uri = database.as_uri() + "?mode=ro"

    def connect():
        connection = sqlite3.connect(uri, uri=True)
        connection.execute("PRAGMA query_only = ON")
        return connection

    return create_engine("sqlite://", creator=connect, future=True)


def _database_path(database: str | None) -> Path:
    if database is not None:
        return Path(database)
    # Reuse the app's .env/environment configuration without importing its engine
    # or startup/migrations (which can create directories or mutate the database).
    from app.config import get_settings

    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        raise ValueError("This exporter requires a file-backed SQLite DATABASE_URL or --database PATH")
    return Path(url.database)


def _json_object(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (ValueError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _finite(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if math.isfinite(number) else None


def official_quality(row: dict[str, Any]) -> bool:
    """Reconstruct full B/C analysis quality using existing preview criteria.

    _run_shadow_b requires quality=1 and >=2 bars in 15m/30m/60m;
    _run_shadow_c requires quality=1 and >=2 bars in 15m/30m. Both use the
    validated shared intraday snapshot. Missing evidence stays non-official.
    """
    metadata = _json_object(row.get("intraday_snapshot_metadata_json"))
    if metadata.get("validation_status") != "ok":
        return False
    snapshot = _json_object(row.get("indicator_snapshot_json"))
    present = False
    for variant, score_field, timeframes in (
        ("b", "b_entry_score", ("15m", "30m", "60m")),
        ("c", "c_reversal_score", ("15m", "30m")),
    ):
        quality = _finite(row.get(f"data_quality_{variant}"))
        if row.get(score_field) is None and quality in (None, 0.0):
            continue
        present = True
        if quality is None or quality < 1.0 or _finite(row.get(score_field)) is None:
            return False
        indicators = _json_object(snapshot.get(variant))
        for timeframe in timeframes:
            count = _finite(_json_object(indicators.get(timeframe)).get("bar_count"))
            if count is None or count < 2:
                return False
    return present


def _observed_date(row: dict[str, Any]) -> date | None:
    value = row.get("observed_at") or row.get("decision_slot")
    if value is None:
        return None
    try:
        timestamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=KST)
    return timestamp.astimezone(KST).date()


def _json_value(value: Any) -> Any:
    return value.isoformat() if isinstance(value, (datetime, date)) else value


def read_rows(connection, args) -> tuple[list[str], list[dict[str, Any]]]:
    """One LEFT JOIN; one exported row for each observation, even without a label."""
    tables = set(inspect(connection).get_table_names())
    if "quant_ab_observations" not in tables:
        raise ValueError("quant_ab_observations table missing; run DB migration/init first")
    metadata = MetaData()
    observation = Table("quant_ab_observations", metadata, autoload_with=connection)
    columns = list(observation.c)
    if "a_gpt_buy_score" not in observation.c:
        print(
            "a_gpt_buy_score column missing; exporting NULL. Run DB migration/init first "
            "to persist new GPT scores.", file=sys.stderr,
        )
        columns.append(literal(None, type_=Float).label("a_gpt_buy_score"))
    source = observation
    outcome_names = []
    if "quant_ab_outcomes" in tables:
        outcome = Table("quant_ab_outcomes", metadata, autoload_with=connection)
        source = observation.outerjoin(outcome, outcome.c.observation_id == observation.c.id)
        for column in outcome.c:
            name = column.name
            if name == "outcome_status":
                name = "outcome_label_status"
            elif name in observation.c:
                name = "outcome_" + name
            columns.append(column.label(name))
            outcome_names.append(name)
    include_v2 = "kis_gpt_shadow_observations" in tables
    v2_columns = ("gpt_v2_export_version", "gpt_v2_status", "gpt_v2_analysis_json",
                  "gpt_v2_outcome_json", "gpt_v2_v1_performance_json") if include_v2 else ()
    if include_v2:
        shadow = Table("kis_gpt_shadow_observations", metadata, autoload_with=connection)
        source = source.outerjoin(shadow, shadow.c.observation_key == observation.c.observation_key)
        columns.extend((
            shadow.c.status.label("gpt_v2_status"),
            shadow.c.analysis_json.label("gpt_v2_analysis_json"),
            shadow.c.outcome_json.label("gpt_v2_outcome_json"),
        ))
    query = select(*columns).select_from(source).order_by(observation.c.observed_at, observation.c.id)
    if args.trigger_source:
        query = query.where(observation.c.trigger_source == args.trigger_source)
    # SQLite ALTER TABLE appends columns; CSV order must not depend on migration history.
    known_columns = (*FRONT_COLUMNS, *DETAIL_COLUMNS)
    extra_columns = sorted(set(observation.c.keys()) - set(known_columns))
    fieldnames = list(dict.fromkeys((*known_columns, *extra_columns, *sorted(outcome_names), *v2_columns)))
    rows = []
    for record in connection.execute(query).mappings():
        row = dict(record)
        observed = _observed_date(row)
        if args.from_date and (observed is None or observed < args.from_date):
            continue
        if args.to_date and (observed is None or observed > args.to_date):
            continue
        row["gpt_score_available"] = row.get("a_gpt_buy_score") is not None
        row["official_quality"] = official_quality(row)
        scores = [_finite(row.get(field)) for field in
                  ("a_rank", "c_reversal_score", "a_gpt_buy_score", "a_final_score")]
        row["entry_funnel_pass"] = bool(
            all(score is not None for score in scores)
            and scores[0] <= args.a_rank_max
            and scores[1] >= args.c_min_score
            and scores[2] >= args.gpt_min_score
            and scores[3] >= args.final_min_score
        )
        if args.official_only and not row["official_quality"]:
            continue
        if args.passed_only and not row["entry_funnel_pass"]:
            continue
        if include_v2:
            metadata_payload = _json_object(row.get("intraday_snapshot_metadata_json"))
            v2_manifest = metadata_payload.get("gpt_shadow") or {}
            if row.get("gpt_v2_status") is None and v2_manifest:
                status = v2_manifest.get("status")
                row["gpt_v2_status"] = status
                row["gpt_v2_analysis_json"] = json.dumps({
                    "snapshot_id": v2_manifest.get("run_key"),
                    "gpt_v2_status": status,
                    "effective_schedule_snapshot": v2_manifest.get("effective_schedule_snapshot"),
                }, ensure_ascii=False)
            if row.get("gpt_v2_status") is not None:
                row["gpt_v2_export_version"] = "pr144-v1"
            performance = metadata_payload.get("gpt_shadow_v1_performance")
            if performance:
                row["gpt_v2_v1_performance_json"] = json.dumps(performance)
        rows.append({name: _json_value(row.get(name)) for name in fieldnames})
    return fieldnames, rows


def _average(rows, key):
    values = [value for row in rows if (value := _finite(row.get(key))) is not None]
    return {"n": len(values), "mean": fmean(values) if values else None}


def _rate(rows, key, expected):
    values = [row[key] for row in rows if row.get(key) is not None]
    return {"n": len(values), "rate": sum(value == expected for value in values) / len(values) if values else None}


def _outcome_metrics(rows, period):
    complete = [item for row in rows if (item := row["outcome"].get(period) or {}).get("status") == "complete"]
    return {
        "candidates": len(rows), "complete_paths": len(complete),
        "stop_survival": _rate(complete, "stop_loss_survived", True),
        "tp_first": _rate(complete, "first_intrabar_barrier", "tp_first"),
        "sl_first": _rate(complete, "first_intrabar_barrier", "sl_first"),
        "sl_first_sensitivity": _rate(complete, "sl_first_sensitivity", "sl_first"),
        "same_bar_ambiguity": _rate(complete, "first_intrabar_barrier", "ambiguous_same_bar"),
        "recovery_after_sl": _rate(complete, "recovered_above_entry_after_sl", True),
        "mfe": _average(complete, "mfe"), "mae": _average(complete, "mae"),
        "horizon_return": _average(complete, "horizon_return"),
        "conservative_intrabar_net_expectancy": _average(complete, "conservative_intrabar_net_return"),
        "monitor_exit_only_net_expectancy": _average(complete, "simulated_monitor_net_return"),
    }


def _latency(values):
    values = sorted(values)
    return {"n": len(values), "p50_ms": median(values) if values else None,
            "p95_ms": values[math.ceil(len(values) * .95) - 1] if values else None}


def v2_comparisons(rows, evaluation_from):
    """Predeclared gates on an explicitly designated chronological holdout."""
    entries = []
    run_v1 = {}
    for row in rows:
        observed = _observed_date(row)
        if not observed or observed < evaluation_from:
            continue
        timing = _json_object(row.get("gpt_v2_v1_performance_json"))
        if timing:
            run_v1[row["run_key"]] = timing
        analysis = _json_object(row.get("gpt_v2_analysis_json"))
        if not row.get("gpt_v2_status"):
            continue
        legacy_c_status = _json_object(row.get("intraday_snapshot_metadata_json")).get("gpt_shadow_legacy_c_status")
        entries.append({
            "legacy_c": _finite(row.get("c_reversal_score")) if legacy_c_status in (None, "analyzed") else None,
            "legacy_gpt": _finite(row.get("a_gpt_buy_score")),
            "legacy_final": _finite(row.get("a_final_score")),
            "experimental_c": _finite(analysis.get("c_v2_score")),
            "v2_gpt": _finite(analysis.get("gpt_buy_score_v2")),
            "v2_final": _finite(analysis.get("final_score_v2")),
            "outcome": _json_object(row.get("gpt_v2_outcome_json")),
            "strict": analysis.get("strict_match_eligible") is True,
            "state": row["gpt_v2_status"], "run": row["run_key"],
            "regime": row.get("market_regime_key") or "unknown",
            "events": {event["event_type"] for event in analysis.get("corporate_events", [])} or {"unknown"},
            "v2_performance": analysis.get("performance") or {},
        })
    variants = {}
    matched = [row for row in entries if row["strict"] and all(row[key] is not None
               for key in ("legacy_c", "legacy_gpt", "experimental_c", "v2_gpt"))]
    for c in ("legacy_c", "experimental_c"):
        for gpt in ("legacy_gpt", "v2_gpt"):
            scored = [row for row in entries if row[c] is not None and row[gpt] is not None]
            eligible = [row for row in scored if row[c] >= 65 and row[gpt] >= 60
                        and round(row[c] * .75 + row[gpt] * .25, 2) >= 65]
            matched_eligible = [row for row in eligible if row in matched]
            variants[f"{c}+{gpt}"] = {
                "score_coverage": {"present": len(scored), "total": len(entries)},
                "eligible_candidates": len(eligible), "strict_matched": len(matched),
                "strict_matched_eligible": len(matched_eligible),
                "strategy_specific": {period: _outcome_metrics(eligible, period) for period in ("short", "long")},
                "matched": {period: _outcome_metrics(matched_eligible, period) for period in ("short", "long")},
            }
    run_v2 = {}
    for row in entries:
        total = _finite(row["v2_performance"].get("total_pipeline_ms"))
        if total is not None:
            run_v2[row["run"]] = total
    groups = {}
    for key in ("regime", "events"):
        values = {row["regime"] for row in entries} if key == "regime" else {
            event for row in entries for event in row["events"]}
        groups[key] = {}
        for value in sorted(values):
            group = [row for row in entries if (row[key] == value if key == "regime" else value in row[key])]
            groups[key][value] = {period: _outcome_metrics(group, period) for period in ("short", "long")}
    comparisons = {}
    for old, new in (("legacy_c", "experimental_c"), ("legacy_gpt", "v2_gpt"), ("legacy_final", "v2_final")):
        comparable = [row for row in matched if row[old] is not None and row[new] is not None]
        comparisons[f"{old}_vs_{new}"] = {
            "n": len(comparable), "strict_matched_total": len(matched),
            "mean_change": fmean(row[new] - row[old] for row in comparable) if comparable else None,
        }
    return {
        "version": "pr144-v1", "evaluation_from": evaluation_from.isoformat(),
        "candidate_count": len(entries), "strict_matched_count": len(matched),
        "status_coverage": dict(Counter(row["state"] for row in entries)),
        "market_regime_coverage": dict(Counter(row["regime"] for row in entries)),
        "corporate_event_coverage": dict(Counter(event for row in entries for event in row["events"])),
        "v1_parallel_decision_latency": _latency([value for row in run_v1.values()
            if row.get("parallel_execution_enabled") and (value := _finite(row.get("v1_decision_ready_ms"))) is not None]),
        "v1_only_decision_latency": _latency([value for row in run_v1.values()
            if row.get("parallel_execution_enabled") is False
            and (value := _finite(row.get("v1_decision_ready_ms"))) is not None]),
        "parallel_pipeline_latency": _latency(list(run_v2.values())),
        "shadow_api_requests": {
            key: sum(row["v2_performance"].get(key, 0) for row in entries)
            for key in ("kis_request_count", "openai_request_count", "cache_hit_count", "cache_miss_count")
        },
        "variants": variants,
        "matched_score_comparisons": comparisons,
        "grouped_outcomes": groups,
    }


def _date_argument(value: str) -> date:
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except ValueError:
        raise argparse.ArgumentTypeError("Expected YYYY-MM-DD") from None


def _score_argument(value: str) -> float:
    score = _finite(value)
    if score is None or not 0 <= score <= 100:
        raise argparse.ArgumentTypeError("Expected a finite score between 0 and 100")
    return score


def _rank_argument(value: str) -> int:
    try:
        rank = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError("Expected a positive integer") from None
    if rank < 1:
        raise argparse.ArgumentTypeError("Expected a positive integer")
    return rank


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--database", help="SQLite path; defaults to the app DATABASE_URL")
    parser.add_argument("--month", help="Korea calendar month YYYY-MM")
    parser.add_argument("--date", type=_date_argument, help="One Korea calendar date YYYY-MM-DD")
    parser.add_argument("--from-date", type=_date_argument)
    parser.add_argument("--to-date", type=_date_argument, help="Inclusive end date")
    parser.add_argument("--trigger-source")
    quality = parser.add_mutually_exclusive_group()
    quality.add_argument("--official-only", action="store_true")
    quality.add_argument("--include-partial", action="store_true", help="Include all qualities (default)")
    parser.add_argument("--format", choices=("csv", "json", "both"), default="csv")
    parser.add_argument("--output", type=Path, default=Path("data/abc_exports"), help="Directory or CSV/JSON file path")
    parser.add_argument("--a-rank-max", type=_rank_argument, default=5)
    parser.add_argument("--c-min-score", type=_score_argument, default=65)
    parser.add_argument("--gpt-min-score", type=_score_argument, default=60)
    parser.add_argument("--final-min-score", type=_score_argument, default=65)
    parser.add_argument("--passed-only", action="store_true")
    parser.add_argument("--v2-summary", type=Path, help="Optional JSON path for fixed-gate V2 comparisons")
    parser.add_argument("--evaluation-from", type=_date_argument, help="First day of the chronological holdout")
    return parser


def _date_filters(parser, args) -> str:
    if (args.month or args.date) and (args.from_date or args.to_date) or (args.month and args.date):
        parser.error("Use --month, --date, or --from-date/--to-date separately")
    if args.month:
        try:
            start = _date_argument(args.month + "-01")
        except argparse.ArgumentTypeError:
            parser.error("--month must be YYYY-MM")
        end = date(start.year + 1, 1, 1) if start.month == 12 else date(start.year, start.month + 1, 1)
        args.from_date, args.to_date = start, end - timedelta(days=1)
        label = args.month
    elif args.date:
        args.from_date = args.to_date = args.date
        label = args.date.isoformat()
    else:
        label = "all" if not (args.from_date or args.to_date) else (
            f"{args.from_date.isoformat() if args.from_date else 'start'}_"
            f"{args.to_date.isoformat() if args.to_date else 'latest'}"
        )
    if args.from_date and args.to_date and args.from_date > args.to_date:
        parser.error("--from-date must be on or before --to-date")
    return label


def _output_paths(parser, args, label: str) -> list[Path]:
    formats = ("csv", "json") if args.format == "both" else (args.format,)
    if args.output.suffix.lower() in {".csv", ".json"}:
        if args.format != "both" and args.output.suffix.lower() != "." + args.format:
            parser.error("--output file extension must match --format")
        return [args.output.with_suffix("." + fmt) for fmt in formats]
    return [args.output / f"abc_observations_{label}.{fmt}" for fmt in formats]


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    label = _date_filters(parser, args)
    paths = _output_paths(parser, args, label)
    if args.v2_summary and args.evaluation_from is None:
        parser.error("--v2-summary requires --evaluation-from")
    if args.v2_summary and (args.passed_only or args.official_only):
        parser.error("--v2-summary requires unfiltered candidate coverage")
    if args.v2_summary and args.v2_summary.resolve() in {path.resolve() for path in paths}:
        parser.error("--v2-summary must be a separate file")
    try:
        database = _database_path(args.database).expanduser().resolve()
        # An output path must never overwrite the database, WAL, or journal.
        protected = {Path(str(database) + suffix) for suffix in ("", "-wal", "-shm", "-journal")}
        if any(
            path.resolve() in protected
            or any(path.exists() and source.exists() and path.samefile(source) for source in protected)
            for path in [*paths, *([args.v2_summary] if args.v2_summary else [])]
        ):
            raise ValueError("Output path must not overwrite the database or SQLite sidecar files")
        engine = create_read_only_engine(database)
        try:
            with engine.connect() as connection:
                fieldnames, rows = read_rows(connection, args)
        finally:
            engine.dispose()
        for path in paths:
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.suffix.lower() == ".csv":
                with path.open("w", encoding="utf-8", newline="") as handle:
                    writer = csv.DictWriter(handle, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows({key: json.dumps(value, ensure_ascii=False) if isinstance(value, bool)
                                      else value for key, value in row.items()} for row in rows)
            else:
                with path.open("w", encoding="utf-8", newline="\n") as handle:
                    json.dump(rows, handle, ensure_ascii=False, indent=2, allow_nan=False)
                    handle.write("\n")
        if args.v2_summary:
            args.v2_summary.parent.mkdir(parents=True, exist_ok=True)
            with args.v2_summary.open("w", encoding="utf-8", newline="\n") as handle:
                json.dump(v2_comparisons(rows, args.evaluation_from), handle, ensure_ascii=False,
                          indent=2, allow_nan=False)
                handle.write("\n")
    except (ValueError, OSError, SQLAlchemyError) as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1
    available = sum(row["gpt_score_available"] for row in rows)
    official = sum(row["official_quality"] for row in rows)
    print("Export complete")
    print(f"rows: {len(rows)}")
    print(f"GPT score available: {available}")
    print(f"GPT score missing: {len(rows) - available}")
    print(f"Final score available: {sum(row.get('a_final_score') is not None for row in rows)}")
    print(f"Entry funnel pass: {sum(row['entry_funnel_pass'] for row in rows)}")
    print(f"Official: {official}")
    print(f"Partial/non-official: {len(rows) - official}")
    for path in paths:
        print(f"output: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
