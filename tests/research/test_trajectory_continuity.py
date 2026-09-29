from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nexus.research.clm_system_one.candidate_evidence_collector import collect_candidate_group
from nexus.research.clm_system_one.trajectory_continuity import (
    bind_trajectory_outcome,
    bind_trajectory_step_result,
    project_corpus_readiness,
    read_experiment_checkpoint,
    read_registered_experiment,
    refresh_checkpoint_from_readiness,
    refresh_registered_experiment,
    seal_trajectory_step,
    write_experiment_checkpoint,
)


def _candidate(candidate_id: str, payload: str, status: str, *, label: str = "ISOLATED_VERIFIER"):
    evidence = {
        "verifier_invoked": True,
        "verifier_status": status,
        "exit_code": 0 if status == "pass" else 1,
    }
    return {
        "candidate_id": candidate_id,
        "candidate_model": "fixture",
        "candidate_source": "trajectory_test",
        "candidate_payload": payload,
        "candidate_payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "candidate_state_hash": "",
        "verifier_status": status,
        "label_quality": label,
        "verifier_evidence": evidence,
        "failure_reason_codes": [],
        "selected": True,
    }


def _candidate_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    task_id: str,
    candidate_id: str,
    status: str,
    label: str = "ISOLATED_VERIFIER",
) -> tuple[Path, str]:
    root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(root))
    result = collect_candidate_group(
        repo_root=tmp_path,
        task_id=task_id,
        attempt_id=f"attempt-{candidate_id}",
        collector_source="trajectory_test",
        source_revision="a" * 40,
        contract_identity={"task_id": task_id},
        verifier_identity={"kind": "pytest"},
        candidates=[_candidate(candidate_id, f"patch-{candidate_id}", status, label=label)],
        winner_id=candidate_id,
    )
    return root, result.row_refs[0]


def _trajectory(
    root: Path,
    *,
    task_id: str,
    trajectory_id: str,
    candidate_id: str,
    candidate_ref: str,
) -> None:
    step0 = seal_trajectory_step(
        evidence_root=root,
        task_id=task_id,
        trajectory_id=trajectory_id,
        attempt_id=f"attempt-{candidate_id}",
        candidate_id=candidate_id,
        step_index=0,
        source_revision="a" * 40,
        pre_action_state={"objective": task_id, "observed": ["file-read"]},
        action_type="shell_command",
        action_payload={"command": "pytest -q"},
        observed_at="2026-09-29T00:00:00+00:00",
    )
    bind_trajectory_step_result(
        evidence_root=root,
        step_ref=step0,
        action_result={"exit_code": 0},
        observed_at="2026-09-29T00:00:01+00:00",
    )
    bind_trajectory_outcome(
        evidence_root=root,
        trajectory_id=trajectory_id,
        candidate_evidence_ref=candidate_ref,
    )


def test_step_is_sealed_before_result_and_is_content_addressed(tmp_path: Path):
    root = tmp_path / "evidence"
    step = seal_trajectory_step(
        evidence_root=root,
        task_id="task-1",
        trajectory_id="traj-1",
        attempt_id="attempt-1",
        candidate_id="candidate-1",
        step_index=0,
        source_revision="a" * 40,
        pre_action_state={"known": ["x"]},
        action_type="source_edit",
        action_payload={"file": "x.py", "change": "bounded"},
        observed_at="2026-09-29T00:00:00+00:00",
    )
    row = json.loads((root / step.step_ref).read_text())
    assert row["sealed_before_result"] is True
    assert "action_result" not in row
    result_ref = bind_trajectory_step_result(
        evidence_root=root,
        step_ref=step,
        action_result={"changed": True},
        observed_at="2026-09-29T00:00:01+00:00",
    )
    result = json.loads((root / result_ref).read_text())
    assert result["step_sha256"] == step.step_sha256


def test_future_final_outcome_cannot_be_in_pre_action_state(tmp_path: Path):
    with pytest.raises(ValueError, match="forbidden final-outcome"):
        seal_trajectory_step(
            evidence_root=tmp_path / "evidence",
            task_id="task-1",
            trajectory_id="traj-1",
            attempt_id="attempt-1",
            candidate_id="candidate-1",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"final_verifier_status": "PASS"},
            action_type="test",
            action_payload={"command": "pytest"},
        )


def test_step_order_gap_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="step order gap"):
        seal_trajectory_step(
            evidence_root=tmp_path / "evidence",
            task_id="task-1",
            trajectory_id="traj-1",
            attempt_id="attempt-1",
            candidate_id="candidate-1",
            step_index=1,
            source_revision="a" * 40,
            pre_action_state={"known": []},
            action_type="test",
            action_payload={"command": "pytest"},
        )


