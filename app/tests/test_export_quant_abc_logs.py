from __future__ import annotations

import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.models import QuantABObservation, QuantABOutcome
from app.scripts.export_quant_abc_logs import FRONT_COLUMNS, create_read_only_engine, main, official_quality


def _snapshot():
    return {variant: {frame: {"bar_count": 3} for frame in ("15m", "30m", "60m")}
            for variant in ("b", "c")}


@pytest.fixture()
def export_database(tmp_path):
    path = tmp_path / "abc.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    QuantABObservation.__table__.create(engine)
    QuantABOutcome.__table__.create(engine)
    with Session(engine) as session:
        for symbol, observed, gpt, final, quality in (
            ("PASS", "2026-10-01T00:00:00", 63, 67, 1),
            ("MISSING", "2026-10-31T23:59:59", None, 72, 1),
            ("PARTIAL", "2026-10-02T09:10:00", 0, 50, .5),
            ("SEPTEMBER", "2026-09-30T23:59:59", None, 68, 1),
            ("NOVEMBER", "2026-11-01T00:00:00", 64, 67, 1),
        ):
            session.add(QuantABObservation(
                observation_key=f"export:{symbol}", run_key=f"run-{symbol}",
                experiment_cohort_key="cohort", trigger_source="replay" if symbol == "SEPTEMBER" else "scheduler",
                provider="kis", market="KR", symbol=symbol,
                observed_at=datetime.fromisoformat(observed), decision_slot=observed + "+09:00",
                gate_level=2, a_rank=2, a_quant_buy_score=72, a_quant_sell_score=12,
                a_gpt_buy_score=gpt, a_final_score=final, c_reversal_score=68,
                b_entry_score=70, data_quality_b=quality, data_quality_c=quality,
                gpt_selected_by_a=True, selected_by_a=True, selected_by_b_shadow=True,
                selected_by_c_shadow=False, indicator_snapshot_json=json.dumps(_snapshot()),
                intraday_snapshot_metadata_json=json.dumps({"validation_status": "ok" if quality == 1 else "partial"}),
                b_reason="분석 로그", outcome_status="pending",
            ))
        session.flush()
        first = session.query(QuantABObservation).filter_by(symbol="PASS").one()
        session.add(QuantABOutcome(
            observation_id=first.id, cohort_key="cohort", symbol="PASS",
            entry_price=100, return_next_slot_pct=1.5, return_second_slot_pct=2.5,
            return_third_slot_pct=3.5, max_favorable_excursion_pct=5,
            max_adverse_excursion_pct=-2, outcome_status="complete", data_quality=1,
            tp_hit=True, sl_hit=False, simulated_return_pct=5,
        ))
        session.commit()
    engine.dispose()
    return path


def _export(database, tmp_path, *options):
    output = tmp_path / "export"
    assert main(["--database", str(database), "--format", "both", "--output", str(output), *options]) == 0
    json_path = next(output.glob("*.json"))
    csv_path = next(output.glob("*.csv"))
    rows = json.loads(json_path.read_text(encoding="utf-8"))
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        csv_rows = list(reader)
        fields = reader.fieldnames
    return rows, csv_rows, fields, json_path


