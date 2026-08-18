from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.brokers.kis_client import (
    KIS_MARKET_CAP_RANKING_PATH,
    KIS_MARKET_CAP_RANKING_TR_ID,
    KisClient,
    normalize_domestic_market_cap_row,
)

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

DEFAULT_TARGET = ROOT / "config" / "watchlist_kr.stage3.universe100.yaml"
DEFAULT_TARGET_PER_MARKET = 50
DEFAULT_BAND_COUNT = 12
DEFAULT_MAX_NOTIONAL_KRW = 50_000.0
DEFAULT_MAX_NOTIONAL_PCT = 0.80

MARKET_CODES = {
    "KOSPI": "0001",
    "KOSDAQ": "1001",
}


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def positive_float(value: str) -> float:
    number = safe_float(value, default=float("nan"))
    if not math.isfinite(number) or number <= 0:
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
    number = safe_float(value, default=float("nan"))
    if not math.isfinite(number):
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


def one_share_price_range(max_notional: float) -> tuple[int, int]:
    minimum_price = int(max_notional // 2) + 1
    maximum_price = int(max_notional)
    if minimum_price >= maximum_price:
        raise ValueError("Invalid one-share price range.")
    return minimum_price, maximum_price


def build_price_bands(
    minimum_price: int,
    maximum_price: int,
    band_count: int,
) -> list[tuple[int, int]]:
    total_range = maximum_price - minimum_price + 1
    width = max(1, math.ceil(total_range / band_count))

    bands: list[tuple[int, int]] = []
    lower = minimum_price

    while lower <= maximum_price:
        upper = min(maximum_price, lower + width - 1)
        bands.append((lower, upper))
        lower = upper + 1

    return bands


def fetch_band(
    client: KisClient,
    *,
    market: str,
    minimum_price: int,
    maximum_price: int,
) -> list[dict[str, Any]]:
    payload = client.request_get(
        KIS_MARKET_CAP_RANKING_PATH,
        tr_id=KIS_MARKET_CAP_RANKING_TR_ID,
        params={
            "FID_COND_MRKT_DIV_CODE": "J",
            "FID_COND_SCR_DIV_CODE": "20174",
            "FID_INPUT_ISCD": MARKET_CODES[market],
            "FID_DIV_CLS_CODE": "0",
            "FID_BLNG_CLS_CODE": "0",
            "FID_TRGT_CLS_CODE": "0",
            "FID_TRGT_EXLS_CLS_CODE": "0",
            "FID_INPUT_PRICE_1": str(minimum_price),
            "FID_INPUT_PRICE_2": str(maximum_price),
            "FID_VOL_CNT": "",
        },
    )

    rows = payload.get("output") or payload.get("output1") or []
    return rows if isinstance(rows, list) else []


def build_universe(
    *,
    target: Path,
    target_per_market: int,
    band_count: int,
    max_notional_krw: float,
    max_notional_pct: float,
) -> int:
    client = KisClient()
    balance = client.get_account_balance()

    equity = safe_float(balance.get("total_asset_value") or balance.get("cash"))
    cash = safe_float(balance.get("cash"))

    if equity <= 0 or cash <= 0:
        raise SystemExit("Account equity or available cash is unavailable.")

    max_notional = calculate_max_notional(
        configured_max_notional_krw=max_notional_krw,
        configured_max_notional_pct=max_notional_pct,
        equity=equity,
        cash=cash,
    )

    minimum_price, maximum_price = one_share_price_range(max_notional)
    price_bands = build_price_bands(
        minimum_price,
        maximum_price,
        band_count,
    )

    print(f"Equity: {equity:,.0f} KRW")
    print(f"Cash: {cash:,.0f} KRW")
    print(f"Configured max notional KRW: {max_notional_krw:,.0f}")
    print(f"Configured max notional pct: {max_notional_pct:.4f}")
    print(f"Effective max notional: {max_notional:,.0f} KRW")
    print(
        f"One-share price range: "
        f"{minimum_price:,} ~ {maximum_price:,} KRW"
    )
    print(f"Price bands: {len(price_bands)}")
    print()

    ranking_by_market: dict[str, list[dict[str, Any]]] = {}

    for market in ("KOSPI", "KOSDAQ"):
        by_symbol: dict[str, dict[str, Any]] = {}

        for band_index, (band_min, band_max) in enumerate(
            price_bands,
            start=1,
        ):
            rows = fetch_band(
                client,
                market=market,
                minimum_price=band_min,
                maximum_price=band_max,
            )
            added = 0

            for row_index, row in enumerate(rows, start=1):
                normalized = normalize_domestic_market_cap_row(
                    row,
                    market=market,
                    fallback_rank=row_index,
                )

                if normalized is None:
                    continue

                raw_symbol = str(normalized.get("symbol") or "").strip()
                if not raw_symbol:
                    continue

                symbol = raw_symbol.zfill(6)

                if not symbol:
                    continue

                candidate = {
                    **normalized,
                    "price_band_min": band_min,
                    "price_band_max": band_max,
                }
                existing = by_symbol.get(symbol)

                if existing is None:
                    by_symbol[symbol] = candidate
                    added += 1
                    continue

                existing_cap = safe_float(existing.get("market_cap"))
                candidate_cap = safe_float(candidate.get("market_cap"))

                if candidate_cap > existing_cap:
                    by_symbol[symbol] = candidate

            print(
                f"{market} band={band_index:02d} | "
                f"price={band_min:,}~{band_max:,} | "
                f"rows={len(rows)} | "
                f"added={added} | "
                f"unique={len(by_symbol)}"
            )

        ranked = list(by_symbol.values())
        ranked.sort(
            key=lambda item: (
                safe_float(item.get("market_cap")),
                -int(item.get("rank") or 999999),
            ),
            reverse=True,
        )

        ranking_by_market[market] = ranked[:target_per_market]
        print(f"{market} selected: {len(ranking_by_market[market])}")
        print()

    kospi_count = len(ranking_by_market["KOSPI"])
    kosdaq_count = len(ranking_by_market["KOSDAQ"])

    if kospi_count != target_per_market or kosdaq_count != target_per_market:
        print(
            "Universe generation blocked: "
            f"KOSPI={kospi_count}, "
            f"KOSDAQ={kosdaq_count}"
        )
        print("Existing universe file was not overwritten.")
        return 2

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for market in ("KOSPI", "KOSDAQ"):
        for row in ranking_by_market[market]:
            raw_symbol = str(row.get("symbol") or "").strip()
            if not raw_symbol:
                continue

            symbol = raw_symbol.zfill(6)

            if len(symbol) != 6 or not symbol.isdigit() or symbol in seen:
                continue

            seen.add(symbol)
            selected.append(
                {
                    "symbol": symbol,
                    "name": str(row.get("name") or ""),
                    "market": market,
                    "market_cap": row.get("market_cap"),
                    "rank": row.get("rank"),
                    "price_band_min": row.get("price_band_min"),
                    "price_band_max": row.get("price_band_max"),
                }
            )

    expected_total = target_per_market * 2
    if len(selected) != expected_total:
        print(
            f"Universe validation failed: "
            f"total={len(selected)}, "
            f"unique={len(seen)}"
        )
        print("Existing universe file was not overwritten.")
        return 2

    payload = {
        "market": "KR",
        "currency": "KRW",
        "timezone": "Asia/Seoul",
        "source": "KIS market-cap ranking segmented by one-share price bands",
        "filters": {
            "minimum_price_krw": minimum_price,
            "maximum_price_krw": maximum_price,
            "configured_max_notional_krw": max_notional_krw,
            "configured_max_notional_pct": max_notional_pct,
            "max_notional_krw": max_notional,
            "expected_quantity": 1,
        },
        "groups": {
            "KOSPI": kospi_count,
            "KOSDAQ": kosdaq_count,
        },
        "symbols": selected,
    }

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target.with_name(f".{target.name}.tmp")
    temp_path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    temp_path.replace(target)

    print()
    print(f"Saved: {target}")
    print(f"KOSPI: {kospi_count}")
    print(f"KOSDAQ: {kosdaq_count}")
    print(f"Total: {len(selected)}")
    print(f"Unique: {len(seen)}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a Stage 3 KR universe of 100 one-share candidates.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--target-per-market",
        type=int,
        default=DEFAULT_TARGET_PER_MARKET,
    )
    parser.add_argument("--band-count", type=int, default=DEFAULT_BAND_COUNT)
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
    args = parser.parse_args(argv)

    if args.target_per_market <= 0:
        parser.error("--target-per-market must be positive")
    if args.band_count <= 0:
        parser.error("--band-count must be positive")

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return build_universe(
        target=args.target,
        target_per_market=int(args.target_per_market),
        band_count=int(args.band_count),
        max_notional_krw=float(args.max_notional_krw),
        max_notional_pct=float(args.max_notional_pct),
    )


if __name__ == "__main__":
    raise SystemExit(main())