def test_critic_only_candidate_cannot_bind_outcome(tmp_path: Path, monkeypatch):
    root, row_ref = _candidate_row(
        tmp_path,
        monkeypatch,
        task_id="task-critic",
        candidate_id="critic-1",
        status="pass",
        label="CRITIC_AGGREGATE",
    )
    row = json.loads((root / row_ref).read_text())
    assert row["dataset_eligible"] is False
    with pytest.raises(ValueError, match="not dataset eligible"):
        bind_trajectory_outcome(
            evidence_root=root,
            trajectory_id="traj-critic",
            candidate_evidence_ref=row_ref,
        )


def test_empty_corpus_waits_for_data(tmp_path: Path):
    readiness = project_corpus_readiness(evidence_root=tmp_path / "evidence")
    assert readiness["disposition"] == "WAITING_FOR_DATA"
    assert readiness["eligible_strong_label_trajectories"] == 0
    assert "no_strong_label_trajectories" in readiness["blockers"]
    assert readiness["task_disjoint_split_possible"] is False


def test_two_task_binary_coverage_reaches_ready_to_reaudit(tmp_path: Path, monkeypatch):
    rows: list[tuple[str, str, str, str]] = []
    for task_id in ("task-a", "task-b"):
        for status in ("pass", "fail"):
            candidate_id = f"{task_id}-{status}"
            root, row_ref = _candidate_row(
                tmp_path,
                monkeypatch,
                task_id=task_id,
                candidate_id=candidate_id,
                status=status,
            )
            rows.append((task_id, candidate_id, status, row_ref))
    for task_id, candidate_id, status, row_ref in rows:
        _trajectory(
            root,
            task_id=task_id,
            trajectory_id=f"traj-{candidate_id}",
            candidate_id=candidate_id,
            candidate_ref=row_ref,
        )
    readiness = project_corpus_readiness(evidence_root=root)
    assert readiness["eligible_strong_label_trajectories"] == 4
    assert readiness["pass_trajectories"] == 2
    assert readiness["fail_trajectories"] == 2
    assert readiness["independent_task_count"] == 2
    assert readiness["task_disjoint_split_possible"] is True
    assert readiness["disposition"] == "READY_TO_REAUDIT"


def test_holdout_overlap_blocks_readiness(tmp_path: Path, monkeypatch):
    rows: list[tuple[str, str, str]] = []
    for task_id in ("task-a", "task-b"):
        for status in ("pass", "fail"):
            candidate_id = f"{task_id}-{status}"
            root, row_ref = _candidate_row(
                tmp_path,
                monkeypatch,
                task_id=task_id,
                candidate_id=candidate_id,
                status=status,
            )
            rows.append((task_id, candidate_id, row_ref))
    for task_id, candidate_id, row_ref in rows:
        _trajectory(
            root,
            task_id=task_id,
            trajectory_id=f"traj-{candidate_id}",
            candidate_id=candidate_id,
            candidate_ref=row_ref,
        )
    readiness = project_corpus_readiness(
        evidence_root=root,
        holdout_task_ids=["task-a"],
    )
    assert readiness["disposition"] == "WAITING_FOR_DATA"
    assert "holdout_overlap" in readiness["blockers"]
    assert readiness["holdout_overlap_trajectories"]


def test_checkpoint_history_and_fresh_session_readback(tmp_path: Path):
    root = tmp_path / "evidence"
    checkpoint = write_experiment_checkpoint(
        evidence_root=root,
        experiment_id="NEXUS_SYSTEM_ONE_CLM_V2",
        track_id="TRACK_1_TRAJECTORY_VERIFIER_HEAD",
        status="WAITING_FOR_DATA",
        claim_ceiling="EXPERIMENTAL_SHADOW_ONLY",
        source_revision="a" * 40,
        holdout_manifest_ref="docs/research/trajectory_verifier_v2/FINAL_HOLDOUT_DO_NOT_TRAIN.json",
        holdout_manifest_sha256="1" * 64,
        corpus_audit_ref="docs/research/trajectory_verifier_v2/TRAJECTORY_CORPUS_READINESS_REPORT.md",
        corpus_audit_sha256="2" * 64,
        blockers=["task_disjoint_split_unavailable"],
        resume_gate="TRAJECTORY_CORPUS_READY_FOR_T1_REAUDIT",
        next_allowed_action="WAIT_FOR_MORE_VERIFIER_BACKED_TRAJECTORIES",
        evidence_refs=["issue:1197"],
        updated_at="2026-09-29T00:00:00+00:00",
    )
    restored = read_experiment_checkpoint(
        evidence_root=root,
        experiment_id="NEXUS_SYSTEM_ONE_CLM_V2",
        track_id="TRACK_1_TRAJECTORY_VERIFIER_HEAD",
    )
    assert restored == checkpoint
    assert restored["auto_chain"] is False
    assert restored["status"] == "WAITING_FOR_DATA"
    assert restored["holdout_manifest_sha256"] == "1" * 64
    assert restored["next_allowed_action"] == "WAIT_FOR_MORE_VERIFIER_BACKED_TRAJECTORIES"
    history = list((root / "experiments").rglob("history/*.json"))
    assert len(history) == 1


