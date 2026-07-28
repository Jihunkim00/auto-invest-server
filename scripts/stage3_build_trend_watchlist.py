from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.indicator_service import IndicatorService

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_MAX_NOTIONAL_KRW = 50_000.0
DEFAULT_MAX_NOTIONAL_PCT = 0.80
DEFAULT_MAX_CANDIDATES = 10
DEFAULT_REQUIRED_SOURCE_COUNT = 100
MIN_REQUIRED_BARS = 60
REQUEST_TIMEOUT = 40
MAX_RETRIES = 4

RATE_LIMIT_MARKERS = (
    "EGW00201",
    "EGW00215",
    "초당 거래건수",
    "허용 가능한 초당 거래건수",
)


@dataclass(frozen=True)
class TrendBuildConfig:
    base_url: str
    source_watchlist: Path
    target_watchlist: Path
    report_dir: Path
    max_notional_krw: float
    max_notional_pct: float
    max_candidates: int
    required_source_count: int
    check_source_only: bool


def finite_number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(number):
        return None

    return number


def positive_float(value: str) -> float:
    number = finite_number(value)
    if number is None or number <= 0:
        raise argparse.ArgumentTypeError("value must be a positive number")
    return number


def pct_float(value: str) -> float:
    number = positive_float(value)
    if number > 1:
        raise argparse.ArgumentTypeError("value must be <= 1")
    return number


def env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return default
    number = finite_number(value)
    if number is None:
        raise ValueError(f"{name} must be numeric")
    return number


def calculate_max_notional(
    *,
    configured_max_notional_krw: float,
    configured_max_notional_pct: float,
    equity: float,
    cash: float,
) -> float:
    return min(
        float(configured_max_notional_krw),
        float(equity) * float(configured_max_notional_pct),
        float(cash),
    )


def api_get(
    path: str,
    *,
    base_url: str,
) -> dict[str, Any]:
    url = f"{base_url.rstrip('/')}{path}"
    last_error: Exception | None = None

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                timeout=REQUEST_TIMEOUT,
            )

            if response.ok:
                payload = response.json()
                time.sleep(0.4)
                return payload

            response_text = response.text or ""
            retryable = any(
                marker in response_text for marker in RATE_LIMIT_MARKERS
            )

            if not retryable:
                response.raise_for_status()

            last_error = RuntimeError(
                f"KIS rate limited: {response.status_code} "
                f"{response_text[:300]}"
            )

        except Exception as exc:
            last_error = exc

        time.sleep(2.0 + attempt)

    raise RuntimeError(f"GET failed after retries: {path}: {last_error}")


