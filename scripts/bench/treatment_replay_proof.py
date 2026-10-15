#!/usr/bin/env python3
"""Treatment-lane replay proof: the 8th assertion of the zero-model symmetry proof (PR-3).

usage: treatment_replay_proof.py <run_out_dir> --tasks-file F [--repo-root R]

The 7-assertion strict proof (``symproof_assert.py``) checks a zero-model counted run. This adds
one assertion for the treatment lane without any model call: for every task of that run, the
captured bare prompt and the captured with-Nexus round-1 prompt are replayed through
``prompt_symmetry_audit.audit_run(lane="treatment")`` together with a synthetic round-2 prompt.

* ``h_round2_self_heal_passes``: the round-1 prompt plus the product's self-heal block
  (``Previous candidate failed verification...`` / ``[FAILURE]`` / a product error code) is a
  legitimate round 2 and must PASS;
* ``h_round2_hint_fails``: the same round 2 with one hint line must FAIL
  (``treatment_round_not_allowed``).

Prints PASS/FAIL per assertion; exit 1 on any FAIL. Never calls a model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.bench.agy_prompt_capture import capture_record, write_record  # noqa: E402
from scripts.bench.prompt_symmetry_audit import (  # noqa: E402
    SELF_HEAL_SENTENCE,
    TaskMaterial,
    audit_run,
    load_captures,
)

HINT_LINE = "hint: return the canonical value the hidden test expects."
REPLAY_RUN_ID = "treatment-replay"


def self_heal_round(round1: str, failure: str = "no_change_candidate", extra: str = "") -> str:
    """The product's round-2 prompt shape: the task line followed by the self-heal block."""

    lines = round1.split("\n")
    for index, line in enumerate(lines):
        if line.startswith("Task: "):
            block = ["", SELF_HEAL_SENTENCE, "[FAILURE]", failure, *([extra] if extra else [])]
            return "\n".join([*lines[: index + 1], *block, *lines[index + 1 :]])
    raise ValueError("round-1 prompt has no 'Task: ' line")


def replay_task(
    key: str, material: TaskMaterial, bare_prompt: str, round1: str, *, hint: bool
) -> dict[str, Any]:
    """Audit bare + round 1 + a synthetic round 2 (no change candidate) in the treatment lane."""

    candidate = material.source
    sha = hashlib.sha256(candidate.encode("utf-8")).hexdigest()
    task_id, _, trial = key.rpartition("__")
    with tempfile.TemporaryDirectory(prefix="treatment-replay-") as tmp:
        capture = Path(tmp) / "calls"
        capture.mkdir(mode=0o700)
        prompts = [
            ("without_nexus", bare_prompt),
            ("with_nexus", round1),
            ("with_nexus", self_heal_round(round1, extra=HINT_LINE if hint else "")),
        ]
        for arm, prompt in prompts:
            env = {
                "NEXUS_BENCH_ARM": arm,
                "NEXUS_BENCH_CAPTURE_KEY": key,
                "NEXUS_BENCH_CAPTURE_RUN_ID": REPLAY_RUN_ID,
            }
            record = capture_record(["--output-format", "json", "--print", prompt], "", env)
            record["ts"] = float(len(list(capture.iterdir())))  # keep the replay order
            write_record(record, str(capture))
        rows = [
            {"mode": "without_nexus", "task_id": task_id, "trial_index": trial, "model_calls": 1},
            {
                "mode": "with_nexus",
                "task_id": task_id,
                "trial_index": trial,
                "model_calls": 2,
                "lane": "treatment",
                "treatment_max_model_calls": 4,
                "treatment_candidates": {sha: candidate},
                "runner_candidate_sha256s": [sha, ""],
                "treatment_visible_outputs": {},
            },
        ]
        return audit_run(
            capture, {key: material}, rows=rows, run_id=REPLAY_RUN_ID, lane="treatment"
        )


def _materials(tasks_file: str, repo_root: Path) -> dict[str, TaskMaterial]:
    from scripts.bench.capability_ab_runner import (
        _hidden_test_for_visible_test,
        _prompt_capture_key,
        _resolve_task_files,
        load_tasks,
    )

    out: dict[str, TaskMaterial] = {}
    for task in load_tasks(tasks_file):
        try:
            target, visible = _resolve_task_files(repo_root, task, materialize_missing=True)
        except (OSError, NotImplementedError, ValueError):
            continue
        hidden = Path(_hidden_test_for_visible_test(visible))
        out[_prompt_capture_key(task)] = TaskMaterial(
            task_id=task.id,
            visible_test=Path(visible).read_text(encoding="utf-8"),
            hidden_test=hidden.read_text(encoding="utf-8") if hidden.is_file() else "",
            source=Path(target).read_text(encoding="utf-8"),
            task_desc=task.task_desc,
        )
    return out


def run_proof(run_dir: Path, materials: dict[str, TaskMaterial]) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {"h_round2_self_heal_passes": [], "h_round2_hint_fails": []}
    replayed = 0
    for calls in sorted(run_dir.glob("prompt_capture/run-*/calls")):
        captures = load_captures(calls)
        for key, material in sorted(materials.items()):
            bare = captures.get(("without_nexus", key), [])
            with_nexus = captures.get(("with_nexus", key), [])
            if not bare or not with_nexus:
                continue
            bare_prompt = str(bare[0].get("prompt") or "")
            round1 = str(with_nexus[0].get("prompt") or "")
            clean = replay_task(key, material, bare_prompt, round1, hint=False)
            if clean["status"] != "PASS":
                task = clean["tasks"][0] if clean["tasks"] else {}
                results["h_round2_self_heal_passes"].append(
                    f"{key}: {task.get('violations')} {task.get('treatment_round_findings', [])[:3]}"
                )
            hinted = replay_task(key, material, bare_prompt, round1, hint=True)
            violations = hinted["tasks"][0]["violations"] if hinted["tasks"] else []
            if hinted["status"] != "FAIL" or "treatment_round_not_allowed" not in violations:
                results["h_round2_hint_fails"].append(f"{key}: {hinted['status']} {violations}")
            replayed += 1
    if replayed == 0:
        results["h_round2_self_heal_passes"].append("no task had a bare and a with-Nexus capture")
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").strip().splitlines()[0])
    parser.add_argument("run_dir")
    parser.add_argument("--tasks-file", required=True)
    parser.add_argument("--repo-root", default=".")
    args = parser.parse_args(argv)
    results = run_proof(
        Path(args.run_dir), _materials(args.tasks_file, Path(args.repo_root).resolve())
    )
    failed = False
    for name, problems in results.items():
        print(
            f"{'PASS' if not problems else 'FAIL'} {name}"
            + (f" ({len(problems)})" if problems else "")
        )
        for item in problems[:20]:
            print("    ", item)
        failed = failed or bool(problems)
    print(json.dumps({name: len(problems) for name, problems in results.items()}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