def test_ready_checkpoint_can_only_resume_t0_t1(tmp_path: Path):
    with pytest.raises(ValueError, match="T0_T1_REAUDIT_ONLY"):
        write_experiment_checkpoint(
            evidence_root=tmp_path / "evidence",
            experiment_id="NEXUS_SYSTEM_ONE_CLM_V2",
            track_id="TRACK_1_TRAJECTORY_VERIFIER_HEAD",
            status="READY_TO_REAUDIT",
            claim_ceiling="EXPERIMENTAL_SHADOW_ONLY",
            source_revision="a" * 40,
            holdout_manifest_ref="holdout.json",
            holdout_manifest_sha256="1" * 64,
            corpus_audit_ref="audit.md",
            corpus_audit_sha256="2" * 64,
            blockers=[],
            resume_gate="TRAJECTORY_CORPUS_READY_FOR_T1_REAUDIT",
            next_allowed_action="TRAIN_HEAD",
        )


def test_refresh_checkpoint_never_auto_chains_training(tmp_path: Path):
    root = tmp_path / "evidence"
    readiness = {
        "disposition": "READY_TO_REAUDIT",
        "blockers": [],
    }
    checkpoint = refresh_checkpoint_from_readiness(
        evidence_root=root,
        experiment_id="NEXUS_SYSTEM_ONE_CLM_V2",
        track_id="TRACK_1_TRAJECTORY_VERIFIER_HEAD",
        readiness=readiness,
        claim_ceiling="EXPERIMENTAL_SHADOW_ONLY",
        source_revision="a" * 40,
        holdout_manifest_ref="holdout.json",
        holdout_manifest_sha256="1" * 64,
        corpus_audit_ref="audit.md",
        corpus_audit_sha256="2" * 64,
        evidence_refs=["issue:1197"],
    )
    assert checkpoint["status"] == "READY_TO_REAUDIT"
    assert checkpoint["next_allowed_action"] == "T0_T1_REAUDIT_ONLY"
    assert checkpoint["auto_chain"] is False


def test_registered_experiment_readback_needs_no_chat_context(tmp_path: Path):
    repo = tmp_path / "repo"
    state_root = tmp_path / "state"
    docs = repo / "docs" / "research" / "trajectory_verifier_v2"
    spec_dir = repo / "nexus" / "research" / "clm_system_one"
    docs.mkdir(parents=True)
    spec_dir.mkdir(parents=True)

    holdout = docs / "FINAL_HOLDOUT_DO_NOT_TRAIN.json"
    audit = docs / "TRAJECTORY_CORPUS_READINESS_REPORT.md"
    report = docs / "TRAJECTORY_VERIFIER_EXPERIMENT_REPORT.md"
    holdout.write_text("{}\n")
    audit.write_text("not ready\n")
    report.write_text("inconclusive\n")

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    spec = {
        "schema": "nexus.research_experiment_spec.v1",
        "issue": 1197,
        "experiment_id": "NEXUS_SYSTEM_ONE_CLM_V2",
        "track_id": "TRACK_1_TRAJECTORY_VERIFIER_HEAD",
        "claim_ceiling": "EXPERIMENTAL_SHADOW_ONLY",
        "holdout_manifest": {
            "path": str(holdout.relative_to(repo)),
            "sha256": sha(holdout),
        },
        "last_corpus_audit": {
            "path": str(audit.relative_to(repo)),
            "sha256": sha(audit),
        },
        "last_experiment_report": {
            "path": str(report.relative_to(repo)),
            "sha256": sha(report),
        },
        "continuity": {"checkpoint_relative_root": "research/clm_system_one"},
    }
    (spec_dir / "trajectory_verifier_v2_spec.json").write_text(json.dumps(spec))

    checkpoint_root = state_root / "research" / "clm_system_one"
    write_experiment_checkpoint(
        evidence_root=checkpoint_root,
        experiment_id=spec["experiment_id"],
        track_id=spec["track_id"],
        status="WAITING_FOR_DATA",
        claim_ceiling=spec["claim_ceiling"],
        source_revision="a" * 40,
        holdout_manifest_ref=spec["holdout_manifest"]["path"],
        holdout_manifest_sha256=spec["holdout_manifest"]["sha256"],
        corpus_audit_ref=spec["last_corpus_audit"]["path"],
        corpus_audit_sha256=spec["last_corpus_audit"]["sha256"],
        blockers=["task_disjoint_split_unavailable"],
        resume_gate="TRAJECTORY_CORPUS_READY_FOR_T1_REAUDIT",
        next_allowed_action="WAIT_FOR_MORE_VERIFIER_BACKED_TRAJECTORIES",
    )

    readback = read_registered_experiment(repo_root=repo, canonical_state_root=state_root)
    assert readback["issue"] == 1197
    assert readback["readback_ok"] is True
    assert readback["checkpoint"]["status"] == "WAITING_FOR_DATA"
    assert readback["checkpoint"]["resume_gate"] == "TRAJECTORY_CORPUS_READY_FOR_T1_REAUDIT"


