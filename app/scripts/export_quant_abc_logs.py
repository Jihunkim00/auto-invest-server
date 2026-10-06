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
from datetime import date, datetime, timedelta
from pathlib import Path
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
    query = select(*columns).select_from(source).order_by(observation.c.observed_at, observation.c.id)
    if args.trigger_source:
        query = query.where(observation.c.trigger_source == args.trigger_source)
    # SQLite ALTER TABLE appends columns; CSV order must not depend on migration history.
    known_columns = (*FRONT_COLUMNS, *DETAIL_COLUMNS)
    extra_columns = sorted(set(observation.c.keys()) - set(known_columns))
    fieldnames = list(dict.fromkeys((*known_columns, *extra_columns, *sorted(outcome_names))))
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
        rows.append({name: _json_value(row.get(name)) for name in fieldnames})
    return fieldnames, rows


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
    try:
        database = _database_path(args.database).expanduser().resolve()
        # An output path must never overwrite the database, WAL, or journal.
        protected = {Path(str(database) + suffix) for suffix in ("", "-wal", "-shm", "-journal")}
        if any(
            path.resolve() in protected
            or any(path.exists() and source.exists() and path.samefile(source) for source in protected)
            for path in paths
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
