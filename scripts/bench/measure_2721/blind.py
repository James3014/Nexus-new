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
from typing import Any, Iterable, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721.common import read_jsonl, sha256_text, write_json, write_jsonl
from scripts.bench.measure_2721.leakage import FLAG_TEST_HUNKS_STRIPPED, strip_test_hunks

BLIND_SCHEMA = "nexus.measure_2721.blinded_candidates.v1"
SCORABLE_OUTCOMES = frozenset({"OK", "TIMEOUT", "MODEL_FAILED"})


def blind(rows: Iterable[dict[str, Any]], out: Path, arm_map_path: Path) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    mapping: dict[str, Any] = {}
    excluded: list[dict[str, Any]] = []
    used: set[str] = set()
    for row in rows:
        if row.get("infra") or row.get("outcome") not in SCORABLE_OUTCOMES:
            excluded.append({key: row.get(key) for key in ("arm", "run_id", "task_id", "repeat", "outcome")})
            continue
        diff = Path(row["diff_path"]).read_text(encoding="utf-8")
        if sha256_text(diff) != row["diff_sha256"]:
            raise RuntimeError(f"{row['run_id']}: diff changed after the run")
        opaque = secrets.token_hex(8)
        while opaque in used:
            opaque = secrets.token_hex(8)
        used.add(opaque)
        # Prereg v0.2 §8: test-path file blocks are removed before scoring, in every arm.
        scored, stripped_paths = strip_test_hunks(diff)
        target = out / "candidates" / f"{opaque}.diff"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(scored, encoding="utf-8")
        candidates.append({"opaque_id": opaque, "task_id": row["task_id"], "diff_sha256": sha256_text(scored)})
        flags = list(row.get("flags") or [])
        if stripped_paths:
            flags.append(FLAG_TEST_HUNKS_STRIPPED)
        mapping[opaque] = {"arm": row["arm"], "run_id": row["run_id"], "repeat": row["repeat"],
                           "task_id": row["task_id"], "flags": flags, "stripped_test_paths": stripped_paths,
                           "raw_diff_sha256": row["diff_sha256"], "scored_diff_sha256": sha256_text(scored)}
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
    args = parser.parse_args(argv)
    out, arm_map = Path(args.out).resolve(), Path(args.arm_map).resolve()
    if out in arm_map.parents or arm_map == out:
        parser.error("--arm-map must live outside --out (the scorer must not see it)")
    rows = [row for root in args.run_roots for row in read_jsonl(Path(root) / "rows.jsonl")]
    print(json.dumps(blind(rows, out, arm_map)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