def test_export_csv_json_preserve_all_observations_and_left_join(export_database, tmp_path, capsys):
    before = hashlib.sha256(export_database.read_bytes()).hexdigest()
    rows, csv_rows, fields, json_path = _export(export_database, tmp_path, "--month", "2026-10")
    assert len(rows) == len(csv_rows) == 3
    assert fields[:len(FRONT_COLUMNS)] == list(FRONT_COLUMNS)
    by_symbol = {row["symbol"]: row for row in rows}
    csv_by_symbol = {row["symbol"]: row for row in csv_rows}
    first = by_symbol["PASS"]
    assert first["a_gpt_buy_score"] == 63.0
    assert first["a_final_score"] == 67.0
    assert first["entry_funnel_pass"] is True
    assert first["official_quality"] is True
    assert first["gpt_score_available"] is True
    assert first["entry_price"] == 100
    assert first["return_next_slot_pct"] == 1.5
    assert first["max_favorable_excursion_pct"] == 5
    assert first["max_adverse_excursion_pct"] == -2
    assert first["outcome_status"] == "pending"
    assert first["outcome_label_status"] == "complete"
    assert first["observed_at"] == "2026-10-01T00:00:00"
    assert isinstance(first["a_gpt_buy_score"], float)
    assert first["tp_hit"] is True
    missing = by_symbol["MISSING"]
    assert missing["a_gpt_buy_score"] is None
    assert missing["gpt_selected_by_a"] is True
    assert missing["gpt_score_available"] is False
    assert missing["entry_funnel_pass"] is False
    assert missing["entry_price"] is None
    assert missing["outcome_id"] is None
    assert missing["tp_hit"] is None
    assert csv_by_symbol["MISSING"]["a_gpt_buy_score"] == ""
    assert csv_by_symbol["MISSING"]["entry_price"] == ""
    assert by_symbol["PARTIAL"]["a_gpt_buy_score"] == 0.0
    assert by_symbol["PARTIAL"]["gpt_score_available"] is True
    assert by_symbol["PARTIAL"]["official_quality"] is False
    assert by_symbol["PARTIAL"]["entry_funnel_pass"] is False
    assert csv_by_symbol["PASS"]["entry_funnel_pass"] == "true"
    assert "분석 로그" in json_path.read_text(encoding="utf-8")
    assert set(rows[0]) == set(fields)
    assert hashlib.sha256(export_database.read_bytes()).hexdigest() == before
    output = capsys.readouterr().out
    for line in ("rows: 3", "GPT score available: 2", "GPT score missing: 1",
                 "Final score available: 3", "Entry funnel pass: 1", "Official: 2", "Partial/non-official: 1"):
        assert line in output


@pytest.mark.parametrize("options,expected", [
    (["--month", "2026-10"], {"PASS", "MISSING", "PARTIAL"}),
    (["--from-date", "2026-10-01", "--to-date", "2026-10-31"], {"PASS", "MISSING", "PARTIAL"}),
    (["--date", "2026-10-31"], {"MISSING"}),
    (["--from-date", "2026-10-31"], {"MISSING", "NOVEMBER"}),
    (["--to-date", "2026-10-01"], {"PASS", "SEPTEMBER"}),
    (["--trigger-source", "replay"], {"SEPTEMBER"}),
    (["--month", "2026-10", "--official-only"], {"PASS", "MISSING"}),
    (["--month", "2026-10", "--include-partial"], {"PASS", "MISSING", "PARTIAL"}),
    (["--month", "2026-10", "--passed-only"], {"PASS"}),
    (["--month", "2026-10", "--passed-only", "--a-rank-max", "1"], set()),
    (["--month", "2026-10", "--passed-only", "--c-min-score", "69"], set()),
    (["--month", "2026-10", "--passed-only", "--gpt-min-score", "64"], set()),
    (["--month", "2026-10", "--passed-only", "--final-min-score", "68"], set()),
])
def test_export_filters(export_database, tmp_path, options, expected):
    rows, _, _, _ = _export(export_database, tmp_path, *options)
    assert {row["symbol"] for row in rows} == expected


def test_custom_thresholds_only_annotate_rows(export_database, tmp_path):
    rows, _, _, _ = _export(export_database, tmp_path, "--month", "2026-10", "--gpt-min-score", "64")
    assert len(rows) == 3
    assert not any(row["entry_funnel_pass"] for row in rows)


