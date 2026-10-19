"""Post-verification learning write-back for P1 workers (measurement only, #2721).

P1 reads memory (FindingsMemoryStore episode cards) and Belief
(``repair_outcome:file:<path>``) before the worker runs, but nothing wrote them back
after a run, so a learning loop could never form.  This module writes one findings
card and one Belief entry per changed file after Nexus's own verifier finishes.

Two measurement switches, both unset on the live Gateway (behaviour unchanged there):

* ``NEXUS_LEARNING_WRITEBACK=1`` enables the write-back (learning phase L-A).
* ``NEXUS_STATE_READ_ONLY=1`` skips every learning-state write, this one included
  (held-out phase L-B); see :func:`state_read_only`, also honoured by the stores.

Content rule (PREREG_2721 §10 v0.6): the card may carry the task text, the changed
files and Nexus's *own* verifier results (commands it ran while working).  It never
carries hidden-test (F2P/P2P) content or scorer results; those do not exist in this
process, and nothing here reads them.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Iterable, Mapping

from nexus.core.state_root import STATE_READ_ONLY_ENV, state_read_only

logger = logging.getLogger(__name__)

WRITEBACK_ENV = "NEXUS_LEARNING_WRITEBACK"
READ_ONLY_ENV = STATE_READ_ONLY_ENV
SCHEMA = "nexus.p1_learning_writeback.v1"
_MAX_TEXT = 4000
_MAX_FILES = 50
_MAX_VERIFIERS = 8
_PASS_CONFIDENCE = 0.9
_FAIL_CONFIDENCE = 0.1


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip() == "1"


def writeback_enabled() -> bool:
    return _flag(WRITEBACK_ENV) and not state_read_only()


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _changed_files(candidate: Any) -> list[str]:
    files: list[str] = []
    for key in ("changed_files", "untracked_files"):
        for path in _get(candidate, key, None) or ():
            text = str(path).strip()
            if text and text not in files:
                files.append(text)
    return sorted(files)[:_MAX_FILES]


# Verifier commands that check the diff but run no test: they cannot make a run PASSED
# (#2721 gap review: L-A must not store unverified "successes").
_NON_TEST_VERIFIERS = frozenset({"git diff --check", "code_integrity_v1"})


def _has_real_test(verifiers: list[dict[str, Any]]) -> bool:
    return any(
        str(item.get("command") or "").strip() not in _NON_TEST_VERIFIERS
        and str(item.get("command") or "").strip()
        for item in verifiers
    )


def _verifier_results(verified: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in list(_get(verified, "verifier_evidence", None) or ())[:_MAX_VERIFIERS]:
        out.append({
            "command": str(_get(item, "command", "") or "")[:300],
            "status": str(_get(item, "status", "") or ""),
            "exit_code": _get(item, "exit_code", None),
        })
    return out


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def run_learning_writeback(
    *,
    contract: Any,
    candidate: Any,
    verified: Any,
    resolution_verdict: str,
    fail_to_pass_status: str | None = None,
    memory_store_factory: Any = None,
    belief_engine_factory: Any = None,
) -> dict[str, Any]:
    """Write the findings card and Belief entries; return a bounded observation.

    Never raises: a write-back failure must not change the task outcome.  The
    observation names what was written (ids, keys, counts), never task text.
    """
    observation: dict[str, Any] = {
        "schema": SCHEMA,
        "enabled": False,
        "read_only": state_read_only(),
        "card_written": False,
        "belief_keys": [],
    }
    if not writeback_enabled():
        observation["skip_reason"] = "READ_ONLY" if state_read_only() else "DISABLED"
        return observation
    observation["enabled"] = True
    try:
        from nexus.core.state_root import configured_state_root

        if configured_state_root() is None:
            # Without NEXUS_STATE_ROOT the task root is the candidate worktree itself:
            # writing .nexus/ there would leak into the candidate. Measurement only.
            observation["skip_reason"] = "NO_STATE_ROOT"
            return observation
        from nexus.core.belief_engine import BeliefEngine, repair_target_key
        from nexus.core.state_root import persistent_state_root
        from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore

        task_id = str(_get(contract, "task_id", "") or "")
        objective = str(_get(contract, "objective", "") or "")[:_MAX_TEXT]
        files = _changed_files(candidate)
        verifiers = _verifier_results(verified)
        verifier_passed = bool(_get(verified, "verifier_gate_passed", False))
        # A task whose acceptance requires fail-to-pass counts as PASSED only once the
        # probe recorded VERIFIED (finalize calls this after the probe for such tasks).
        # The probe status decides the outcome only; it is not written to the card.
        if not _has_real_test(verifiers) or str(fail_to_pass_status) == "NOT_RUN":
            # Only diff checks ran, or a required fail-to-pass probe never ran: no
            # evidence either way.  Card says so; no Belief entry is written.
            outcome = "UNVERIFIED"
        elif (
            str(resolution_verdict) == "PROVEN"
            and verifier_passed
            and (fail_to_pass_status is None or str(fail_to_pass_status) == "VERIFIED")
        ):
            outcome = "PASSED"
        else:
            outcome = "FAILED"
        # Same root the P1 memory reader uses: workspace_root = the task's own worktree,
        # contract.target_repo_root.  (target_worktree_root is the shared targets
        # directory, its parent, which persistent_state_root does not rebase.)
        task_root = _get(contract, "target_repo_root", "") or ""
        if not str(task_root).strip():
            observation["skip_reason"] = "NO_TASK_ROOT"
            return observation
        task_path = Path(str(task_root)).resolve()
        root = persistent_state_root(Path(str(task_root))).resolve()
        if root == task_path or root.is_relative_to(task_path) or not root.is_absolute():
            # Not rebased to NEXUS_STATE_ROOT (not a Gateway task worktree): never
            # write into the candidate's own tree.
            observation["skip_reason"] = "ROOT_NOT_REBASED"
            return observation
        observation["store_root"] = str(root)

        body = "\n".join([
            f"Task: {objective}",
            f"Outcome (Nexus's own verifiers): {outcome}",
            "Changed files: " + (", ".join(files) or "(none)"),
            "Verifier results: " + json.dumps(verifiers, sort_keys=True),
        ])
        card = FindingsCard(
            kind="episodes",
            title=f"P1 repair {outcome.lower()}: {objective[:80]}",
            scope="task",
            tags=["p1_writeback", outcome.lower()],
            stage="experiment",
            confidence="medium",
            evidence_paths=list(files),
            retrieval_hints=list(files) + [objective[:200]],
            body=body,
            task_id=task_id,
            extra={
                "schema": SCHEMA,
                "outcome": outcome,
                "attempt_verdict": str(resolution_verdict),
                "verifier_gate_passed": verifier_passed,
                "candidate_state_hash": str(_get(verified, "candidate_state_hash", "") or ""),
            },
        )
        store = (memory_store_factory or FindingsMemoryStore)(root)
        store.write(card)
        observation["card_written"] = True
        observation["card_id"] = card.id
        observation["card_sha256"] = _sha256_json(card.to_dict() | {"updated_at": "", "extra": {}})

        engine = (belief_engine_factory or BeliefEngine)(root / ".nexus" / "belief_state.json")
        confidence = _PASS_CONFIDENCE if outcome == "PASSED" else _FAIL_CONFIDENCE
        if outcome == "UNVERIFIED":
            files_for_belief: list[str] = []
        else:
            files_for_belief = files
        evidence_id = f"p1_writeback:{task_id}:{card.id}"
        keys: list[str] = []
        for path in files_for_belief:
            key = repair_target_key(path)
            if not key:
                continue
            engine.update_belief(
                task_id=task_id, assumption=key, confidence=confidence, evidence_id=evidence_id
            )
            keys.append(key)
        observation["belief_keys"] = keys
        observation["belief_confidence"] = confidence
        observation["outcome"] = outcome
        observation["changed_file_count"] = len(files)
        observation["verifier_count"] = len(verifiers)
    except Exception as exc:  # noqa: BLE001 - write-back must not fail the task
        logger.warning("P1 learning write-back failed: %s", type(exc).__name__)
        observation["error_type"] = type(exc).__name__
    return observation


__all__: Iterable[str] = (
    "READ_ONLY_ENV",
    "SCHEMA",
    "WRITEBACK_ENV",
    "run_learning_writeback",
    "state_read_only",
    "writeback_enabled",
)
