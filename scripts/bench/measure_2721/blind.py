"""Blind the candidates for scoring.

Reads ``rows.jsonl`` from one or more run roots and writes:
* ``<out>/candidates/<opaque_id>.diff`` (test-path file blocks stripped,
  prereg v0.2 §8) and ``<out>/candidates.jsonl``
  (``opaque_id``, ``task_id``, ``diff_sha256``) in a random order: the
  scorer's only input;
* ``--arm-map`` (mode 0600, kept by workspace-b6, not by the scorer):
  opaque id -> arm, run id, repeat, plus the sha256 of candidates.jsonl so
  the mapping is bound to exactly that candidate set.

Infra rows and blocked rows are not candidates; they are listed in the arm
map under ``excluded`` with their reason, so the S4 re-run rule can act.
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
    for row in rows:
        if row.get("infra") or row.get("outcome") not in SCORABLE_OUTCOMES:
            excluded.append({key: row.get(key) for key in ("arm", "run_id", "task_id", "repeat", "outcome")})
            continue
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
        target = out / "candidates" / f"{opaque}.diff"
        target.parent.mkdir(parents=True, exist_ok=True)
        write_diff(target, scored)
        candidates.append({"opaque_id": opaque, "task_id": row["task_id"], "diff_sha256": sha256_text(scored)})
        mapping[opaque] = {
            "arm": row["arm"], "run_id": row["run_id"], "repeat": row["repeat"], "task_id": row["task_id"],
            "flags": flags,
            "tamper_paths": filtered["tamper_paths"],
            "stripped_test_paths": filtered["stripped_test_paths"],
            "stripped_out_of_scope_paths": filtered["stripped_out_of_scope_paths"],
            "raw_diff_sha256": row["diff_sha256"], "scored_diff_sha256": sha256_text(scored),
        }
    secrets.SystemRandom().shuffle(candidates)
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
