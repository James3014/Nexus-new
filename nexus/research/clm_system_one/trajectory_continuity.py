from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

STEP_SCHEMA = "nexus.clm_trajectory_step.v1"
STEP_RESULT_SCHEMA = "nexus.clm_trajectory_step_result.v1"
OUTCOME_SCHEMA = "nexus.clm_trajectory_outcome_binding.v1"
READINESS_SCHEMA = "nexus.clm_trajectory_corpus_readiness.v1"
CHECKPOINT_SCHEMA = "nexus.research_experiment_checkpoint.v1"

_ALLOWED_CHECKPOINT_STATES = {
    "ACTIVE",
    "WAITING_FOR_DATA",
    "READY_TO_REAUDIT",
    "TERMINAL",
}
_STRONG_LABELS = {"ISOLATED_VERIFIER", "MECHANICAL_GATE"}
_FORBIDDEN_PRE_ACTION_KEYS = {
    "final_verifier_status",
    "final_outcome",
    "final_candidate_status",
    "trajectory_outcome",
}


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: Any) -> str:
    return _sha256_bytes(_canonical_json(value).encode("utf-8"))


def _write_create_only(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise RuntimeError(f"immutable evidence collision: {path}")
        return
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(tmp_path, path)
        except FileExistsError:
            if path.read_bytes() != payload:
                raise RuntimeError(f"immutable evidence collision: {path}")
    finally:
        tmp_path.unlink(missing_ok=True)


def _atomic_replace(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp_path = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)
    finally:
        tmp_path.unlink(missing_ok=True)


def _json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trajectory_storage_key(trajectory_id: str) -> str:
    value = str(trajectory_id or "").strip()
    if not value:
        raise ValueError("trajectory_id is required")
    return _sha256_bytes(value.encode("utf-8"))


def resolve_research_evidence_root(repo_root: str | Path) -> Path:
    override = os.getenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return (
        Path(repo_root).expanduser().resolve()
        / ".nexus"
        / "research"
        / "clm_system_one"
        / "candidate_evidence"
    ).resolve()


def _contains_forbidden_future_key(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key) in _FORBIDDEN_PRE_ACTION_KEYS:
                return True
            if _contains_forbidden_future_key(child):
                return True
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return any(_contains_forbidden_future_key(child) for child in value)
    return False


@dataclass(frozen=True)
class TrajectoryStepRef:
    trajectory_id: str
    step_index: int
    step_sha256: str
    step_ref: str


def seal_trajectory_step(
    *,
    evidence_root: str | Path,
    task_id: str,
    trajectory_id: str,
    attempt_id: str,
    candidate_id: str,
    step_index: int,
    source_revision: str,
    pre_action_state: Any,
    action_type: str,
    action_payload: Any,
    observed_at: str | None = None,
) -> TrajectoryStepRef:
    root = Path(evidence_root).expanduser().resolve()
    if step_index < 0:
        raise ValueError("step_index must be non-negative")
    if not task_id or not trajectory_id or not attempt_id or not candidate_id:
        raise ValueError("task/trajectory/attempt/candidate identity is required")
    if _contains_forbidden_future_key(pre_action_state):
        raise ValueError("pre-action state contains forbidden final-outcome evidence")
    state_sha = _sha256_json(pre_action_state)
    action_sha = _sha256_json(action_payload)
    state_path = root / "trajectory" / "state" / state_sha[:2] / f"{state_sha}.json"
    action_path = root / "trajectory" / "action" / action_sha[:2] / f"{action_sha}.json"
    _write_create_only(state_path, _json_bytes(pre_action_state))
    _write_create_only(action_path, _json_bytes(action_payload))

    steps_dir = root / "trajectory" / "steps" / _trajectory_storage_key(trajectory_id)
    previous_sha = ""
    if step_index:
        previous_path = steps_dir / f"{step_index - 1:08d}.json"
        if not previous_path.exists():
            raise ValueError("trajectory step order gap")
        previous = json.loads(previous_path.read_text(encoding="utf-8"))
        previous_sha = str(previous.get("record_sha256") or "")
    step_body = {
        "schema": STEP_SCHEMA,
        "task_id": task_id,
        "trajectory_id": trajectory_id,
        "attempt_id": attempt_id,
        "candidate_id": candidate_id,
        "step_index": step_index,
        "source_revision": source_revision,
        "pre_action_state_sha256": state_sha,
        "pre_action_state_ref": str(state_path.relative_to(root)),
        "action_type": action_type,
        "action_sha256": action_sha,
        "action_ref": str(action_path.relative_to(root)),
        "parent_step_sha256": previous_sha,
        "observed_at": observed_at or _now(),
        "sealed_before_result": True,
    }
    step_sha = _sha256_json(step_body)
    step = dict(step_body, record_sha256=step_sha)
    step_path = steps_dir / f"{step_index:08d}.json"
    _write_create_only(step_path, _json_bytes(step))
    return TrajectoryStepRef(trajectory_id, step_index, step_sha, str(step_path.relative_to(root)))


def bind_trajectory_step_result(
    *,
    evidence_root: str | Path,
    step_ref: TrajectoryStepRef,
    action_result: Any,
    observed_at: str | None = None,
) -> str:
    root = Path(evidence_root).expanduser().resolve()
    step_path = root / step_ref.step_ref
    if not step_path.exists():
        raise ValueError("step_ref not found")
    step = json.loads(step_path.read_text(encoding="utf-8"))
    if step.get("record_sha256") != step_ref.step_sha256:
        raise ValueError("step_ref hash mismatch")
    result_sha = _sha256_json(action_result)
    result_blob = root / "trajectory" / "result" / result_sha[:2] / f"{result_sha}.json"
    _write_create_only(result_blob, _json_bytes(action_result))
    body = {
        "schema": STEP_RESULT_SCHEMA,
        "trajectory_id": step_ref.trajectory_id,
        "step_index": step_ref.step_index,
        "step_sha256": step_ref.step_sha256,
        "action_result_sha256": result_sha,
        "action_result_ref": str(result_blob.relative_to(root)),
        "observed_at": observed_at or _now(),
    }
    record_sha = _sha256_json(body)
    record = dict(body, record_sha256=record_sha)
    record_path = (
        root
        / "trajectory"
        / "step_results"
        / _trajectory_storage_key(step_ref.trajectory_id)
        / f"{step_ref.step_index:08d}.json"
    )
    _write_create_only(record_path, _json_bytes(record))
    return str(record_path.relative_to(root))


def bind_trajectory_outcome(
    *,
    evidence_root: str | Path,
    trajectory_id: str,
    candidate_evidence_ref: str,
) -> str:
    root = Path(evidence_root).expanduser().resolve()
    candidate_path = (root / candidate_evidence_ref).resolve()
    if root not in candidate_path.parents or not candidate_path.exists():
        raise ValueError("candidate evidence ref is invalid")
    candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
    if not candidate.get("dataset_eligible"):
        raise ValueError("candidate evidence is not dataset eligible")
    label_quality = str(candidate.get("label_quality") or "")
    verifier_status = str(candidate.get("verifier_status") or "")
    if label_quality not in _STRONG_LABELS or verifier_status not in {"PASS", "FAIL"}:
        raise ValueError("candidate evidence is not strong verifier truth")
    body = {
        "schema": OUTCOME_SCHEMA,
        "trajectory_id": trajectory_id,
        "task_id": str(candidate.get("task_id") or ""),
        "attempt_id": str(candidate.get("attempt_id") or ""),
        "candidate_id": str(candidate.get("candidate_id") or ""),
        "candidate_evidence_ref": candidate_evidence_ref,
        "candidate_record_sha256": str(candidate.get("record_sha256") or ""),
        "verifier_status": verifier_status,
        "label_quality": label_quality,
        "bound_at": _now(),
    }
    record_sha = _sha256_json(body)
    record = dict(body, record_sha256=record_sha)
    path = root / "trajectory" / "outcomes" / f"{_trajectory_storage_key(trajectory_id)}.json"
    _write_create_only(path, _json_bytes(record))
    return str(path.relative_to(root))


def _trajectory_complete(root: Path, trajectory_id: str) -> tuple[bool, list[str]]:
    steps_dir = root / "trajectory" / "steps" / _trajectory_storage_key(trajectory_id)
    result_dir = root / "trajectory" / "step_results" / _trajectory_storage_key(trajectory_id)
    if not steps_dir.exists():
        return False, ["missing_steps"]
    steps = sorted(steps_dir.glob("*.json"))
    if not steps:
        return False, ["missing_steps"]
    problems: list[str] = []
    previous_sha = ""
    for expected, step_path in enumerate(steps):
        step = json.loads(step_path.read_text(encoding="utf-8"))
        if step.get("step_index") != expected:
            problems.append("step_index_gap")
        if str(step.get("parent_step_sha256") or "") != previous_sha:
            problems.append("parent_step_mismatch")
        if step.get("sealed_before_result") is not True:
            problems.append("unsealed_pre_action_state")
        previous_sha = str(step.get("record_sha256") or "")
        result_path = result_dir / f"{expected:08d}.json"
        if not result_path.exists():
            problems.append("missing_step_result")
            continue
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if result.get("step_sha256") != previous_sha:
            problems.append("step_result_binding_mismatch")
    return not problems, sorted(set(problems))


def _labels_by_group(rows: Sequence[Mapping[str, Any]], key: str) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if not value:
            continue
        groups.setdefault(value, set()).add(str(row.get("verifier_status") or ""))
    return groups


def _two_group_binary_split_possible(groups: Mapping[str, set[str]]) -> bool:
    binary = [key for key, labels in groups.items() if {"PASS", "FAIL"} <= labels]
    return len(binary) >= 2


def project_corpus_readiness(
    *,
    evidence_root: str | Path,
    holdout_task_ids: Sequence[str] = (),
    task_family_by_task: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    root = Path(evidence_root).expanduser().resolve()
    holdout = set(holdout_task_ids)
    families = dict(task_family_by_task or {})
    valid: list[dict[str, Any]] = []
    malformed: list[str] = []
    leakage: list[str] = []
    overlap: list[str] = []
    outcomes_dir = root / "trajectory" / "outcomes"
    if outcomes_dir.exists():
        for path in sorted(outcomes_dir.glob("*.json")):
            try:
                outcome = json.loads(path.read_text(encoding="utf-8"))
                trajectory_id = str(outcome.get("trajectory_id") or "")
                complete, problems = _trajectory_complete(root, trajectory_id)
                if not complete:
                    leakage.extend(f"{trajectory_id}:{problem}" for problem in problems)
                    continue
                candidate_path = (root / str(outcome.get("candidate_evidence_ref") or "")).resolve()
                if root not in candidate_path.parents or not candidate_path.exists():
                    malformed.append(f"{trajectory_id}:candidate_ref_invalid")
                    continue
                candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
                if candidate.get("record_sha256") != outcome.get("candidate_record_sha256"):
                    malformed.append(f"{trajectory_id}:candidate_hash_mismatch")
                    continue
                if not candidate.get("dataset_eligible"):
                    malformed.append(f"{trajectory_id}:candidate_not_eligible")
                    continue
                task_id = str(outcome.get("task_id") or "")
                if task_id in holdout:
                    overlap.append(trajectory_id)
                    continue
                valid.append(dict(outcome))
            except Exception:
                malformed.append(path.name)

    pass_count = sum(1 for row in valid if row.get("verifier_status") == "PASS")
    fail_count = sum(1 for row in valid if row.get("verifier_status") == "FAIL")
    task_groups = _labels_by_group(valid, "task_id")
    task_split = _two_group_binary_split_possible(task_groups)
    family_rows = [
        dict(row, task_family=families.get(str(row.get("task_id") or ""), ""))
        for row in valid
        if families.get(str(row.get("task_id") or ""))
    ]
    family_groups = _labels_by_group(family_rows, "task_family")
    family_split = bool(family_rows) and _two_group_binary_split_possible(family_groups)
    blockers: list[str] = []
    if not valid:
        blockers.append("no_strong_label_trajectories")
    if not task_split:
        blockers.append("task_disjoint_split_unavailable")
    if leakage:
        blockers.append("trajectory_leakage_or_binding_problem")
    if overlap:
        blockers.append("holdout_overlap")
    if malformed:
        blockers.append("malformed_evidence")
    disposition = (
        "READY_TO_REAUDIT" if not blockers and pass_count and fail_count else "WAITING_FOR_DATA"
    )
    provenance: dict[str, int] = {}
    for row in valid:
        label = str(row.get("label_quality") or "")
        provenance[label] = provenance.get(label, 0) + 1
    return {
        "schema": READINESS_SCHEMA,
        "disposition": disposition,
        "eligible_strong_label_trajectories": len(valid),
        "pass_trajectories": pass_count,
        "fail_trajectories": fail_count,
        "unknown_trajectories": 0,
        "independent_task_count": len(task_groups),
        "task_family_count": len(family_groups),
        "strong_label_provenance": provenance,
        "task_disjoint_split_possible": task_split,
        "family_disjoint_split_possible": family_split,
        "holdout_overlap_trajectories": overlap,
        "leakage_findings": leakage,
        "malformed_evidence": malformed,
        "blockers": blockers,
        "observed_at": _now(),
    }


def write_experiment_checkpoint(
    *,
    evidence_root: str | Path,
    experiment_id: str,
    track_id: str,
    status: str,
    claim_ceiling: str,
    source_revision: str,
    holdout_manifest_ref: str,
    holdout_manifest_sha256: str,
    corpus_audit_ref: str,
    corpus_audit_sha256: str,
    blockers: Sequence[str],
    resume_gate: str,
    next_allowed_action: str,
    evidence_refs: Sequence[str] = (),
    updated_at: str | None = None,
) -> dict[str, Any]:
    if status not in _ALLOWED_CHECKPOINT_STATES:
        raise ValueError("invalid checkpoint status")
    if status == "READY_TO_REAUDIT" and next_allowed_action != "T0_T1_REAUDIT_ONLY":
        raise ValueError("READY_TO_REAUDIT may only unlock T0_T1_REAUDIT_ONLY")
    if "TRAIN" in next_allowed_action.upper() or "FINE_TUNE" in next_allowed_action.upper():
        raise ValueError("checkpoint may not auto-chain into training")
    root = Path(evidence_root).expanduser().resolve()
    checkpoint_body = {
        "schema": CHECKPOINT_SCHEMA,
        "experiment_id": experiment_id,
        "track_id": track_id,
        "status": status,
        "claim_ceiling": claim_ceiling,
        "source_revision": source_revision,
        "holdout_manifest_ref": holdout_manifest_ref,
        "holdout_manifest_sha256": holdout_manifest_sha256,
        "corpus_audit_ref": corpus_audit_ref,
        "corpus_audit_sha256": corpus_audit_sha256,
        "blockers": list(blockers),
        "resume_gate": resume_gate,
        "next_allowed_action": next_allowed_action,
        "auto_chain": False,
        "evidence_refs": list(evidence_refs),
        "updated_at": updated_at or _now(),
    }
    digest = _sha256_json(checkpoint_body)
    checkpoint = dict(checkpoint_body, checkpoint_sha256=digest)
    slug = f"{experiment_id}__{track_id}"
    base = root / "experiments" / slug
    history_path = base / "history" / f"{digest}.json"
    _write_create_only(history_path, _json_bytes(checkpoint))
    pointer = {
        "schema": "nexus.research_experiment_checkpoint_pointer.v1",
        "experiment_id": experiment_id,
        "track_id": track_id,
        "checkpoint_sha256": digest,
        "checkpoint_ref": str(history_path.relative_to(root)),
        "updated_at": checkpoint["updated_at"],
    }
    _atomic_replace(base / "checkpoint.json", _json_bytes(pointer))
    return checkpoint


def read_experiment_checkpoint(
    *,
    evidence_root: str | Path,
    experiment_id: str,
    track_id: str,
) -> dict[str, Any]:
    root = Path(evidence_root).expanduser().resolve()
    slug = f"{experiment_id}__{track_id}"
    pointer_path = root / "experiments" / slug / "checkpoint.json"
    pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    checkpoint_path = root / str(pointer.get("checkpoint_ref") or "")
    checkpoint = json.loads(checkpoint_path.read_text(encoding="utf-8"))
    digest = str(checkpoint.get("checkpoint_sha256") or "")
    body = dict(checkpoint)
    body.pop("checkpoint_sha256", None)
    if _sha256_json(body) != digest or digest != pointer.get("checkpoint_sha256"):
        raise RuntimeError("checkpoint digest mismatch")
    return checkpoint


def refresh_checkpoint_from_readiness(
    *,
    evidence_root: str | Path,
    experiment_id: str,
    track_id: str,
    readiness: Mapping[str, Any],
    claim_ceiling: str,
    source_revision: str,
    holdout_manifest_ref: str,
    holdout_manifest_sha256: str,
    corpus_audit_ref: str,
    corpus_audit_sha256: str,
    evidence_refs: Sequence[str] = (),
) -> dict[str, Any]:
    disposition = str(readiness.get("disposition") or "WAITING_FOR_DATA")
    status = "READY_TO_REAUDIT" if disposition == "READY_TO_REAUDIT" else "WAITING_FOR_DATA"
    return write_experiment_checkpoint(
        evidence_root=evidence_root,
        experiment_id=experiment_id,
        track_id=track_id,
        status=status,
        claim_ceiling=claim_ceiling,
        source_revision=source_revision,
        holdout_manifest_ref=holdout_manifest_ref,
        holdout_manifest_sha256=holdout_manifest_sha256,
        corpus_audit_ref=corpus_audit_ref,
        corpus_audit_sha256=corpus_audit_sha256,
        blockers=list(readiness.get("blockers") or []),
        resume_gate="TRAJECTORY_CORPUS_READY_FOR_T1_REAUDIT",
        next_allowed_action=(
            "T0_T1_REAUDIT_ONLY"
            if status == "READY_TO_REAUDIT"
            else "WAIT_FOR_MORE_VERIFIER_BACKED_TRAJECTORIES"
        ),
        evidence_refs=evidence_refs,
    )


def read_registered_experiment(
    *,
    repo_root: str | Path,
    canonical_state_root: str | Path,
    spec_name: str = "trajectory_verifier_v2_spec.json",
) -> dict[str, Any]:
    repo = Path(repo_root).expanduser().resolve()
    spec_path = repo / "nexus" / "research" / "clm_system_one" / spec_name
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    continuity = dict(spec.get("continuity") or {})
    checkpoint_root = Path(canonical_state_root).expanduser().resolve() / str(
        continuity.get("checkpoint_relative_root") or "research/clm_system_one"
    )
    checkpoint = read_experiment_checkpoint(
        evidence_root=checkpoint_root,
        experiment_id=str(spec.get("experiment_id") or ""),
        track_id=str(spec.get("track_id") or ""),
    )

    integrity: dict[str, bool] = {}
    for key in ("holdout_manifest", "last_corpus_audit", "last_experiment_report"):
        item = dict(spec.get(key) or {})
        rel = str(item.get("path") or "")
        expected = str(item.get("sha256") or "")
        target = (repo / rel).resolve()
        if repo not in target.parents or not target.exists():
            integrity[key] = False
            continue
        integrity[key] = _sha256_bytes(target.read_bytes()) == expected

    checkpoint_matches_spec = bool(
        checkpoint.get("experiment_id") == spec.get("experiment_id")
        and checkpoint.get("track_id") == spec.get("track_id")
        and checkpoint.get("claim_ceiling") == spec.get("claim_ceiling")
        and checkpoint.get("holdout_manifest_sha256")
        == (spec.get("holdout_manifest") or {}).get("sha256")
        and checkpoint.get("corpus_audit_sha256")
        == (spec.get("last_corpus_audit") or {}).get("sha256")
        and checkpoint.get("auto_chain") is False
    )
    all_integrity_ok = all(integrity.values()) and checkpoint_matches_spec
    return {
        "schema": "nexus.research_experiment_readback.v1",
        "issue": spec.get("issue"),
        "experiment_id": spec.get("experiment_id"),
        "track_id": spec.get("track_id"),
        "spec_ref": str(spec_path.relative_to(repo)),
        "checkpoint_root": str(checkpoint_root),
        "checkpoint": checkpoint,
        "artifact_integrity": integrity,
        "checkpoint_matches_spec": checkpoint_matches_spec,
        "readback_ok": all_integrity_ok,
    }


def resolve_canonical_state_root() -> Path:
    configured = os.getenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    home = Path.home()
    for candidate in (
        home / "Workspace" / "Nexus-new-self-hosted-state",
        home / "workspace" / "Nexus-new-self-hosted-state",
    ):
        if candidate.exists():
            return candidate.resolve()
    raise FileNotFoundError("canonical Nexus state root is unavailable")


def _git_head(repo: Path) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def _write_readiness_snapshot(
    *,
    checkpoint_root: Path,
    experiment_id: str,
    track_id: str,
    readiness: Mapping[str, Any],
) -> tuple[str, str]:
    body = dict(readiness)
    digest = _sha256_json(body)
    slug = f"{experiment_id}__{track_id}"
    path = checkpoint_root / "experiments" / slug / "readiness" / f"{digest}.json"
    _write_create_only(path, _json_bytes(body))
    pointer = {
        "schema": "nexus.clm_trajectory_corpus_readiness_pointer.v1",
        "readiness_sha256": digest,
        "readiness_ref": str(path.relative_to(checkpoint_root)),
        "updated_at": body.get("observed_at") or _now(),
    }
    _atomic_replace(
        checkpoint_root / "experiments" / slug / "readiness.json",
        _json_bytes(pointer),
    )
    return str(path.relative_to(checkpoint_root)), digest


def refresh_registered_experiment(
    *,
    repo_root: str | Path,
    candidate_evidence_root: str | Path | None = None,
    canonical_state_root: str | Path | None = None,
    spec_name: str = "trajectory_verifier_v2_spec.json",
) -> dict[str, Any]:
    repo = Path(repo_root).expanduser().resolve()
    spec_path = repo / "nexus" / "research" / "clm_system_one" / spec_name
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    holdout_info = dict(spec.get("holdout_manifest") or {})
    holdout_path = (repo / str(holdout_info.get("path") or "")).resolve()
    if repo not in holdout_path.parents or not holdout_path.exists():
        raise ValueError("registered holdout manifest is unavailable")
    holdout = json.loads(holdout_path.read_text(encoding="utf-8"))
    holdout_tasks = list(holdout.get("historical_replay_tasks") or [])

    evidence_root = (
        Path(candidate_evidence_root).expanduser().resolve()
        if candidate_evidence_root is not None
        else resolve_research_evidence_root(repo)
    )
    readiness = project_corpus_readiness(
        evidence_root=evidence_root,
        holdout_task_ids=holdout_tasks,
    )
    state_root = (
        Path(canonical_state_root).expanduser().resolve()
        if canonical_state_root is not None
        else resolve_canonical_state_root()
    )
    continuity = dict(spec.get("continuity") or {})
    checkpoint_root = state_root / str(
        continuity.get("checkpoint_relative_root") or "research/clm_system_one"
    )
    readiness_ref, readiness_sha = _write_readiness_snapshot(
        checkpoint_root=checkpoint_root,
        experiment_id=str(spec.get("experiment_id") or ""),
        track_id=str(spec.get("track_id") or ""),
        readiness=readiness,
    )
    audit = dict(spec.get("last_corpus_audit") or {})
    checkpoint = refresh_checkpoint_from_readiness(
        evidence_root=checkpoint_root,
        experiment_id=str(spec.get("experiment_id") or ""),
        track_id=str(spec.get("track_id") or ""),
        readiness=readiness,
        claim_ceiling=str(spec.get("claim_ceiling") or "EXPERIMENTAL_SHADOW_ONLY"),
        source_revision=_git_head(repo),
        holdout_manifest_ref=str(holdout_info.get("path") or ""),
        holdout_manifest_sha256=str(holdout_info.get("sha256") or ""),
        corpus_audit_ref=str(audit.get("path") or ""),
        corpus_audit_sha256=str(audit.get("sha256") or ""),
        evidence_refs=[
            f"readiness:{readiness_sha}:{readiness_ref}",
            "github:James3014/Nexus-new#1197",
        ],
    )
    return {
        "schema": "nexus.research_experiment_refresh.v1",
        "readiness": readiness,
        "readiness_ref": readiness_ref,
        "readiness_sha256": readiness_sha,
        "checkpoint": checkpoint,
    }
