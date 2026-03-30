#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.delivery.models import CompletionResult
from nexus.delivery.report import render_markdown_report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render a markdown delivery report from a completion-gate JSON file.",
    )
    parser.add_argument("input_json")
    parser.add_argument("--output")
    args = parser.parse_args()

    input_path = Path(args.input_json)
    result = CompletionResult.model_validate(json.loads(input_path.read_text(encoding="utf-8")))
    markdown = render_markdown_report(result)
    if args.output:
        Path(args.output).write_text(markdown, encoding="utf-8")
    else:
        print(markdown)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
