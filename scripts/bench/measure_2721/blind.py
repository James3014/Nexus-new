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
from all arms. Every other invalid row stays a candidate with the arm-neutral
flag ``RUN_INVALID_NOT_SOLVED``: not solved, kept in the denominator.

Which rows are infra (``exclusion_reason``; PREREG amendment 10 as clarified
by the scoring owner on #2721, 2026-10-20):

* BARE and NOOP rows (no ``worker_accepted`` field): the row's own ``infra``
  boolean, unchanged.
* NEXUS rows with ``worker_accepted: false`` (card create/commit, model probe,
  the Gateway refusing the worker request, a duplicate task): the model never
  ran for this row -> infra, re-run in all arms, then dropped.  A Gateway/Nexus
  refusal (``rule: NEXUS_NOT_ACCEPTED``) is reported per arm as Nexus
  reliability (``nexus_reliability: true``); a failure of the harness's own
  pre-checks is ``rule: HARNESS_NOT_SUBMITTED`` (``harness_failure: true``).
* NEXUS rows with ``worker_accepted: true``: infra ONLY for the model-side
  causes that make a BARE row infra too (``symmetric_infra_reasons``): the
  Claude attempt ended as infra (``claude_infra:*``, e.g. a 429 with a
  partial diff, provider unavailable), a provider infra marker in the worker
  error, a watchdog (host) event, a CLI time-limit mismatch or an unusable
  task venv, plus a stuck Gateway (PREREG §3.3) (``rule: SYMMETRIC_INFRA``).
  Any other failure after acceptance is Gateway/Nexus-side -- GATEWAY_ERROR,
  STATE_LEAK, a void such as SNAPSHOT_MISSING, TRACE_MISSING or
  LB_STATE_CHANGED -- and is NOT infra: the row stays a candidate with
  ``RUN_INVALID_NOT_SOLVED``.
* Rows of a runner run root that are not the final attempt of a resolved
  block (``runner.block_outcomes``: superseded by an infra re-run, or part of
  a block that never finished) are dropped before blinding (``dropped`` in the
  arm map), so only complete blocks reach the scorer.
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
    INFRA_ERROR_MARKERS,
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


# A NEXUS row not accepted counts as Nexus reliability only when the Gateway/Nexus
# refused (an error answer to card create/commit, probe or the worker request, or a
# duplicate task); a failure of the harness's own pre-checks (venv, Controller reset,
# state restore, a busy instance) is HARNESS_NOT_SUBMITTED.
NEXUS_REFUSAL_PREFIXES = ("PRE_SUBMIT_FAILURE:", "WORKER_NOT_ACCEPTED:", "DUPLICATE_TASK")
# Model-side infra causes a BARE row also has (arms.run_bare), checked on NEXUS rows.
SYMMETRIC_INFRA_FLAGS = ("CLI_TIMEOUT_MISMATCH", "VENV_NOT_USABLE")


def symmetric_infra_reasons(row: Mapping[str, Any]) -> list[str]:
    """Model/host-side infra causes in a NEXUS row that BARE treats as infra as well."""
    reasons = []
    if row.get("attempt_status") == "INFRA":
        reasons.append("MODEL_ATTEMPT_INFRA")
    if any(marker in str(row.get("error") or "") for marker in INFRA_ERROR_MARKERS):
        reasons.append("PROVIDER_INFRA_MARKER")
    if row.get("watchdog_event") is not None:
        reasons.append("WATCHDOG_EVENT")
    if row.get("gateway_connection_lost"):
        # The Gateway died at the connection layer (e.g. the watchdog killed it): INFRA.
        reasons.append("GATEWAY_CONNECTION_LOST")
    if row.get("gateway_stuck"):
        # PREREG §3.3: a stuck Gateway is INFRA (both arms re-run), whether or not
        # the watchdog fired first.
        reasons.append("GATEWAY_STUCK")
    reasons.extend(flag for flag in SYMMETRIC_INFRA_FLAGS if flag in (row.get("flags") or []))
    return reasons


def exclusion_reason(row: Mapping[str, Any]) -> tuple[str, str] | None:
    """(rule, reason) when the row is infra and leaves the candidate set, else None."""
    reason = str(row.get("void_reason") or row.get("outcome"))
    if "worker_accepted" not in row:  # BARE / NOOP: unchanged
        return ("ROW_INFRA", reason) if row.get("infra") else None
    if not row["worker_accepted"]:
        nexus_side = str(row.get("void_reason") or "").startswith(NEXUS_REFUSAL_PREFIXES) or \
            row.get("outcome") == "BLOCKED_EXTERNAL_TARGET_UNSUPPORTED"
        return ("NEXUS_NOT_ACCEPTED" if nexus_side else "HARNESS_NOT_SUBMITTED"), reason
    symmetric = symmetric_infra_reasons(row)
    return ("SYMMETRIC_INFRA", ",".join(symmetric)) if symmetric else None


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
          tasks: Mapping[str, Mapping[str, Any]], dropped: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
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
        excluded_by = exclusion_reason(row)
        if excluded_by is not None:
            # Only infra (amendment 10 split, module docstring) leaves the candidate
            # set; score_arms.py drops that task/repeat from all arms.
            rule, reason = excluded_by
            entry = {**{key: row.get(key) for key in ("arm", "run_id", "task_id", "repeat", "outcome")},
                     "infra": True, "reason": row.get("void_reason") or row.get("outcome")}
            if rule != "ROW_INFRA":
                entry.update(rule=rule, nexus_reliability=rule == "NEXUS_NOT_ACCEPTED")
                if rule == "HARNESS_NOT_SUBMITTED":
                    entry["harness_failure"] = True
                if rule == "SYMMETRIC_INFRA":
                    entry["symmetric_infra_reasons"] = reason.split(",")
            excluded.append(entry)
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
                              "map": mapping, "excluded": excluded, "dropped": list(dropped)}, mode=0o600)
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
    from scripts.bench.measure_2721.runner import block_outcomes

    rows, dropped = [], []
    for root in args.run_roots:
        outcome = block_outcomes(Path(root))
        for row in read_jsonl(Path(root) / "rows.jsonl"):
            if outcome is not None and row.get("run_id") not in outcome["counted"]:
                # Only the final attempt of a resolved block counts (runner.py).
                dropped.append({key: row.get(key) for key in ("arm", "run_id", "task_id", "repeat", "infra")} |
                               {"reason": outcome["dropped"].get(row.get("run_id"), "NOT_IN_RUNNER_PROGRESS")})
                continue
            rows.append(row)
    tasks = {task["task_id"]: task for task in read_jsonl(args.manifest)}
    print(json.dumps(blind(rows, out, arm_map, tasks, dropped)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
