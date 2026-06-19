from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "app" / "tests" / "fixtures" / "agent_chat_eval_cases.json"
EVAL_TESTS = (
    "app/tests/test_agent_chat_eval_dataset.py",
    "app/tests/test_agent_chat_guardrails.py",
    "app/tests/test_agent_chat_utf8.py",
    "app/tests/test_agent_chat_followup_eval.py",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize or run the Agent Chat eval suite.")
    parser.add_argument("--pytest", action="store_true", help="Run the Agent Chat eval pytest files.")
    args = parser.parse_args()

    cases = json.loads(FIXTURE.read_text(encoding="utf-8"))
    groups = Counter(case["group"] for case in cases)
    categories = Counter(case["expected"]["category"] for case in cases)

    print(f"Agent Chat eval cases: {len(cases)}")
    print("Groups:")
    for key, count in sorted(groups.items()):
        print(f"  {key}: {count}")
    print("Categories:")
    for key, count in sorted(categories.items()):
        print(f"  {key}: {count}")

    if not args.pytest:
        return 0

    sys.stdout.flush()
    return subprocess.call([sys.executable, "-m", "pytest", "-q", *EVAL_TESTS], cwd=ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