def test_korea_date_boundary_for_aware_timestamp(export_database, tmp_path):
    engine = create_engine(f"sqlite:///{export_database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("UPDATE quant_ab_observations SET observed_at=:at WHERE symbol='PASS'"),
                           {"at": "2026-09-30T15:00:00+00:00"})
        connection.execute(text("UPDATE quant_ab_observations SET observed_at=:at WHERE symbol='MISSING'"),
                           {"at": "2026-10-31T15:00:00+00:00"})
    engine.dispose()
    rows, _, _, _ = _export(export_database, tmp_path, "--month", "2026-10")
    assert {row["symbol"] for row in rows} == {"PASS", "PARTIAL"}


def test_read_only_connection_rejects_writes(export_database):
    before = export_database.read_bytes()
    engine = create_read_only_engine(export_database)
    try:
        with engine.connect() as connection:
            assert connection.exec_driver_sql("PRAGMA query_only").scalar_one() == 1
            with pytest.raises(OperationalError, match="readonly"):
                connection.exec_driver_sql("DELETE FROM quant_ab_observations")
    finally:
        engine.dispose()
    assert export_database.read_bytes() == before


def test_legacy_schema_exports_null_without_migration(export_database, tmp_path, capsys):
    engine = create_engine(f"sqlite:///{export_database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE quant_ab_observations DROP COLUMN a_gpt_buy_score"))
    engine.dispose()
    before = export_database.read_bytes()
    rows, _, _, _ = _export(export_database, tmp_path, "--month", "2026-10")
    assert all(row["a_gpt_buy_score"] is None and not row["entry_funnel_pass"] for row in rows)
    assert export_database.read_bytes() == before
    assert "a_gpt_buy_score column missing" in capsys.readouterr().err


def test_default_database_url_is_reused_without_overwrite(export_database, tmp_path, monkeypatch):
    from app import config
    database_url = f"sqlite:///{export_database.as_posix()}"
    monkeypatch.setattr(config, "get_settings", lambda: SimpleNamespace(database_url=database_url))
    environment_before = os.environ.get("DATABASE_URL")
    target = tmp_path / "default.json"
    assert main(["--format", "json", "--output", str(target)]) == 0
    assert len(json.loads(target.read_text(encoding="utf-8"))) == 5
    assert os.environ.get("DATABASE_URL") == environment_before


