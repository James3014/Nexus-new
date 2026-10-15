#!/usr/bin/env python3
"""Summarise one online A/B run dir with both lane columns (wiring plan PR-3).

usage: analyze_run.py <run_dir> [--json]

Reads ``with_nexus_*.jsonl`` / ``without_nexus_*.jsonl`` and, when present,
``prompt_symmetry_audit.json``. The rows are re-classified with
``scripts.bench.strict_llm_baseline`` (the runner's own rules), then reported as:

* per arm: rows, ``first_attempt`` and ``after_treatment`` solves, gain, model calls, tokens,
  tokens per extra solve, treatments that actually ran (attested);
* paired per task x trial: bare vs with-Nexus first attempt vs with-Nexus after treatment;
* flags: delivered candidate not among the row's model candidates, captured calls != row calls,
  first attempt not verifiable, prompt-symmetry status.

The lane comes from the rows (``lane``); rows without it are strict-lane rows, where
``first_attempt == after_treatment``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.strict_llm_baseline import (  # noqa: E402
    WITH_NEXUS_MODE,
    WITHOUT_NEXUS_MODE,
    apply_strict_llm_baseline_classification,
    lane_scorecard,
)


def load_rows(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for prefix in ("with_nexus", "without_nexus"):
        for path in sorted(run_dir.glob(f"{prefix}_*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    row = json.loads(line)
                    if isinstance(row, dict) and "mode" in row:
                        rows.append(row)
    return rows


def _audit_calls(run_dir: Path) -> dict[str, dict[str, Any]]:
    path = run_dir / "prompt_symmetry_audit.json"
    if not path.is_file():
        return {}
    report = json.loads(path.read_text(encoding="utf-8"))
    return {
        str(task.get("key")): task for task in report.get("tasks") or [] if isinstance(task, dict)
    } | {"__status__": {"status": report.get("status"), "lane": report.get("lane")}}


def _key(row: dict[str, Any]) -> str:
    return f"{row.get('task_id')}__{row.get('trial_index')}"


def analyze(run_dir: Path) -> dict[str, Any]:
    rows = load_rows(run_dir)
    apply_strict_llm_baseline_classification(rows)
    audit = _audit_calls(run_dir)
    lanes = sorted({str(row.get("lane") or "strict") for row in rows})
    arms = {
        "bare": lane_scorecard(rows, WITHOUT_NEXUS_MODE),
        "with_nexus": lane_scorecard(rows, WITH_NEXUS_MODE),
    }
    paired: dict[str, dict[str, Any]] = {}
    flags: list[str] = []
    for row in rows:
        if row.get("not_run"):
            continue
        entry = paired.setdefault(
            _key(row), {"task_id": row.get("task_id"), "trial": row.get("trial_index")}
        )
        if str(row.get("mode")) == WITHOUT_NEXUS_MODE:
            entry["bare"] = row.get("first_attempt")
            entry["bare_tokens"] = row.get("tokens")
            continue
        entry.update({
            "nexus_first": row.get("first_attempt"),
            "nexus_after": row.get("after_treatment"),
            "nexus_calls": int(row.get("model_calls") or 0),
            "nexus_tokens": row.get("tokens"),
            "treatment_applied": list(row.get("treatment_applied") or []),
            "classification": row.get("solve_classification"),
        })
        ident = f"{row.get('task_id')}#{row.get('trial_index')}"
        if row.get("treatment_sha_unbound"):
            flags.append(f"{ident}: delivered candidate not among the row's model candidates")
        task_audit = audit.get(_key(row))
        if task_audit is not None and int(task_audit.get("with_nexus_calls") or 0) != int(
            row.get("model_calls") or 0
        ):
            flags.append(
                f"{ident}: captured calls {task_audit.get('with_nexus_calls')} != row model_calls {row.get('model_calls')}"
            )
        if (
            row.get("lane") == "treatment"
            and int(row.get("model_calls") or 0) > 0
            and row.get("first_attempt_hidden_passed") is None
        ):
            flags.append(
                f"{ident}: first attempt not verifiable ({row.get('first_attempt_status')})"
            )
    return {
        "run_dir": str(run_dir),
        "lanes": lanes,
        "prompt_symmetry": audit.get("__status__", {}),
        "arms": arms,
        "paired": [paired[key] for key in sorted(paired)],
        "flags": flags,
    }


def _cell(value: Any) -> str:
    if value is True:
        return "solved"
    if value is False:
        return "-"
    return "" if value is None else str(value)


def render_markdown(result: dict[str, Any]) -> str:
    out = [
        f"# Online A/B run: {result['run_dir']}",
        f"lane(s): {', '.join(result['lanes'])}; prompt symmetry: {result['prompt_symmetry'].get('status', 'n/a')}",
        "",
        "| arm | rows | first_attempt | after_treatment | gain | model calls | extra calls | tokens | tokens / extra solve | treatments applied |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for arm, card in result["arms"].items():
        applied = ", ".join(f"{k}:{v}" for k, v in card["treatment_applied"].items()) or "-"
        out.append(
            f"| {arm} | {card['total_n']} | {card['first_attempt']} | {card['after_treatment']} | "
            f"{card['treatment_gain']} | {card['model_calls_total']} | {card['extra_model_calls']} | "
            f"{card['tokens_total']} | {_cell(card['tokens_per_extra_solve'])} | {applied} |"
        )
    out += [
        "",
        "| task | trial | bare | Nexus first attempt | Nexus after treatment | Nexus calls | Nexus tokens | treatments |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for entry in result["paired"]:
        out.append(
            f"| {entry.get('task_id')} | {entry.get('trial')} | {_cell(entry.get('bare'))} | "
            f"{_cell(entry.get('nexus_first'))} | {_cell(entry.get('nexus_after'))} | "
            f"{_cell(entry.get('nexus_calls'))} | {_cell(entry.get('nexus_tokens'))} | "
            f"{', '.join(entry.get('treatment_applied') or []) or '-'} |"
        )
    if result["flags"]:
        out += ["", "## Flags", *[f"- {flag}" for flag in result["flags"]]]
    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("run_dir")
    parser.add_argument("--json", action="store_true", help="print the analysis as JSON")
    args = parser.parse_args(argv)
    result = analyze(Path(args.run_dir))
    print(
        json.dumps(result, indent=2, sort_keys=True) if args.json else render_markdown(result),
        end="",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