def test_trajectory_identity_is_not_used_as_a_filesystem_path(tmp_path: Path):
    root = tmp_path / "evidence"
    step = seal_trajectory_step(
        evidence_root=root,
        task_id="task-1",
        trajectory_id="../../escape",
        attempt_id="attempt-1",
        candidate_id="candidate-1",
        step_index=0,
        source_revision="a" * 40,
        pre_action_state={"known": ["safe"]},
        action_type="read",
        action_payload={"path": "file.py"},
    )
    step_path = (root / step.step_ref).resolve()
    assert root.resolve() in step_path.parents
    assert ".." not in Path(step.step_ref).parts
    assert len(step_path.parent.name) == 64


def test_registered_refresh_persists_ready_to_reaudit_without_auto_chain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = tmp_path / "repo"
    state_root = tmp_path / "state"
    evidence_root = repo / "evidence"
    docs = repo / "docs" / "research" / "trajectory_verifier_v2"
    spec_dir = repo / "nexus" / "research" / "clm_system_one"
    docs.mkdir(parents=True)
    spec_dir.mkdir(parents=True)

    holdout = docs / "FINAL_HOLDOUT_DO_NOT_TRAIN.json"
    audit = docs / "TRAJECTORY_CORPUS_READINESS_REPORT.md"
    report = docs / "TRAJECTORY_VERIFIER_EXPERIMENT_REPORT.md"
    holdout.write_text('{"historical_replay_tasks":["R01"]}\n')
    audit.write_text("not ready\n")
    report.write_text("inconclusive\n")

    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    spec = {
        "schema": "nexus.research_experiment_spec.v1",
        "issue": 1197,
        "experiment_id": "NEXUS_SYSTEM_ONE_CLM_V2",
        "track_id": "TRACK_1_TRAJECTORY_VERIFIER_HEAD",
        "claim_ceiling": "EXPERIMENTAL_SHADOW_ONLY",
        "holdout_manifest": {
            "path": str(holdout.relative_to(repo)),
            "sha256": sha(holdout),
        },
        "last_corpus_audit": {
            "path": str(audit.relative_to(repo)),
            "sha256": sha(audit),
        },
        "last_experiment_report": {
            "path": str(report.relative_to(repo)),
            "sha256": sha(report),
        },
        "continuity": {"checkpoint_relative_root": "research/clm_system_one"},
    }
    (spec_dir / "trajectory_verifier_v2_spec.json").write_text(json.dumps(spec))

    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    rows: list[tuple[str, str, str]] = []
    for task_id in ("task-a", "task-b"):
        for status in ("pass", "fail"):
            candidate_id = f"{task_id}-{status}"
            _, row_ref = _candidate_row(
                repo,
                monkeypatch,
                task_id=task_id,
                candidate_id=candidate_id,
                status=status,
            )
            rows.append((task_id, candidate_id, row_ref))
    for task_id, candidate_id, row_ref in rows:
        _trajectory(
            evidence_root,
            task_id=task_id,
            trajectory_id=f"traj-{candidate_id}",
            candidate_id=candidate_id,
            candidate_ref=row_ref,
        )

    refreshed = refresh_registered_experiment(
        repo_root=repo,
        candidate_evidence_root=evidence_root,
        canonical_state_root=state_root,
    )
    assert refreshed["readiness"]["disposition"] == "READY_TO_REAUDIT"
    assert refreshed["checkpoint"]["status"] == "READY_TO_REAUDIT"
    assert refreshed["checkpoint"]["next_allowed_action"] == "T0_T1_REAUDIT_ONLY"
    assert refreshed["checkpoint"]["auto_chain"] is False
    readiness_pointer = (
        state_root
        / "research"
        / "clm_system_one"
        / "experiments"
        / "NEXUS_SYSTEM_ONE_CLM_V2__TRACK_1_TRAJECTORY_VERIFIER_HEAD"
        / "readiness.json"
    )
    assert readiness_pointer.exists()
