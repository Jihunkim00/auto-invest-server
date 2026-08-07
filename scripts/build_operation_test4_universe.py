from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.operation_test4_universe import (
    DEFAULT_MAXIMUM_COUNT,
    DEFAULT_MINIMUM_COUNT,
    OperationTest4UniverseError,
    build_operation_test4_universe,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build the approved Operation Test 4 KR reserve universe."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "config/watchlist_kr_test4_universe.yaml",
    )
    parser.add_argument("--minimum-count", type=int, default=DEFAULT_MINIMUM_COUNT)
    parser.add_argument("--maximum-count", type=int, default=DEFAULT_MAXIMUM_COUNT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        payload = build_operation_test4_universe(
            root=ROOT,
            output_path=args.output,
            minimum_count=args.minimum_count,
            maximum_count=args.maximum_count,
        )
    except OperationTest4UniverseError as exc:
        print(f"Operation Test 4 universe build failed: {exc}", file=sys.stderr)
        if exc.details:
            print(f"details={exc.details}", file=sys.stderr)
        return 1
    print(
        f"built {payload['configured_count']} approved symbols; "
        f"source_counts={payload['source_counts']}; output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())