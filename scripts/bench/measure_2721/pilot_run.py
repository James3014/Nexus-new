"""BARE Haiku pilot on rejected-but-verified candidates (never held-out tasks).

One command: build rows (``pilot_rows``), materialize, run BARE once per task
through the measurement adapter, score each diff with ``pilot_oracle`` and
write ``pilot_summary.json``: solve rate, tokens (input / output / cache
creation / cache read), $ per task, wall time, infra count.

The API key is read only by the adapter from
``NEXUS_MEASUREMENT_ANTHROPIC_ENV_FILE``; nothing here reads or prints it.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.arms import load_manifest, run_bare
from scripts.bench.measure_2721.common import read_diff, write_json, write_jsonl
from scripts.bench.measure_2721.materialize import materialize_task
from scripts.bench.measure_2721.pilot_oracle import score
from scripts.bench.measure_2721.pilot_rows import pilot_rows
from scripts.bench.measure_2721.providers import ClaudeProvider


def summarize(rows: list[dict[str, Any]], scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    scored = [row for row in rows if not row.get("infra")]
    labels = [scores.get(row["run_id"], {}).get("label") for row in scored]
    costs = [row.get("total_cost_usd") or 0.0 for row in scored]

    def total(key: str) -> int:
        return sum(int(row.get(key) or 0) for row in scored)

    n = len(scored)
    return {
        "tasks_run": len(rows),
        "infra_rows": len(rows) - n,
        "scored_rows": n,
        "resolved": labels.count("RESOLVED"),
        "solve_rate": (labels.count("RESOLVED") / n) if n else None,
        "labels": {label: labels.count(label) for label in sorted({str(x) for x in labels})},
        "tokens": {key: total(key) for key in (
            "input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")},
        "usd_total": round(sum(costs), 4),
        "usd_per_task_mean": round(statistics.mean(costs), 4) if costs else None,
        "usd_per_task_median": round(statistics.median(costs), 4) if costs else None,
        "wall_seconds_median": statistics.median([row["wall_seconds"] for row in scored]) if scored else None,
        "num_turns_median": statistics.median([row.get("num_turns") or 0 for row in scored]) if scored else None,
        "not_prereg_scorer": True,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bank", required=True)
    parser.add_argument("--ids", nargs="+", required=True, help="10-15 rejected-but-verified candidate ids")
    parser.add_argument("--out", required=True)
    parser.add_argument("--claude-bin", required=True)
    parser.add_argument("--timeout", type=float, default=900.0)
    parser.add_argument("--key-file", default=str(Path("~/.config/nexus-measure-2721/anthropic.env").expanduser()))
    args = parser.parse_args(argv)
    out = Path(args.out).resolve()
    bank = Path(args.bank)
    rows_path = out / "pilot_rows.jsonl"
    write_jsonl(rows_path, pilot_rows(bank, args.ids))
    records = [materialize_task(row, bank / "repos", out / "mat") for row in json.loads(
        "[" + ",".join(rows_path.read_text().splitlines()) + "]")]
    write_jsonl(out / "mat" / "manifest.jsonl", records)
    if not Path(args.key_file).is_file():
        parser.error("no API key file yet; the pilot needs the measurement key (never use a personal login)")
    provider = ClaudeProvider(args.claude_bin, out / "run" / "traces", args.key_file)
    results, scores = [], {}
    for task in load_manifest(out / "mat" / "manifest.jsonl"):
        row = run_bare(task, 1, out / "run", provider, timeout_seconds=args.timeout)
        results.append(row)
        if not row.get("infra"):
            scores[row["run_id"]] = score(bank, task["task_id"], task["repo"], task["base_commit"],
                                          read_diff(Path(row["diff_path"])), out / "score" / row["run_id"])
            write_json(out / "score" / f"{row['run_id']}.json", scores[row["run_id"]])
    summary = summarize(results, scores)
    write_json(out / "pilot_summary.json", summary)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
