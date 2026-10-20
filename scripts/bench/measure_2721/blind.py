"""Blind the candidates for scoring.

Reads ``rows.jsonl`` from one or more run roots and writes:
* ``<out>/candidates/<opaque_id>.diff`` (test-path file blocks stripped,
  prereg v0.2 §8) and ``<out>/candidates.jsonl``
  (``opaque_id``, ``task_id``, ``repeat``, ``diff_sha256``, ``scoring_flags``)
  in a random order: the scorer's only input (``score_arms.py run``);
* ``--arm-map`` (mode 0600, kept by the custodian named in PREREG, not by the scorer):
  opaque id -> arm, run id, repeat, plus the sha256 of candidates.jsonl so
  the mapping is bound to exactly that candidate set.

Only infra rows are not candidates; they are listed in the arm map under
``excluded`` (``infra: true``, reason), so the S4 rule drops that task/repeat
from all arms. Every other invalid row (TAMPERED, a non-infra Gateway error,
STATE_LEAK, a void reason) stays a candidate with the arm-neutral flag
``RUN_INVALID_NOT_SOLVED``: not solved, kept in the denominator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import secrets
import sys
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.common import (
    read_diff,
    read_jsonl,
    sha256_text,
    write_diff,
    write_json,
    write_jsonl,
)
from scripts.bench.measure_2721.leakage import FLAG_PATCH_DOES_NOT_APPLY, filter_candidate

BLIND_SCHEMA = "nexus.measure_2721.blinded_candidates.v1"
SCORABLE_OUTCOMES = frozenset({"OK", "TIMEOUT", "MODEL_FAILED"})
# Flags the scorer may see (identical filter in every arm, so they reveal no arm).
FLAG_RUN_INVALID_NOT_SOLVED = "RUN_INVALID_NOT_SOLVED"
SCORER_VISIBLE_FLAGS = frozenset({"HARNESS_TAMPER", "OUT_OF_SCOPE_STRIPPED", "PATCH_DOES_NOT_APPLY",
                                  FLAG_RUN_INVALID_NOT_SOLVED})


def run_invalid_reason(row: Mapping[str, Any]) -> str | None:
    """Why a non-infra row cannot count as a solve (None: a normal candidate)."""
    if row.get("void_reason"):
        return f"VOID:{row['void_reason']}"
    if "STATE_LEAK" in (row.get("flags") or []):
        return "STATE_LEAK"
    if row.get("non_model_solve_path"):
        return "NON_MODEL_SOLVE_PATH"
    if row.get("outcome") not in SCORABLE_OUTCOMES:
        return f"OUTCOME:{row.get('outcome')}"
    return None


def applies_to_base(diff: str, task: Mapping[str, Any]) -> bool:
    """``git apply --check`` of the scored diff on a fresh copy of the base."""
    import subprocess
    import tempfile

    from scripts.bench.measure_2721.materialize import checkout_base

    if not diff.strip():
        return True
    with tempfile.TemporaryDirectory(prefix="m2721-apply-") as tmp:
        tree = Path(tmp) / "tree"
        checkout_base(Path(task["base_checkout"]), task["base_commit"], tree)
        patch = Path(tmp) / "c.diff"
        patch.write_bytes(diff.encode("utf-8", errors="surrogateescape"))
        return subprocess.run(["git", "apply", "--check", "--binary", str(patch)], cwd=tree,
                              capture_output=True).returncode == 0


def blind(rows: Iterable[dict[str, Any]], out: Path, arm_map_path: Path,
          tasks: Mapping[str, Mapping[str, Any]]) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    mapping: dict[str, Any] = {}
    excluded: list[dict[str, Any]] = []
    used: set[str] = set()
    rows = list(rows)
    hashes = {row["read_roots_sha256"] for row in rows if row.get("read_roots_sha256")}
    if len(hashes) > 1:
        # Every arm must have run with the Gateway's own READ_ROOTS (L2).
        raise RuntimeError(f"READ_ROOTS_DIFFER_ACROSS_ARMS: {sorted(hashes)}")
    pending: list[tuple[str, str]] = []  # (opaque id, scored diff), written after the shuffle
    for row in rows:
        if row.get("infra"):
            # Only true infra (after the harness's both-arm model re-runs) leaves the
            # candidate set; score_arms.py drops that task/repeat from all arms.
            excluded.append({**{key: row.get(key) for key in ("arm", "run_id", "task_id", "repeat", "outcome")},
                             "infra": True, "reason": row.get("void_reason") or row.get("outcome")})
            continue
        invalid = run_invalid_reason(row)
        diff = ""
        if row.get("diff_path") and (invalid is None or Path(row["diff_path"]).is_file()):
            diff = read_diff(Path(row["diff_path"]))
            if sha256_text(diff) != row["diff_sha256"]:
                raise RuntimeError(f"{row['run_id']}: diff changed after the run")
        opaque = secrets.token_hex(8)
        while opaque in used:
            opaque = secrets.token_hex(8)
        used.add(opaque)
        # Prereg §8 / gap F14, same for every arm: tamper check on the raw diff,
        # then strip test-path blocks, then strip out-of-scope blocks.
        task = tasks[row["task_id"]]
        filtered = filter_candidate(diff, task["scope"])
        scored = filtered["scored_diff"]
        flags = [*(row.get("flags") or []), *filtered["flags"]]
        if not applies_to_base(scored, task):
            flags.append(FLAG_PATCH_DOES_NOT_APPLY)
        if invalid is not None:
            # A non-infra invalid run (TAMPERED, a non-infra Gateway error, a state
            # leak, a void reason) stays a candidate: not solved, in the denominator.
            flags.append(FLAG_RUN_INVALID_NOT_SOLVED)
        pending.append((opaque, scored))
        # Scorer-visible: the repeat (S4 re-runs a task/repeat in all arms) and only the
        # pre-registered scoring flags (amendment 8.3, applied blind by score_arms.py).
        # Arm-specific harness flags stay in the arm map.
        candidates.append({"opaque_id": opaque, "task_id": row["task_id"], "repeat": row["repeat"],
                           "diff_sha256": sha256_text(scored),
                           "scoring_flags": sorted(set(flags) & SCORER_VISIBLE_FLAGS)})
        mapping[opaque] = {
            "arm": row["arm"], "run_id": row["run_id"], "repeat": row["repeat"], "task_id": row["task_id"],
            "flags": flags, "outcome": row.get("outcome"), "run_invalid_reason": invalid,
            "tamper_paths": filtered["tamper_paths"],
            "stripped_test_paths": filtered["stripped_test_paths"],
            "stripped_out_of_scope_paths": filtered["stripped_out_of_scope_paths"],
            "raw_diff_sha256": row.get("diff_sha256"), "scored_diff_sha256": sha256_text(scored),
        }
    rng = secrets.SystemRandom()
    rng.shuffle(candidates)
    rng.shuffle(pending)  # file creation order (mtime, inode) must not cluster by arm
    for opaque, scored in pending:
        write_diff(out / "candidates" / f"{opaque}.diff", scored)
    write_jsonl(out / "candidates.jsonl", candidates)
    candidates_sha = hashlib.sha256((out / "candidates.jsonl").read_bytes()).hexdigest()
    write_json(arm_map_path, {"schema": BLIND_SCHEMA, "candidates_jsonl_sha256": candidates_sha,
                              "map": mapping, "excluded": excluded}, mode=0o600)
    return {"candidates": len(candidates), "excluded": len(excluded), "candidates_jsonl_sha256": candidates_sha}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Blind #2721 candidates for scoring")
    parser.add_argument("--run-roots", nargs="+", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--arm-map", required=True, help="path for the arm mapping (outside --out)")
    parser.add_argument("--manifest", required=True, help="materialized manifest.jsonl (scope, base)")
    args = parser.parse_args(argv)
    out, arm_map = Path(args.out).resolve(), Path(args.arm_map).resolve()
    if out in arm_map.parents or arm_map == out:
        parser.error("--arm-map must live outside --out (the scorer must not see it)")
    rows = [row for root in args.run_roots for row in read_jsonl(Path(root) / "rows.jsonl")]
    tasks = {task["task_id"]: task for task in read_jsonl(args.manifest)}
    print(json.dumps(blind(rows, out, arm_map, tasks)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
