from __future__ import annotations

import argparse
import json
from pathlib import Path

from nexus.services.local_heal.manifest_report import summarize_manifest_results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_jsonl")
    parser.add_argument("--output", help="Optional JSON summary output path")
    args = parser.parse_args()

    summary = summarize_manifest_results(args.results_jsonl)
    text = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
