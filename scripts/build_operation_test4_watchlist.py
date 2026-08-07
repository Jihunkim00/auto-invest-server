from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.brokers.kis_client import KisClient
from app.config import get_settings
from app.services.operation_test4_watchlist import (
    DEFAULT_COUNT,
    DEFAULT_PRICE_CAP_KRW,
    OperationTest4WatchlistError,
    build_operation_test4_watchlist,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the Operation Test 4 KR watchlist.")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "config/watchlist_kr_test4.yaml",
    )
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--price-cap-krw", type=float, default=DEFAULT_PRICE_CAP_KRW)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.count <= 0 or args.price_cap_krw <= 0:
        print("count and price cap must be positive", file=sys.stderr)
        return 2
    try:
        result = build_operation_test4_watchlist(
            root=ROOT,
            output_path=args.output,
            count=args.count,
            price_cap_krw=args.price_cap_krw,
            client=KisClient(get_settings()),
        )
    except OperationTest4WatchlistError as exc:
        print(f"Operation Test 4 watchlist build failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"built {result['configured_count']} symbols; "
        f"excluded={result['excluded_count']}; output={result['output_path']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())