def test_cli_has_no_broker_gpt_or_app_startup_imports(export_database, tmp_path):
    target = tmp_path / "subprocess.json"
    script = """
import builtins, sys
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.startswith(('app.db', 'app.brokers', 'app.services', 'app.main', 'openai', 'requests', 'httpx')):
        raise AssertionError('Forbidden exporter dependency: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
from app.scripts.export_quant_abc_logs import main
raise SystemExit(main(sys.argv[1:]))
"""
    result = subprocess.run([sys.executable, "-c", script, "--database", str(export_database),
                             "--format", "json", "--output", str(target)],
                            cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert len(json.loads(target.read_text(encoding="utf-8"))) == 5


@pytest.mark.parametrize("options", [
    ["--month", "2026-13"], ["--date", "2026-02-30"],
    ["--month", "2026-10", "--date", "2026-10-01"],
    ["--month", "2026-10", "--from-date", "2026-10-01"],
    ["--from-date", "2026-10-31", "--to-date", "2026-10-01"],
    ["--official-only", "--include-partial"], ["--gpt-min-score", "nan"],
    ["--final-min-score", "101"], ["--a-rank-max", "0"],
])
def test_invalid_cli_arguments_do_not_create_database(tmp_path, options):
    missing = tmp_path / "missing.db"
    with pytest.raises(SystemExit) as error:
        main(["--database", str(missing), *options])
    assert error.value.code == 2
    assert not missing.exists()


def test_missing_database_is_not_created(tmp_path, capsys):
    missing = tmp_path / "missing.db"
    assert main(["--database", str(missing), "--output", str(tmp_path / "export")]) == 1
    assert not missing.exists()
    assert "Database file does not exist" in capsys.readouterr().err


def test_export_cannot_overwrite_source_database(export_database, capsys):
    target = export_database.with_suffix(".csv")
    export_database.rename(target)
    before = target.read_bytes()
    assert main(["--database", str(target), "--output", str(target)]) == 1
    assert target.read_bytes() == before
    assert "must not overwrite" in capsys.readouterr().err


@pytest.mark.parametrize("change", ["partial", "missing_metadata", "malformed_metadata", "low_b", "low_c", "few_b_bars", "few_c_bars"])
def test_official_quality_matches_existing_partial_evidence(change):
    row = {"b_entry_score": 70, "c_reversal_score": 68, "data_quality_b": 1,
           "data_quality_c": 1, "indicator_snapshot_json": json.dumps(_snapshot()),
           "intraday_snapshot_metadata_json": '{"validation_status":"ok"}'}
    assert official_quality(row) is True
    if change == "partial":
        row["intraday_snapshot_metadata_json"] = '{"validation_status":"partial"}'
    elif change == "missing_metadata":
        row["intraday_snapshot_metadata_json"] = None
    elif change == "malformed_metadata":
        row["intraday_snapshot_metadata_json"] = "invalid-json"
    elif change.startswith("low_"):
        row[f"data_quality_{change[-1]}"] = .99
    else:
        snapshot = _snapshot()
        snapshot[change[4]]["30m"]["bar_count"] = 1
        row["indicator_snapshot_json"] = json.dumps(snapshot)
    assert official_quality(row) is False



def test_export_cannot_overwrite_source_through_hardlink(export_database, tmp_path):
    target = tmp_path / "alias.csv"
    os.link(export_database, target)
    before = export_database.read_bytes()
    assert main(["--database", str(export_database), "--output", str(target)]) == 1
    assert export_database.read_bytes() == before


def test_observations_export_when_outcome_table_is_absent(export_database, tmp_path):
    engine = create_engine(f"sqlite:///{export_database.as_posix()}")
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE quant_ab_outcomes"))
    engine.dispose()
    rows, _, _, _ = _export(export_database, tmp_path, "--month", "2026-10")
    assert len(rows) == 3
    assert rows[0]["a_gpt_buy_score"] == 63


def test_missing_observation_table_has_clear_error(tmp_path, capsys):
    path = tmp_path / "empty.db"
    engine = create_engine(f"sqlite:///{path.as_posix()}")
    with engine.connect():
        pass
    engine.dispose()
    assert main(["--database", str(path), "--output", str(tmp_path / "export")]) == 1
    assert "quant_ab_observations table missing" in capsys.readouterr().err


def test_c_only_full_quality_uses_c_snapshot():
    row = {"b_entry_score": None, "data_quality_b": 0, "c_reversal_score": 68,
           "data_quality_c": 1, "indicator_snapshot_json": json.dumps({"c": _snapshot()["c"]}),
           "intraday_snapshot_metadata_json": '{"validation_status":"ok"}'}
    assert official_quality(row) is True



def test_csv_column_order_is_independent_of_sqlite_column_order(export_database, tmp_path):
    from sqlalchemy import Column, MetaData, Table, select

    _, _, original_fields, _ = _export(export_database, tmp_path / "original")
    engine = create_engine(f"sqlite:///{export_database.as_posix()}")
    with engine.begin() as connection:
        for name in ("quant_ab_outcomes", "quant_ab_observations"):
            original = Table(name, MetaData(), autoload_with=connection)
            values = [dict(row) for row in connection.execute(select(original)).mappings()]
            original.drop(connection)
            reordered = Table(name, MetaData(), *(Column(column.name, column.type)
                                                  for column in reversed(list(original.c))))
            reordered.create(connection)
            connection.execute(reordered.insert(), values)
    engine.dispose()
    _, _, reordered_fields, _ = _export(export_database, tmp_path / "reordered")
    assert original_fields == reordered_fields