def normalize_source_symbols(items: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    symbols: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicates: list[str] = []
    invalid: list[Any] = []

    for item in items:
        if not isinstance(item, dict):
            invalid.append(item)
            continue

        raw_symbol = str(item.get("symbol") or "").strip()
        if not raw_symbol:
            invalid.append(item)
            continue

        symbol = raw_symbol.zfill(6)
        if len(symbol) != 6 or not symbol.isdigit():
            invalid.append(item)
            continue

        if symbol in seen:
            duplicates.append(symbol)
            continue

        seen.add(symbol)
        symbols.append(
            {
                "symbol": symbol,
                "name": str(item.get("name") or ""),
                "market": str(item.get("market") or "KR"),
            }
        )

    summary = {
        "source_symbol_count": len(items),
        "normalized_symbol_count": len(symbols),
        "duplicate_symbols": duplicates,
        "invalid_symbol_count": len(invalid),
    }
    return symbols, summary


def load_source_symbols(
    path: Path,
    *,
    required_count: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not path.exists():
        raise SystemExit(f"Source watchlist is missing: {path}")

    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    raw_symbols = payload.get("symbols") or []
    if not isinstance(raw_symbols, list):
        raise SystemExit("Source watchlist symbols must be a list.")

    symbols, summary = normalize_source_symbols(raw_symbols)
    if summary["invalid_symbol_count"]:
        raise SystemExit(
            "Source watchlist contains invalid symbols: "
            f"{summary['invalid_symbol_count']}"
        )
    if summary["duplicate_symbols"]:
        raise SystemExit(
            "Source watchlist contains duplicate symbols: "
            + ", ".join(summary["duplicate_symbols"])
        )
    if len(symbols) != required_count:
        raise SystemExit(
            "Source watchlist count mismatch: "
            f"expected={required_count}, actual={len(symbols)}"
        )
    return symbols, summary


def build_candidate_checks(
    *,
    current_price: float,
    ema20: float,
    ema50: float,
    vwap: float,
    short_momentum: float,
    max_notional: float,
    cash: float,
) -> tuple[dict[str, bool], int, float]:
    expected_qty = int(max_notional // current_price) if current_price > 0 else 0
    estimated_notional = float(current_price) * float(expected_qty)
    checks = {
        "price_positive": current_price > 0,
        "price_within_max_notional": current_price <= max_notional,
        "estimated_notional_within_cash": estimated_notional <= cash,
        "one_share_quantity": expected_qty == 1,
        "price_above_ema20": current_price > ema20,
        "ema20_above_ema50": ema20 > ema50,
        "price_above_ema50": current_price > ema50,
        "price_above_vwap": current_price > vwap,
        "positive_momentum": short_momentum > 0,
    }
    return checks, expected_qty, estimated_notional


def trend_strength(
    *,
    current_price: float,
    ema20: float,
    ema50: float,
    vwap: float,
    short_momentum: float,
) -> float:
    return (
        ((current_price / ema20) - 1.0) * 100
        + ((ema20 / ema50) - 1.0) * 100
        + ((current_price / vwap) - 1.0) * 100
        + short_momentum * 100
    )


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def build_trend_watchlist(config: TrendBuildConfig) -> int:
    source_symbols, source_summary = load_source_symbols(
        config.source_watchlist,
        required_count=config.required_source_count,
    )

    if config.check_source_only:
        print(json.dumps(source_summary, ensure_ascii=False, indent=2))
        return 0

    if not config.target_watchlist.exists():
        raise SystemExit(f"Target watchlist is missing: {config.target_watchlist}")

    config.report_dir.mkdir(parents=True, exist_ok=True)

    balance = api_get("/kis/account/balance", base_url=config.base_url)

    equity = finite_number(balance.get("total_asset_value") or balance.get("cash"))
    cash = finite_number(balance.get("cash"))

    if equity is None or equity <= 0:
        raise SystemExit("KIS total asset value is unavailable.")

    if cash is None or cash <= 0:
        raise SystemExit("KIS available cash is unavailable.")

    max_notional = calculate_max_notional(
        configured_max_notional_krw=config.max_notional_krw,
        configured_max_notional_pct=config.max_notional_pct,
        equity=equity,
        cash=cash,
    )

    if max_notional <= 0:
        raise SystemExit("Max notional is unavailable.")

    indicator_service = IndicatorService()
    passed: list[dict[str, Any]] = []
    report_rows: list[dict[str, Any]] = []

    print(f"Source symbols: {len(source_symbols)}")
    print(f"Equity: {equity:,.0f} KRW")
    print(f"Cash: {cash:,.0f} KRW")
    print(f"Configured max notional KRW: {config.max_notional_krw:,.0f}")
    print(f"Configured max notional pct: {config.max_notional_pct:.4f}")
    print(f"Effective max notional: {max_notional:,.0f} KRW")
    print()

    for index, item in enumerate(source_symbols, start=1):
        symbol = str(item["symbol"])
        name = str(item.get("name") or "")
        market = str(item.get("market") or "KR")

        row: dict[str, Any] = {
            "symbol": symbol,
            "name": name,
            "market": market,
            "passed": False,
            "failed_checks": [],
        }

        try:
            bars_payload = api_get(
                f"/kis/market/bars/{symbol}?limit=100",
                base_url=config.base_url,
            )
            bars = bars_payload.get("bars") or []
            row["bar_count"] = len(bars)

            if len(bars) < MIN_REQUIRED_BARS:
                row["failed_checks"].append("insufficient_bars")
                report_rows.append(row)
                print(
                    f"[{index}/{len(source_symbols)}] "
                    f"FAIL {symbol} {name}: insufficient_bars"
                )
                continue

            indicators = indicator_service.calculate(bars)

            ema20 = finite_number(indicators.get("ema20"))
            ema50 = finite_number(indicators.get("ema50"))
            vwap = finite_number(indicators.get("vwap"))
            momentum = finite_number(indicators.get("short_momentum"))
            volume_ratio = finite_number(indicators.get("volume_ratio"))
            rsi = finite_number(indicators.get("rsi"))

            price_payload = api_get(
                f"/kis/market/price/{symbol}",
                base_url=config.base_url,
            )
            current_price = finite_number(price_payload.get("current_price"))

            row.update(
                {
                    "current_price": current_price,
                    "ema20": ema20,
                    "ema50": ema50,
                    "vwap": vwap,
                    "short_momentum": momentum,
                    "volume_ratio": volume_ratio,
                    "rsi": rsi,
                }
            )

            required_values = {
                "current_price": current_price,
                "ema20": ema20,
                "ema50": ema50,
                "vwap": vwap,
                "short_momentum": momentum,
            }
            missing = [
                key
                for key, value in required_values.items()
                if value is None
            ]

            if missing:
                row["failed_checks"].append("missing:" + ",".join(missing))
                report_rows.append(row)
                print(
                    f"[{index}/{len(source_symbols)}] "
                    f"FAIL {symbol} {name}: missing indicators"
                )
                continue

            checks, expected_qty, estimated_notional = build_candidate_checks(
                current_price=float(current_price),
                ema20=float(ema20),
                ema50=float(ema50),
                vwap=float(vwap),
                short_momentum=float(momentum),
                max_notional=float(max_notional),
                cash=float(cash),
            )

            failed_checks = [
                key for key, passed_check in checks.items() if not passed_check
            ]

            row["checks"] = checks
            row["failed_checks"] = failed_checks
            row["expected_qty"] = expected_qty
            row["estimated_notional"] = estimated_notional

            if failed_checks:
                report_rows.append(row)
                print(
                    f"[{index}/{len(source_symbols)}] "
                    f"FAIL {symbol} {name} | "
                    f"price={current_price:,.0f} | "
                    f"failed={','.join(failed_checks)}"
                )
                continue

            strength = trend_strength(
                current_price=float(current_price),
                ema20=float(ema20),
                ema50=float(ema50),
                vwap=float(vwap),
                short_momentum=float(momentum),
            )

            row["passed"] = True
            row["trend_strength"] = strength
            report_rows.append(row)

            passed.append(
                {
                    "symbol": symbol,
                    "name": name or str(price_payload.get("name") or ""),
                    "market": market,
                    "current_price": current_price,
                    "ema20": ema20,
                    "ema50": ema50,
                    "vwap": vwap,
                    "short_momentum": momentum,
                    "volume_ratio": volume_ratio,
                    "rsi": rsi,
                    "expected_qty": expected_qty,
                    "estimated_notional": estimated_notional,
                    "trend_strength": strength,
                }
            )

            print(
                f"[{index}/{len(source_symbols)}] "
                f"PASS {symbol} {name} | "
                f"price={current_price:,.0f} | "
                f"EMA20={ema20:,.0f} | "
                f"EMA50={ema50:,.0f} | "
                f"VWAP={vwap:,.0f} | "
                f"momentum={momentum:+.2%} | "
                f"expected_qty={expected_qty}"
            )

        except Exception as exc:
            row["failed_checks"].append(f"request_error:{type(exc).__name__}")
            row["error"] = str(exc)
            report_rows.append(row)
            print(f"[{index}/{len(source_symbols)}] ERROR {symbol} {name}: {exc}")

    passed.sort(
        key=lambda item: (
            item["trend_strength"],
            item["short_momentum"],
            item["volume_ratio"] or 0,
        ),
        reverse=True,
    )

    selected = passed[: config.max_candidates]
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = config.report_dir / f"trend_watchlist_report_{timestamp}.json"
    top_candidate = selected[0] if selected else None

    report = {
        "created_at": datetime.now().isoformat(),
        "source_watchlist": str(config.source_watchlist),
        "target_watchlist": str(config.target_watchlist),
        "source_symbol_count": len(source_symbols),
        "account_equity": equity,
        "available_cash": cash,
        "configured_max_notional_krw": config.max_notional_krw,
        "configured_max_notional_pct": config.max_notional_pct,
        "max_notional": max_notional,
        "filters": {
            "expected_qty": 1,
            "price_within_max_notional": True,
            "estimated_notional_within_cash": True,
            "price_above_ema20": True,
            "ema20_above_ema50": True,
            "price_above_ema50": True,
            "price_above_vwap": True,
            "short_momentum_gt_zero": True,
        },
        "technical_pass_count": len(passed),
        "passed_count": len(passed),
        "selected_count": len(selected),
        "top_candidate": top_candidate,
        "selected": selected,
        "all_results": report_rows,
        "real_order_submitted": False,
        "broker_submit_called": False,
    }

    write_json(report_path, report)

    print()
    print(f"Passed technical filter: {len(passed)}")
    print(f"Report: {report_path}")
    if top_candidate:
        print(
            "Top technical candidate: "
            f"{top_candidate['symbol']} {top_candidate['name']} | "
            f"price={top_candidate['current_price']:,.0f} | "
            f"expected_qty={top_candidate['expected_qty']}"
        )

    if not selected:
        print(
            "No symbol passed all technical conditions. "
            "Current watchlist was not modified. Default action=HOLD."
        )
        return 2

    new_watchlist = {
        "market": "KR",
        "currency": "KRW",
        "timezone": "Asia/Seoul",
        "symbols": [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "market": item["market"],
            }
            for item in selected
        ],
    }

    temp_path = config.target_watchlist.with_name(
        f".{config.target_watchlist.name}.tmp"
    )
    temp_path.write_text(
        yaml.safe_dump(new_watchlist, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    temp_path.replace(config.target_watchlist)

    print()
    print(f"New watchlist saved: {config.target_watchlist}")
    print(f"Selected symbols: {len(selected)}")

    for item in selected:
        print(
            f"- {item['symbol']} {item['name']} | "
            f"price={item['current_price']:,.0f} | "
            f"momentum={item['short_momentum']:+.2%} | "
            f"expected_qty={item['expected_qty']}"
        )

    return 0


def parse_args(argv: list[str] | None = None) -> TrendBuildConfig:
    parser = argparse.ArgumentParser(
        description="Build a Stage 3 KR trend watchlist without submitting orders.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get("STAGE3_BASE_URL", DEFAULT_BASE_URL),
    )
    parser.add_argument(
        "--source-watchlist",
        type=Path,
        default=ROOT / "config" / "watchlist_kr.stage3.universe100.yaml",
    )
    parser.add_argument(
        "--target-watchlist",
        type=Path,
        default=ROOT / "config" / "watchlist_kr.yaml",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=ROOT / "stage3_logs",
    )
    parser.add_argument(
        "--max-notional-krw",
        type=positive_float,
        default=env_float("STAGE3_MAX_NOTIONAL_KRW", DEFAULT_MAX_NOTIONAL_KRW),
    )
    parser.add_argument(
        "--max-notional-pct",
        type=pct_float,
        default=env_float("STAGE3_MAX_NOTIONAL_PCT", DEFAULT_MAX_NOTIONAL_PCT),
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=DEFAULT_MAX_CANDIDATES,
    )
    parser.add_argument(
        "--require-source-count",
        type=int,
        default=DEFAULT_REQUIRED_SOURCE_COUNT,
    )
    parser.add_argument(
        "--check-source-only",
        action="store_true",
        help="Validate the source universe count without API calls or writes.",
    )
    args = parser.parse_args(argv)

    if args.max_candidates <= 0:
        parser.error("--max-candidates must be positive")
    if args.require_source_count <= 0:
        parser.error("--require-source-count must be positive")

    return TrendBuildConfig(
        base_url=str(args.base_url),
        source_watchlist=args.source_watchlist,
        target_watchlist=args.target_watchlist,
        report_dir=args.report_dir,
        max_notional_krw=float(args.max_notional_krw),
        max_notional_pct=float(args.max_notional_pct),
        max_candidates=int(args.max_candidates),
        required_source_count=int(args.require_source_count),
        check_source_only=bool(args.check_source_only),
    )


def main(argv: list[str] | None = None) -> int:
    config = parse_args(argv)
    return build_trend_watchlist(config)


if __name__ == "__main__":
    raise SystemExit(main())
