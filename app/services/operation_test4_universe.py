from __future__ import annotations

import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml


DEFAULT_MINIMUM_COUNT = 70
DEFAULT_MAXIMUM_COUNT = 100
UNIVERSE_MARKET = "KR"
UNIVERSE_PROVIDER = "kis"
UNIVERSE_PURPOSE = "operation_test4"


class OperationTest4UniverseError(ValueError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.details = details or {}


def build_operation_test4_universe(
    *,
    root: Path,
    output_path: Path,
    minimum_count: int = DEFAULT_MINIMUM_COUNT,
    maximum_count: int = DEFAULT_MAXIMUM_COUNT,
    now: datetime | None = None,
) -> dict[str, Any]:
    minimum = int(minimum_count)
    maximum = int(maximum_count)
    if minimum <= 0 or maximum < minimum:
        raise OperationTest4UniverseError(
            "minimum-count and maximum-count must be positive with minimum <= maximum"
        )

    source_rows = _approved_source_rows(root)
    symbols: list[dict[str, Any]] = []
    seen: set[str] = set()
    source_counts: dict[str, int] = {}
    source_candidate_counts: dict[str, int] = {}
    for source_name, rows in source_rows:
        source_candidate_counts[source_name] = 0
        for row in rows:
            normalized = _normalize_row(row, source_name=source_name)
            if normalized is None:
                continue
            source_candidate_counts[source_name] += 1
            symbol = normalized["symbol"]
            if symbol in seen:
                continue
            seen.add(symbol)
            source_counts[source_name] = source_counts.get(source_name, 0) + 1
            symbols.append(normalized)
            if len(symbols) >= maximum:
                break
        if len(symbols) >= maximum:
            break

    if len(symbols) < minimum:
        details = {
            "minimum_count": minimum,
            "maximum_count": maximum,
            "universe_count": len(symbols),
            "source_candidate_counts": source_candidate_counts,
            "source_counts": source_counts,
        }
        raise OperationTest4UniverseError(
            "approved Test4 universe is below minimum: "
            f"minimum={minimum}, actual={len(symbols)}, "
            f"source_counts={source_counts}",
            details=details,
        )

    generated_at = (now or datetime.now(UTC)).astimezone(UTC).isoformat()
    payload = {
        "market": UNIVERSE_MARKET,
        "provider": UNIVERSE_PROVIDER,
        "purpose": UNIVERSE_PURPOSE,
        "generated_at": generated_at,
        "minimum_count": minimum,
        "maximum_count": maximum,
        "configured_count": len(symbols),
        "source_counts": source_counts,
        "source_candidate_counts": source_candidate_counts,
        "sources": [
            {
                "source": source_name,
                "candidate_count": source_candidate_counts.get(source_name, 0),
                "contributed_count": source_counts.get(source_name, 0),
            }
            for source_name, _rows in source_rows
        ],
        "symbols": symbols,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    return payload


def load_operation_test4_universe(
    path: Path,
    *,
    minimum_count: int = DEFAULT_MINIMUM_COUNT,
    maximum_count: int = DEFAULT_MAXIMUM_COUNT,
) -> dict[str, Any]:
    if not path.exists():
        raise OperationTest4UniverseError(f"universe is missing: {path}")
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise OperationTest4UniverseError("universe must be a mapping")
    if payload.get("market") != UNIVERSE_MARKET:
        raise OperationTest4UniverseError("universe market must be KR")
    if payload.get("provider") != UNIVERSE_PROVIDER:
        raise OperationTest4UniverseError("universe provider must be kis")
    rows = payload.get("symbols")
    if not isinstance(rows, list):
        raise OperationTest4UniverseError("universe symbols must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        normalized_row = _normalize_row(row, source_name=str(row.get("source") or "universe")) if isinstance(row, dict) else None
        if normalized_row is None:
            raise OperationTest4UniverseError("universe contains an invalid symbol")
        if normalized_row["symbol"] in seen:
            raise OperationTest4UniverseError(
                f"universe contains duplicate symbol: {normalized_row['symbol']}"
            )
        seen.add(normalized_row["symbol"])
        normalized.append(normalized_row)
    if not minimum_count <= len(normalized) <= maximum_count:
        raise OperationTest4UniverseError(
            f"universe count must be between {minimum_count} and {maximum_count}: {len(normalized)}"
        )
    return {**payload, "symbols": normalized, "count": len(normalized)}


def _approved_source_rows(root: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    sources: list[tuple[str, list[dict[str, Any]]]] = []
    seen_sources: set[str] = set()

    def add_source(source_name: str, rows: list[dict[str, Any]]) -> None:
        if source_name in seen_sources or not rows:
            return
        seen_sources.add(source_name)
        sources.append((source_name, rows))

    base_path = root / "config/local-watchlists/watchlist_kr.base50.yaml"
    add_source("local_watchlist_kr_base50", _rows_from_file(base_path))

    for commit, rows in _git_history_rows(root):
        add_source(f"historical_default_watchlist:{commit}", rows)

    operational_paths = sorted(
        (root / "config/local-watchlists").glob("watchlist_kr*.yaml")
        if (root / "config/local-watchlists").exists()
        else []
    )
    for path in operational_paths:
        if path.name == "watchlist_kr.base50.yaml":
            continue
        add_source(f"operational_watchlist:{path.name}", _rows_from_file(path))

    repository_paths = [
        root / "config/watchlist_kr.yaml",
        *sorted((root / "config").glob("watchlist_kr*.yaml")),
        *sorted((root / "config").glob("watchlist_kr*.yml")),
        root / "config/watchlist_kr.stage3.universe100.yaml",
    ]
    for path in repository_paths:
        if not path.exists():
            continue
        add_source(f"repository_watchlist:{path.name}", _rows_from_file(path))
    return sources


def _git_history_rows(root: Path) -> list[tuple[str, list[dict[str, Any]]]]:
    try:
        result = subprocess.run(
            [
                "git",
                "log",
                "--all",
                "--format=%H",
                "-50",
                "--",
                "config/watchlist_kr.yaml",
            ],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    history: list[tuple[str, list[dict[str, Any]]]] = []
    seen_commits: set[str] = set()
    for commit in result.stdout.splitlines():
        commit = commit.strip()
        if not commit or commit in seen_commits:
            continue
        seen_commits.add(commit)
        try:
            content = subprocess.run(
                ["git", "show", f"{commit}:config/watchlist_kr.yaml"],
                cwd=root,
                check=True,
                capture_output=True,
            ).stdout.decode("utf-8")
        except (OSError, UnicodeDecodeError, subprocess.SubprocessError):
            continue
        rows = _rows_from_text(content)
        if rows:
            history.append((commit, rows))
    return history


def _rows_from_file(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        return _rows_from_payload(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except (OSError, UnicodeError, yaml.YAMLError):
        return []


def _rows_from_text(content: str) -> list[dict[str, Any]]:
    try:
        return _rows_from_payload(yaml.safe_load(content) or {})
    except yaml.YAMLError:
        return []


def _rows_from_payload(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        market = str(payload.get("market") or "").strip().upper()
        if market and market != UNIVERSE_MARKET:
            return []
        rows = payload.get("symbols") or payload.get("watchlist") or []
    elif isinstance(payload, list):
        rows = payload
    else:
        return []
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def _normalize_row(row: dict[str, Any], *, source_name: str) -> dict[str, Any] | None:
    raw_symbol = str(row.get("symbol") or row.get("code") or "").strip()
    if raw_symbol.isdigit():
        raw_symbol = raw_symbol.zfill(6)
    if not re.fullmatch(r"\d{6}", raw_symbol):
        return None
    name = str(row.get("name") or row.get("source_name") or "").strip()
    return {
        "symbol": raw_symbol,
        "name": name,
        "source_name": str(row.get("source_name") or name),
        "source": str(row.get("source") or source_name),
        "market": str(row.get("market") or UNIVERSE_MARKET),
    }