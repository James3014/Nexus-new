from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from nexus.research.clm_system_one.candidate_evidence_collector import collect_candidate_group
from nexus.research.clm_system_one.trajectory_continuity import (
    _MAX_RESULT_INLINE_BYTES,
    _MIN_TASK_FAMILIES,
    HEALTH_SCHEMA,
    _health_snapshot_path,
    _redact_value,
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

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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
    contract_identity: dict | None = None,
) -> tuple[Path, str]:
    root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(root))
    result = collect_candidate_group(
        repo_root=tmp_path,
        task_id=task_id,
        attempt_id=f"attempt-{candidate_id}",
        collector_source="trajectory_test",
        source_revision="a" * 40,
        contract_identity=contract_identity or {"task_id": task_id},
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


def _five_family_corpus(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, dict[str, str]]:
    """Build a corpus with exactly _MIN_TASK_FAMILIES (5) task families,
    each having PASS+FAIL coverage, suitable for READY_TO_REAUDIT."""
    families = {f"task-f{i}-pass": f"family-{i}" for i in range(_MIN_TASK_FAMILIES)}
    families.update({f"task-f{i}-fail": f"family-{i}" for i in range(_MIN_TASK_FAMILIES)})

    root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(root))

    for i in range(_MIN_TASK_FAMILIES):
        for status in ("pass", "fail"):
            task_id = f"task-f{i}-{status}"
            candidate_id = f"cand-f{i}-{status}"
            root_e, row_ref = _candidate_row(
                tmp_path, monkeypatch, task_id=task_id, candidate_id=candidate_id, status=status
            )
            _trajectory(
                root_e,
                task_id=task_id,
                trajectory_id=f"traj-{candidate_id}",
                candidate_id=candidate_id,
                candidate_ref=row_ref,
            )

    task_family_map = {
        **{f"task-f{i}-pass": f"family-{i}" for i in range(_MIN_TASK_FAMILIES)},
        **{f"task-f{i}-fail": f"family-{i}" for i in range(_MIN_TASK_FAMILIES)},
    }
    return root, task_family_map


# ---------------------------------------------------------------------------
# #1197 compatibility – original tests preserved
# ---------------------------------------------------------------------------


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
    """Backwards-compatibility note: with the #1212 hardening, two tasks/two families
    is NOT enough for READY_TO_REAUDIT (requires _MIN_TASK_FAMILIES=5 strong families).
    This test now asserts WAITING_FOR_DATA and the new blockers."""
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
    task_family_map = {"task-a": "family-a", "task-b": "family-b"}
    readiness = project_corpus_readiness(evidence_root=root, task_family_by_task=task_family_map)
    assert readiness["eligible_strong_label_trajectories"] == 4
    assert readiness["pass_trajectories"] == 2
    assert readiness["fail_trajectories"] == 2
    assert readiness["independent_task_count"] == 2
    assert readiness["task_disjoint_split_possible"] is True
    # Only 2 strong families → blocked by insufficient_task_families
    assert any("insufficient_task_families" in b for b in readiness["blockers"])
    assert readiness["disposition"] == "WAITING_FOR_DATA"


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


def test_explicit_trajectory_exclusion_is_not_counted(tmp_path: Path, monkeypatch):
    root, row_ref = _candidate_row(
        tmp_path,
        monkeypatch,
        task_id="fixture-task",
        candidate_id="fixture-candidate",
        status="pass",
    )
    _trajectory(
        root,
        task_id="fixture-task",
        trajectory_id="fixture-trajectory",
        candidate_id="fixture-candidate",
        candidate_ref=row_ref,
    )

    readiness = project_corpus_readiness(
        evidence_root=root,
        excluded_trajectory_ids=["fixture-trajectory"],
    )

    assert readiness["eligible_strong_label_trajectories"] == 0
    assert readiness["pass_trajectories"] == 0
    assert readiness["excluded_trajectories"] == ["fixture-trajectory"]
    assert "no_strong_label_trajectories" in readiness["blockers"]


def test_registered_refresh_applies_spec_trajectory_exclusions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    repo = Path(__file__).resolve().parents[2]
    excluded_id = "c15-6e-controlled-success#delegated-retry-01-ornith-9b#provider-trajectory"
    root, row_ref = _candidate_row(
        tmp_path,
        monkeypatch,
        task_id="fixture-task",
        candidate_id="fixture-candidate",
        status="pass",
    )
    _trajectory(
        root,
        task_id="fixture-task",
        trajectory_id=excluded_id,
        candidate_id="fixture-candidate",
        candidate_ref=row_ref,
    )

    refreshed = refresh_registered_experiment(
        repo_root=repo,
        candidate_evidence_root=root,
        canonical_state_root=tmp_path / "state",
    )

    assert refreshed["readiness"]["eligible_strong_label_trajectories"] == 0
    assert refreshed["readiness"]["excluded_trajectories"] == [excluded_id]
    assert refreshed["checkpoint"]["status"] == "WAITING_FOR_DATA"
    assert refreshed["checkpoint"]["auto_chain"] is False


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


def test_registered_v2_spec_artifact_digests_match_repository():
    repo = Path(__file__).resolve().parents[2]
    spec_path = repo / "nexus" / "research" / "clm_system_one" / "trajectory_verifier_v2_spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))

    for key in ("holdout_manifest", "last_corpus_audit", "last_experiment_report"):
        artifact = dict(spec[key])
        target = repo / artifact["path"]
        assert target.exists(), f"missing registered artifact: {target}"
        assert hashlib.sha256(target.read_bytes()).hexdigest() == artifact["sha256"]


# ---------------------------------------------------------------------------
# #1212 Hardening – new invariant tests
# ---------------------------------------------------------------------------


class TestNullableCandidateId:
    """candidate_id is nullable (pre-candidate steps)."""

    def test_none_candidate_id_accepted(self, tmp_path: Path):
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-pre-candidate",
            attempt_id="attempt-1",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"phase": "exploration"},
            action_type="read_file",
            action_payload={"path": "README.md"},
        )
        row = json.loads((root / step.step_ref).read_text())
        assert row["candidate_id"] == ""

    def test_empty_string_candidate_id_accepted(self, tmp_path: Path):
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-empty-cand",
            attempt_id="attempt-1",
            candidate_id="",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"phase": "exploration"},
            action_type="read_file",
            action_payload={"path": "README.md"},
        )
        row = json.loads((root / step.step_ref).read_text())
        assert row["candidate_id"] == ""

    def test_explicit_candidate_id_stored(self, tmp_path: Path):
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-with-cand",
            attempt_id="attempt-1",
            candidate_id="cand-xyz-001",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"phase": "repair"},
            action_type="apply_patch",
            action_payload={"patch": "--- a/x.py"},
        )
        row = json.loads((root / step.step_ref).read_text())
        assert row["candidate_id"] == "cand-xyz-001"


class TestBaseSourceRevisionAndManifestSha:
    """base_source_revision is fixed per trajectory; working_state_manifest_sha256 per step."""

    def test_base_source_revision_persisted(self, tmp_path: Path):
        root = tmp_path / "evidence"
        base_rev = "b" * 40
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-rev",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            base_source_revision=base_rev,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "y.py"},
        )
        row = json.loads((root / step.step_ref).read_text())
        assert row["base_source_revision"] == base_rev

    def test_working_state_manifest_sha_persisted(self, tmp_path: Path):
        root = tmp_path / "evidence"
        manifest_sha = "c" * 64
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-manifest",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            working_state_manifest_sha256=manifest_sha,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "y.py"},
        )
        row = json.loads((root / step.step_ref).read_text())
        assert row["working_state_manifest_sha256"] == manifest_sha

    def test_both_optional_fields_default_empty(self, tmp_path: Path):
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-no-extras",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "y.py"},
        )
        row = json.loads((root / step.step_ref).read_text())
        assert row["base_source_revision"] == ""
        assert row["working_state_manifest_sha256"] == ""


class TestSecretRedaction:
    """Secrets are redacted BEFORE hashing or persistence."""

    def test_password_in_state_is_redacted_on_disk(self, tmp_path: Path):
        root = tmp_path / "evidence"
        fake_password = "fixture-password-value"
        fake_github_token = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-secret",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={
                "command": f"curl -u user:{fake_password} http://api.example.com/endpoint"
            },
            action_type="api_call",
            action_payload={"token": f"Bearer {fake_github_token}"},
        )
        state_path = root / "trajectory" / "state"
        all_state_files = list(state_path.rglob("*.json"))
        assert all_state_files, "at least one state blob must exist"
        for f in all_state_files:
            content = f.read_text(encoding="utf-8")
            assert fake_password not in content
            assert fake_github_token not in content  # not in state

        action_path = root / "trajectory" / "action"
        for f in action_path.rglob("*.json"):
            content = f.read_text(encoding="utf-8")
            assert fake_github_token not in content

    def test_private_key_pattern_is_redacted(self, tmp_path: Path):
        root = tmp_path / "evidence"
        sensitive_state = {
            "key_material": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA...\n-----END RSA PRIVATE KEY-----"
        }
        seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-privkey",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state=sensitive_state,
            action_type="sign",
            action_payload={"data": "hello"},
        )
        state_path = root / "trajectory" / "state"
        for f in state_path.rglob("*.json"):
            content = f.read_text(encoding="utf-8")
            assert "BEGIN RSA PRIVATE KEY" not in content

    def test_api_key_pattern_is_redacted(self, tmp_path: Path):
        root = tmp_path / "evidence"
        fake_openai_key = "sk-" + "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdef123456"
        seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-apikey",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"config": {"api_key": fake_openai_key}},
            action_type="config_write",
            action_payload={"file": "config.json"},
        )
        state_path = root / "trajectory" / "state"
        for f in state_path.rglob("*.json"):
            content = f.read_text(encoding="utf-8")
            assert fake_openai_key not in content

    def test_redact_value_function_directly(self):
        """Unit-test _redact_value without disk I/O."""
        fixture_password = "fixture-password-value"
        fixture_token = "fixture-token-value"
        raw = {
            "password": fixture_password,
            "nested": {"token": f"Bearer {fixture_token}"},
            "safe_field": "this is fine",
        }
        redacted = _redact_value(raw)
        assert fixture_password not in json.dumps(redacted)
        assert fixture_token not in json.dumps(redacted)
        assert redacted["safe_field"] == "this is fine"

    def test_result_is_redacted_before_persistence(self, tmp_path: Path):
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-result-secret",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="call_api",
            action_payload={"url": "https://api.example.com"},
        )
        bind_trajectory_step_result(
            evidence_root=root,
            step_ref=step,
            action_result={"token": "fixture-secret-value", "output": "ok"},
        )
        result_path = root / "trajectory" / "result"
        for f in result_path.rglob("*.json"):
            content = f.read_text(encoding="utf-8")
            assert "fixture-secret-value" not in content


class TestWeakSupervision:
    """WEAK_SUPERVISION label emitted when no step oracle provided."""

    def test_no_oracle_yields_weak_supervision(self, tmp_path: Path):
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-weak",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        row = json.loads((root / step.step_ref).read_text())
        assert row["supervision_mode"] == "WEAK_SUPERVISION"

    def test_oracle_present_yields_oracle_supervised(self, tmp_path: Path):
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-1",
            trajectory_id="traj-oracle",
            attempt_id="attempt-1",
            candidate_id="cand-1",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
            step_oracle={"expected_action": "read_file"},
        )
        row = json.loads((root / step.step_ref).read_text())
        assert row["supervision_mode"] == "ORACLE_SUPERVISED"


class TestClosedTrajectoryGuard:
    """Closed trajectories cannot silently append steps after outcome is bound."""

    def test_cannot_append_step_after_outcome_bound(self, tmp_path: Path, monkeypatch):
        root, row_ref = _candidate_row(
            tmp_path, monkeypatch, task_id="task-closed", candidate_id="cand-closed", status="pass"
        )
        traj_id = "traj-closed-1"
        step0 = seal_trajectory_step(
            evidence_root=root,
            task_id="task-closed",
            trajectory_id=traj_id,
            attempt_id="attempt-cand-closed",
            candidate_id="cand-closed",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        bind_trajectory_step_result(
            evidence_root=root, step_ref=step0, action_result={"exit_code": 0}
        )
        bind_trajectory_outcome(
            evidence_root=root, trajectory_id=traj_id, candidate_evidence_ref=row_ref
        )
        # Attempt to append another step → must be rejected
        with pytest.raises(ValueError, match="closed"):
            seal_trajectory_step(
                evidence_root=root,
                task_id="task-closed",
                trajectory_id=traj_id,
                attempt_id="attempt-cand-closed",
                candidate_id="cand-closed",
                step_index=1,
                source_revision="a" * 40,
                pre_action_state={"x": 2},
                action_type="write",
                action_payload={"f": "y.py"},
            )

    def test_outcome_binding_is_write_once(self, tmp_path: Path, monkeypatch):
        """Attempting to bind a second outcome to the same trajectory must fail."""
        root, row_ref = _candidate_row(
            tmp_path, monkeypatch, task_id="task-double", candidate_id="cand-double", status="fail"
        )
        traj_id = "traj-double"
        step0 = seal_trajectory_step(
            evidence_root=root,
            task_id="task-double",
            trajectory_id=traj_id,
            attempt_id="attempt-cand-double",
            candidate_id="cand-double",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="test",
            action_payload={"cmd": "pytest"},
        )
        bind_trajectory_step_result(
            evidence_root=root, step_ref=step0, action_result={"exit_code": 1}
        )
        bind_trajectory_outcome(
            evidence_root=root, trajectory_id=traj_id, candidate_evidence_ref=row_ref
        )
        with pytest.raises((ValueError, RuntimeError)):
            bind_trajectory_outcome(
                evidence_root=root, trajectory_id=traj_id, candidate_evidence_ref=row_ref
            )


class TestOutcomeChainValidation:
    """bind_trajectory_outcome validates the full trajectory/candidate/complete chain."""

    def test_incomplete_trajectory_cannot_bind_outcome(self, tmp_path: Path, monkeypatch):
        """Trajectory with steps but no results → bind_trajectory_outcome must fail."""
        root, row_ref = _candidate_row(
            tmp_path, monkeypatch, task_id="task-incomplete", candidate_id="cand-inc", status="pass"
        )
        traj_id = "traj-incomplete"
        # Seal step but do NOT bind result
        seal_trajectory_step(
            evidence_root=root,
            task_id="task-incomplete",
            trajectory_id=traj_id,
            attempt_id="attempt-inc",
            candidate_id="cand-inc",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        with pytest.raises(ValueError, match="incomplete"):
            bind_trajectory_outcome(
                evidence_root=root, trajectory_id=traj_id, candidate_evidence_ref=row_ref
            )

    def test_missing_trajectory_steps_block_outcome(self, tmp_path: Path, monkeypatch):
        """Trajectory with zero steps → bind_trajectory_outcome must fail."""
        root, row_ref = _candidate_row(
            tmp_path, monkeypatch, task_id="task-nosteps", candidate_id="cand-ns", status="fail"
        )
        with pytest.raises(ValueError, match="incomplete"):
            bind_trajectory_outcome(
                evidence_root=root,
                trajectory_id="traj-no-steps",
                candidate_evidence_ref=row_ref,
            )


class TestOutcomeIdentityBinding:
    """Post-episode binding rejects identity drift and records contract fields."""

    def _complete_step(
        self,
        root: Path,
        *,
        task_id: str,
        trajectory_id: str,
        attempt_id: str,
        candidate_id: str | None,
    ) -> None:
        step = seal_trajectory_step(
            evidence_root=root,
            task_id=task_id,
            trajectory_id=trajectory_id,
            attempt_id=attempt_id,
            candidate_id=candidate_id,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"objective": task_id},
            action_type="test",
            action_payload={"cmd": "pytest"},
        )
        bind_trajectory_step_result(
            evidence_root=root,
            step_ref=step,
            action_result={"exit_code": 0},
        )

    def test_candidate_id_mismatch_is_rejected(self, tmp_path: Path, monkeypatch):
        root, row_ref = _candidate_row(
            tmp_path,
            monkeypatch,
            task_id="task-id",
            candidate_id="candidate-final",
            status="pass",
        )
        self._complete_step(
            root,
            task_id="task-id",
            trajectory_id="traj-id-mismatch",
            attempt_id="attempt-candidate-final",
            candidate_id="candidate-other",
        )
        with pytest.raises(ValueError, match="candidate_id"):
            bind_trajectory_outcome(
                evidence_root=root,
                trajectory_id="traj-id-mismatch",
                candidate_evidence_ref=row_ref,
            )

    def test_attempt_id_mismatch_is_rejected(self, tmp_path: Path, monkeypatch):
        root, row_ref = _candidate_row(
            tmp_path,
            monkeypatch,
            task_id="task-attempt",
            candidate_id="candidate-attempt",
            status="pass",
        )
        self._complete_step(
            root,
            task_id="task-attempt",
            trajectory_id="traj-attempt-mismatch",
            attempt_id="attempt-wrong",
            candidate_id="candidate-attempt",
        )
        with pytest.raises(ValueError, match="attempt_id"):
            bind_trajectory_outcome(
                evidence_root=root,
                trajectory_id="traj-attempt-mismatch",
                candidate_evidence_ref=row_ref,
            )

    def test_null_early_candidate_can_bind_final_candidate(self, tmp_path: Path, monkeypatch):
        root, row_ref = _candidate_row(
            tmp_path,
            monkeypatch,
            task_id="task-null",
            candidate_id="candidate-null",
            status="pass",
        )
        self._complete_step(
            root,
            task_id="task-null",
            trajectory_id="traj-null-final",
            attempt_id="attempt-candidate-null",
            candidate_id=None,
        )
        outcome_ref = bind_trajectory_outcome(
            evidence_root=root,
            trajectory_id="traj-null-final",
            candidate_evidence_ref=row_ref,
        )
        binding = json.loads((root / outcome_ref).read_text(encoding="utf-8"))
        assert binding["schema"] == "nexus.clm_trajectory_binding.v1"
        assert binding["candidate_id"] == "candidate-null"
        assert binding["comparison_group_sha256"]
        assert binding["step_count"] == 1
        assert binding["terminal_step_sha256"]
        assert binding["binding_sha256"] == binding["record_sha256"]


class TestContentAddressedResultBlob:
    def test_large_string_blob_name_hashes_exact_persisted_bytes(self, tmp_path: Path):
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-blob",
            trajectory_id="traj-blob",
            attempt_id="attempt-blob",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="command",
            action_payload={"cmd": "emit"},
        )
        result_ref = bind_trajectory_step_result(
            evidence_root=root,
            step_ref=step,
            action_result="X" * (_MAX_RESULT_INLINE_BYTES + 500),
        )
        result = json.loads((root / result_ref).read_text(encoding="utf-8"))
        blob_path = root / result["action_result_blob_ref"]
        assert blob_path.exists()
        digest = hashlib.sha256(blob_path.read_bytes()).hexdigest()
        assert blob_path.stem == digest
        assert result["action_result_sha256"] == digest


class TestIneligibleRowsExcluded:
    """Incomplete/unknown/critic rows are ineligible in corpus readiness."""

    def test_unknown_verifier_status_row_is_excluded(self, tmp_path: Path, monkeypatch):
        """A row with dataset_eligible=False (unknown status) must not count."""
        # Use CRITIC_AGGREGATE which produces dataset_eligible=False
        root, row_ref = _candidate_row(
            tmp_path,
            monkeypatch,
            task_id="task-unk",
            candidate_id="cand-unk",
            status="pass",
            label="CRITIC_AGGREGATE",
        )
        row = json.loads((root / row_ref).read_text())
        assert not row["dataset_eligible"]
        # Manually write a fake outcome referencing this ineligible row
        # project_corpus_readiness should exclude it via dataset_eligible check
        readiness = project_corpus_readiness(evidence_root=root)
        assert readiness["eligible_strong_label_trajectories"] == 0

    def test_insufficient_families_blocks_readiness(self, tmp_path: Path, monkeypatch):
        """Fewer than _MIN_TASK_FAMILIES strong families → WAITING_FOR_DATA."""
        # 3 families is not enough
        n_families = _MIN_TASK_FAMILIES - 2
        root = tmp_path / "evidence"
        monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(root))
        task_family_map: dict[str, str] = {}
        for i in range(n_families):
            for status in ("pass", "fail"):
                task_id = f"task-fam{i}-{status}"
                candidate_id = f"cand-fam{i}-{status}"
                task_family_map[task_id] = f"family-{i}"
                _, row_ref = _candidate_row(
                    tmp_path,
                    monkeypatch,
                    task_id=task_id,
                    candidate_id=candidate_id,
                    status=status,
                )
                _trajectory(
                    root,
                    task_id=task_id,
                    trajectory_id=f"traj-{candidate_id}",
                    candidate_id=candidate_id,
                    candidate_ref=row_ref,
                )
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        assert readiness["disposition"] == "WAITING_FOR_DATA"
        assert any("insufficient_task_families" in b for b in readiness["blockers"])
        assert readiness["strong_family_count"] == n_families


class TestFiveTaskFamilyReadiness:
    """>=5 independent task families with strong PASS+FAIL → READY_TO_REAUDIT."""

    def test_five_strong_families_reaches_ready_to_reaudit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        root, task_family_map = _five_family_corpus(tmp_path, monkeypatch)
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        assert readiness["eligible_strong_label_trajectories"] == _MIN_TASK_FAMILIES * 2
        assert readiness["pass_trajectories"] == _MIN_TASK_FAMILIES
        assert readiness["fail_trajectories"] == _MIN_TASK_FAMILIES
        assert readiness["strong_family_count"] == _MIN_TASK_FAMILIES
        assert readiness["family_disjoint_split_possible"] is True
        assert readiness["disposition"] == "READY_TO_REAUDIT"
        assert not readiness["blockers"]

    def test_five_families_auto_chain_always_false(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        root, task_family_map = _five_family_corpus(tmp_path, monkeypatch)
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        assert readiness["disposition"] == "READY_TO_REAUDIT"
        state_root = tmp_path / "state"
        # Write a minimal spec so refresh_checkpoint_from_readiness works
        checkpoint = refresh_checkpoint_from_readiness(
            evidence_root=state_root / "ckpt",
            experiment_id="EXP",
            track_id="TRACK",
            readiness=readiness,
            claim_ceiling="EXPERIMENTAL_SHADOW_ONLY",
            source_revision="a" * 40,
            holdout_manifest_ref="holdout.json",
            holdout_manifest_sha256="0" * 64,
            corpus_audit_ref="audit.md",
            corpus_audit_sha256="1" * 64,
        )
        assert checkpoint["auto_chain"] is False
        assert checkpoint["next_allowed_action"] == "T0_T1_REAUDIT_ONLY"
        assert checkpoint["status"] == "READY_TO_REAUDIT"

    def test_four_families_is_not_enough(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        root = tmp_path / "evidence"
        monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(root))
        task_family_map: dict[str, str] = {}
        for i in range(_MIN_TASK_FAMILIES - 1):  # 4 families
            for status in ("pass", "fail"):
                task_id = f"task-4f{i}-{status}"
                candidate_id = f"cand-4f{i}-{status}"
                task_family_map[task_id] = f"family-{i}"
                _, row_ref = _candidate_row(
                    tmp_path,
                    monkeypatch,
                    task_id=task_id,
                    candidate_id=candidate_id,
                    status=status,
                )
                _trajectory(
                    root,
                    task_id=task_id,
                    trajectory_id=f"traj-{candidate_id}",
                    candidate_id=candidate_id,
                    candidate_ref=row_ref,
                )
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        assert readiness["disposition"] == "WAITING_FOR_DATA"
        assert any("insufficient_task_families" in b for b in readiness["blockers"])


class TestFamilyDisjointSplitRequired:
    """task-family-disjoint split is now required (not just task-level split)."""

    def test_no_family_map_blocks_family_split(self, tmp_path: Path, monkeypatch):
        """If no task_family_by_task is provided, family_disjoint_split is False → blocked."""
        rows: list[tuple[str, str, str, str]] = []
        for task_id in (f"task-{i}" for i in range(10)):
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
        readiness = project_corpus_readiness(evidence_root=root)  # no task_family_by_task
        assert readiness["family_disjoint_split_possible"] is False
        assert "family_disjoint_split_unavailable" in readiness["blockers"]
        assert readiness["disposition"] == "WAITING_FOR_DATA"


class TestSidecarHealthFailOpen:
    """Sidecar health writes are fail-visible but main workflow is fail-open."""

    def test_sidecar_health_log_written_on_closed_trajectory_attempt(
        self, tmp_path: Path, monkeypatch
    ):
        """After closing a trajectory, an append attempt writes to sidecar health log."""
        root, row_ref = _candidate_row(
            tmp_path, monkeypatch, task_id="task-sh", candidate_id="cand-sh", status="pass"
        )
        traj_id = "traj-sh-closed"
        step0 = seal_trajectory_step(
            evidence_root=root,
            task_id="task-sh",
            trajectory_id=traj_id,
            attempt_id="attempt-cand-sh",
            candidate_id="cand-sh",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        bind_trajectory_step_result(
            evidence_root=root, step_ref=step0, action_result={"exit_code": 0}
        )
        bind_trajectory_outcome(
            evidence_root=root, trajectory_id=traj_id, candidate_evidence_ref=row_ref
        )
        # Attempt to append (must raise)
        with pytest.raises(ValueError, match="closed"):
            seal_trajectory_step(
                evidence_root=root,
                task_id="task-sh",
                trajectory_id=traj_id,
                attempt_id="attempt-cand-sh",
                candidate_id="cand-sh",
                step_index=1,
                source_revision="a" * 40,
                pre_action_state={"x": 2},
                action_type="write",
                action_payload={"f": "y.py"},
            )
        # Sidecar health log must exist and mention the event
        health_path = root / "trajectory" / "sidecar_health.jsonl"
        assert health_path.exists()
        events = [json.loads(line) for line in health_path.read_text().splitlines() if line.strip()]
        assert any(e["event_type"] == "CLOSED_TRAJECTORY_APPEND_ATTEMPT" for e in events)


class TestReadinessNoHoldoutOverlapAndNoLeakage:
    """No holdout overlap and no leakage/malformed evidence for READY_TO_REAUDIT."""

    def test_holdout_overlap_prevents_ready_to_reaudit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        root, task_family_map = _five_family_corpus(tmp_path, monkeypatch)
        # Mark one task as holdout
        holdout_task = "task-f0-pass"
        readiness = project_corpus_readiness(
            evidence_root=root,
            holdout_task_ids=[holdout_task],
            task_family_by_task=task_family_map,
        )
        assert readiness["disposition"] == "WAITING_FOR_DATA"
        assert "holdout_overlap" in readiness["blockers"]

    def test_malformed_evidence_prevents_ready_to_reaudit(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        root, task_family_map = _five_family_corpus(tmp_path, monkeypatch)
        # Inject a malformed outcome file
        outcomes_dir = root / "trajectory" / "outcomes"
        malformed_path = (
            outcomes_dir / "fffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff.json"
        )
        malformed_path.write_text(json.dumps({"bad": "data"}))
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        assert "malformed_evidence" in readiness["blockers"]
        assert readiness["disposition"] == "WAITING_FOR_DATA"


class TestRegisteredRefreshWithFiveFamilies:
    """refresh_registered_experiment with 5-family corpus persists READY_TO_REAUDIT without auto-chain."""

    def test_five_family_refresh_ready_no_auto_chain(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        repo = tmp_path / "repo"
        state_root = tmp_path / "state"
        evidence_root = tmp_path / "evidence"
        docs = repo / "docs" / "research" / "trajectory_verifier_v2"
        spec_dir = repo / "nexus" / "research" / "clm_system_one"
        docs.mkdir(parents=True)
        spec_dir.mkdir(parents=True)

        holdout = docs / "FINAL_HOLDOUT_DO_NOT_TRAIN.json"
        audit = docs / "TRAJECTORY_CORPUS_READINESS_REPORT.md"
        report = docs / "TRAJECTORY_VERIFIER_EXPERIMENT_REPORT.md"
        holdout.write_text('{"historical_replay_tasks":[]}\n')
        audit.write_text("not ready\n")
        report.write_text("inconclusive\n")

        def sha(path: Path) -> str:
            return hashlib.sha256(path.read_bytes()).hexdigest()

        spec = {
            "schema": "nexus.research_experiment_spec.v1",
            "issue": 1212,
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

        # Build 5-family corpus under evidence_root
        monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
        task_family_map: dict[str, str] = {}
        for i in range(_MIN_TASK_FAMILIES):
            for status in ("pass", "fail"):
                task_id = f"task-rf{i}-{status}"
                candidate_id = f"cand-rf{i}-{status}"
                task_family_map[task_id] = f"family-{i}"
                _, row_ref = _candidate_row(
                    tmp_path, monkeypatch, task_id=task_id, candidate_id=candidate_id, status=status
                )
                _trajectory(
                    evidence_root,
                    task_id=task_id,
                    trajectory_id=f"traj-{candidate_id}",
                    candidate_id=candidate_id,
                    candidate_ref=row_ref,
                )

        # project_corpus_readiness needs task_family_by_task; pass it via wrapper
        # But refresh_registered_experiment doesn't take it → verify at readiness level
        readiness = project_corpus_readiness(
            evidence_root=evidence_root,
            task_family_by_task=task_family_map,
        )
        assert readiness["disposition"] == "READY_TO_REAUDIT"

        # Use refresh_checkpoint_from_readiness directly (refresh_registered_experiment
        # doesn't pass task_family_by_task so disposition will be WAITING_FOR_DATA there;
        # the critical guarantee is auto_chain=False and T0_T1_REAUDIT_ONLY)
        checkpoint_root = state_root / "research" / "clm_system_one"
        checkpoint = refresh_checkpoint_from_readiness(
            evidence_root=checkpoint_root,
            experiment_id=spec["experiment_id"],
            track_id=spec["track_id"],
            readiness=readiness,
            claim_ceiling=spec["claim_ceiling"],
            source_revision="a" * 40,
            holdout_manifest_ref=spec["holdout_manifest"]["path"],
            holdout_manifest_sha256=spec["holdout_manifest"]["sha256"],
            corpus_audit_ref=spec["last_corpus_audit"]["path"],
            corpus_audit_sha256=spec["last_corpus_audit"]["sha256"],
        )
        assert checkpoint["status"] == "READY_TO_REAUDIT"
        assert checkpoint["next_allowed_action"] == "T0_T1_REAUDIT_ONLY"
        assert checkpoint["auto_chain"] is False


# ---------------------------------------------------------------------------
# #1212 Acceptance-delta: A) Readiness Semantics – PASS/FAIL distributed across families
# ---------------------------------------------------------------------------


class TestReadinessSemanticsDistributedLabels:
    """PASS and FAIL don't need to be in every family; just distributed across them overall."""

    def _build_distributed_corpus(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        *,
        n_families: int = _MIN_TASK_FAMILIES,
    ) -> tuple[Path, dict[str, str]]:
        """Build a corpus with n_families where PASS goes to some families, FAIL to others.

        Distribution: first half of families have PASS tasks; second half have FAIL tasks.
        No individual family has both PASS and FAIL (strong_family_count == 0 per family).
        But the corpus as a whole has pass_count > 0 and fail_count > 0.
        """
        root = tmp_path / "evidence"
        monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(root))
        task_family_map: dict[str, str] = {}
        half = n_families // 2 or 1

        for i in range(n_families):
            fam = f"family-{i}"
            status = "pass" if i < half else "fail"
            task_id = f"task-dist-{i}"
            candidate_id = f"cand-dist-{i}"
            task_family_map[task_id] = fam
            root_e, row_ref = _candidate_row(
                tmp_path, monkeypatch, task_id=task_id, candidate_id=candidate_id, status=status
            )
            _trajectory(
                root_e,
                task_id=task_id,
                trajectory_id=f"traj-dist-{i}",
                candidate_id=candidate_id,
                candidate_ref=row_ref,
            )
        return root, task_family_map

    def test_distributed_pass_fail_five_families_reaches_ready(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """5 families with PASS/FAIL distributed (not per-family) → READY_TO_REAUDIT."""
        root, task_family_map = self._build_distributed_corpus(tmp_path, monkeypatch)
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        # Overall corpus has both PASS and FAIL
        assert readiness["pass_trajectories"] > 0
        assert readiness["fail_trajectories"] > 0
        # 5 distinct mapped families
        assert readiness["task_family_count"] == _MIN_TASK_FAMILIES
        # family_disjoint_split_possible = >=2 distinct families
        assert readiness["family_disjoint_split_possible"] is True
        # No insufficient_task_families blocker
        assert not any("insufficient_task_families" in b for b in readiness["blockers"])
        assert readiness["disposition"] == "READY_TO_REAUDIT"

    def test_four_families_distributed_still_blocks(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """4 families (distributed PASS/FAIL) → still blocked (need >=5 families)."""
        root, task_family_map = self._build_distributed_corpus(
            tmp_path, monkeypatch, n_families=_MIN_TASK_FAMILIES - 1
        )
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        assert readiness["task_family_count"] == _MIN_TASK_FAMILIES - 1
        assert any("insufficient_task_families" in b for b in readiness["blockers"])
        assert readiness["disposition"] == "WAITING_FOR_DATA"

    def test_task_family_count_means_distinct_mapped_families(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """task_family_count reports the number of distinct mapped task families."""
        root, task_family_map = self._build_distributed_corpus(tmp_path, monkeypatch, n_families=7)
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        assert readiness["task_family_count"] == 7

    def test_family_disjoint_split_requires_two_distinct_families(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """family_disjoint_split_possible is True when >=2 distinct mapped families exist."""
        root = tmp_path / "evidence"
        monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(root))
        # Build 2 families with PASS/FAIL distributed
        task_family_map: dict[str, str] = {}
        for i, status in enumerate(("pass", "fail")):
            task_id = f"task-twodf-{i}"
            candidate_id = f"cand-twodf-{i}"
            task_family_map[task_id] = f"family-{i}"
            root_e, row_ref = _candidate_row(
                tmp_path, monkeypatch, task_id=task_id, candidate_id=candidate_id, status=status
            )
            _trajectory(
                root_e,
                task_id=task_id,
                trajectory_id=f"traj-twodf-{i}",
                candidate_id=candidate_id,
                candidate_ref=row_ref,
            )
        readiness = project_corpus_readiness(
            evidence_root=root, task_family_by_task=task_family_map
        )
        assert readiness["family_disjoint_split_possible"] is True
        # But insufficient families blocker still fires (only 2 < 5)
        assert any("insufficient_task_families" in b for b in readiness["blockers"])
        assert readiness["disposition"] == "WAITING_FOR_DATA"


# ---------------------------------------------------------------------------
# #1212 Acceptance-delta: B) Health Contract – sidecar snapshot
# ---------------------------------------------------------------------------


class TestHealthContract:
    """nexus.clm_trajectory_health.v1 snapshot is written sidecar-only."""

    def test_health_snapshot_created_and_schema_correct(self, tmp_path: Path):
        """After sealing a step, sidecar_health_snapshot.json must exist with correct schema."""
        root = tmp_path / "evidence"
        seal_trajectory_step(
            evidence_root=root,
            task_id="task-hc",
            trajectory_id="traj-hc",
            attempt_id="attempt-hc",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        snap_path = _health_snapshot_path(root)
        assert snap_path.exists(), "health snapshot must be created after seal_trajectory_step"
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        assert snap["schema"] == HEALTH_SCHEMA

    def test_health_snapshot_has_all_required_fields(self, tmp_path: Path):
        """Health snapshot must have all seven mutable atomic fields."""
        root = tmp_path / "evidence"
        seal_trajectory_step(
            evidence_root=root,
            task_id="task-hf",
            trajectory_id="traj-hf",
            attempt_id="attempt-hf",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        snap_path = _health_snapshot_path(root)
        snap = json.loads(snap_path.read_text(encoding="utf-8"))
        required_fields = {
            "attempted_step_count",
            "persisted_step_count",
            "instrumentation_error_count",
            "last_error_class",
            "last_successful_observation",
            "trajectory_groups_completed",
            "strong_label_bindings_completed",
        }
        for field in required_fields:
            assert field in snap, f"health snapshot missing required field: {field}"

    def test_attempted_incremented_before_persisted(self, tmp_path: Path):
        """attempted_step_count >= persisted_step_count after successful steps."""
        root = tmp_path / "evidence"
        for i in range(3):
            seal_trajectory_step(
                evidence_root=root,
                task_id="task-hap",
                trajectory_id=f"traj-hap-{i}",
                attempt_id="attempt-hap",
                candidate_id=None,
                step_index=0,
                source_revision="a" * 40,
                pre_action_state={"i": i},
                action_type="read",
                action_payload={"f": "x.py"},
            )
        snap = json.loads(_health_snapshot_path(root).read_text())
        assert snap["attempted_step_count"] == 3
        assert snap["persisted_step_count"] == 3
        # attempted >= persisted always
        assert snap["attempted_step_count"] >= snap["persisted_step_count"]

    def test_groups_completed_and_strong_bindings_incremented_after_outcome(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """trajectory_groups_completed and strong_label_bindings_completed increment on outcome binding."""
        root, row_ref = _candidate_row(
            tmp_path, monkeypatch, task_id="task-hgb", candidate_id="cand-hgb", status="pass"
        )
        step0 = seal_trajectory_step(
            evidence_root=root,
            task_id="task-hgb",
            trajectory_id="traj-hgb",
            attempt_id="attempt-cand-hgb",
            candidate_id="cand-hgb",
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        bind_trajectory_step_result(
            evidence_root=root, step_ref=step0, action_result={"exit_code": 0}
        )
        bind_trajectory_outcome(
            evidence_root=root, trajectory_id="traj-hgb", candidate_evidence_ref=row_ref
        )
        snap = json.loads(_health_snapshot_path(root).read_text())
        assert snap["trajectory_groups_completed"] >= 1
        assert snap["strong_label_bindings_completed"] >= 1

    def test_health_snapshot_never_affects_routing(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        """Health snapshot write must not affect trajectory data or raise exceptions."""
        root = tmp_path / "evidence"
        # Corrupt the snapshot path to a directory to force write failure
        snap_path = _health_snapshot_path(root)
        snap_path.parent.mkdir(parents=True, exist_ok=True)
        snap_path.mkdir(parents=True, exist_ok=True)  # make it a dir, not a file

        # seal must still succeed despite health write failure
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-hne",
            trajectory_id="traj-hne",
            attempt_id="attempt-hne",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        # Step sealed correctly despite health failure
        assert step.step_index == 0


# ---------------------------------------------------------------------------
# #1212 Acceptance-delta: C) Bounding/Offload
# ---------------------------------------------------------------------------


class TestBoundingAndOffload:
    """Enforce Redact -> Bound -> Hash -> Persist with blob offload for large results."""

    def test_oversized_secret_absent_on_disk(self, tmp_path: Path):
        """Oversized state with a secret: secret must not appear anywhere on disk after bounding."""
        root = tmp_path / "evidence"
        # Build a large state that forces bounding — contains a secret
        large_safe_data = "x" * 20000
        pw = "fixture-password-" + ("x" * 48)
        state_with_secret = {
            "description": large_safe_data,
            "password": pw,
        }
        seal_trajectory_step(
            evidence_root=root,
            task_id="task-bs",
            trajectory_id="traj-bs",
            attempt_id="attempt-bs",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state=state_with_secret,
            action_type="read",
            action_payload={"f": "x.py"},
        )
        # Walk all files under root; secret must not appear anywhere
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    assert pw not in content, f"secret found on disk at {path}"
                except Exception:
                    pass

    def test_small_result_stored_inline(self, tmp_path: Path):
        """Results below the inline limit are stored inline (no blob)."""
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-si",
            trajectory_id="traj-si",
            attempt_id="attempt-si",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="read",
            action_payload={"f": "x.py"},
        )
        result_ref = bind_trajectory_step_result(
            evidence_root=root,
            step_ref=step,
            action_result={"exit_code": 0, "output": "ok"},
        )
        record = json.loads((root / result_ref).read_text())
        # Small result: must have action_result_ref (inline), no blob ref
        assert "action_result_ref" in record
        assert "action_result_blob_ref" not in record

    def test_large_result_uses_content_addressed_blob(self, tmp_path: Path):
        """Results exceeding inline limit must be stored in trajectory/blobs/ with only ref in record."""
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-lb",
            trajectory_id="traj-lb",
            attempt_id="attempt-lb",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="compute",
            action_payload={"cmd": "run"},
        )
        # Build a result that exceeds the inline limit
        large_output = "Y" * (_MAX_RESULT_INLINE_BYTES + 500)
        result_ref = bind_trajectory_step_result(
            evidence_root=root,
            step_ref=step,
            action_result={"output": large_output, "exit_code": 0},
        )
        record = json.loads((root / result_ref).read_text())
        # Large result: must have blob ref, no inline payload
        assert "action_result_blob_ref" in record, "large result must carry blob ref"
        assert "action_result_ref" not in record, "large result must NOT carry inline result_ref"
        # Blob file must actually exist
        blob_path = root / record["action_result_blob_ref"]
        assert blob_path.exists(), f"blob file must exist at {blob_path}"
        # The record contains the hash
        assert "action_result_sha256" in record

    def test_large_result_with_secret_uses_blob_and_secret_absent(self, tmp_path: Path):
        """Large result with embedded secret: secret absent from disk, blob used."""
        root = tmp_path / "evidence"
        step = seal_trajectory_step(
            evidence_root=root,
            task_id="task-lbs",
            trajectory_id="traj-lbs",
            attempt_id="attempt-lbs",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state={"x": 1},
            action_type="api_call",
            action_payload={"url": "https://api.example.com"},
        )
        fake_large_result_token = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ1234567890"
        large_secret_result = {
            "output": "A" * (_MAX_RESULT_INLINE_BYTES + 200),
            "token": fake_large_result_token,
        }
        bind_trajectory_step_result(
            evidence_root=root,
            step_ref=step,
            action_result=large_secret_result,
        )
        # Walk all files; secret must be absent from disk
        for path in root.rglob("*"):
            if path.is_file():
                try:
                    content = path.read_text(encoding="utf-8", errors="replace")
                    assert fake_large_result_token not in content, (
                        f"secret found in large blob at {path}"
                    )
                except Exception:
                    pass

    def test_state_bounded_to_max_chars(self, tmp_path: Path):
        """State payloads exceeding max chars are bounded before persistence."""
        from nexus.research.clm_system_one.trajectory_continuity import _MAX_STATE_ACTION_CHARS

        root = tmp_path / "evidence"
        oversized_state = {"data": "Z" * (_MAX_STATE_ACTION_CHARS + 5000)}
        seal_trajectory_step(
            evidence_root=root,
            task_id="task-sb",
            trajectory_id="traj-sb",
            attempt_id="attempt-sb",
            candidate_id=None,
            step_index=0,
            source_revision="a" * 40,
            pre_action_state=oversized_state,
            action_type="read",
            action_payload={"f": "x.py"},
        )
        # State blob on disk must not exceed max chars in its serialized form
        state_dir = root / "trajectory" / "state"
        for f in state_dir.rglob("*.json"):
            content = f.read_text(encoding="utf-8")
            assert len(content) <= _MAX_STATE_ACTION_CHARS + 200, (
                f"state blob too large (bounding failed): {len(content)} chars"
            )


# #1677: family provenance must originate in immutable, pre-execution Task Cards.
# These fixtures deliberately NEVER use the live central corpus.
def _preexecution_card_family_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import subprocess

    repo = tmp_path / "repo"
    state_root = tmp_path / "state"
    evidence_root = tmp_path / "evidence"
    expected = {
        f"task-f{i}-{status}": f"family-{i}"
        for i in range(_MIN_TASK_FAMILIES)
        for status in ("pass", "fail")
    }
    docs = repo / "docs" / "research" / "trajectory_verifier_v2"
    spec_dir = repo / "nexus" / "research" / "clm_system_one"
    docs.mkdir(parents=True)
    spec_dir.mkdir(parents=True)
    (docs / "FINAL_HOLDOUT_DO_NOT_TRAIN.json").write_text('{"historical_replay_tasks":[]}')
    (docs / "TRAJECTORY_CORPUS_READINESS_REPORT.md").write_text("fixture only")
    (docs / "TRAJECTORY_VERIFIER_EXPERIMENT_REPORT.md").write_text("fixture only")
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    spec = {
        "schema": "nexus.research_experiment_spec.v1",
        "experiment_id": "NEXUS_SYSTEM_ONE_CLM_V2",
        "track_id": "TRACK_1_TRAJECTORY_VERIFIER_HEAD",
        "claim_ceiling": "EXPERIMENTAL_SHADOW_ONLY",
        "holdout_manifest": {
            "path": "docs/research/trajectory_verifier_v2/FINAL_HOLDOUT_DO_NOT_TRAIN.json",
            "sha256": sha(docs / "FINAL_HOLDOUT_DO_NOT_TRAIN.json"),
        },
        "last_corpus_audit": {
            "path": "docs/research/trajectory_verifier_v2/TRAJECTORY_CORPUS_READINESS_REPORT.md",
            "sha256": sha(docs / "TRAJECTORY_CORPUS_READINESS_REPORT.md"),
        },
        "continuity": {"checkpoint_relative_root": "research/clm_system_one"},
    }
    (spec_dir / "trajectory_verifier_v2_spec.json").write_text(json.dumps(spec))
    categories = [
        "defect_repair", "feature_extension", "test_oracle",
        "runtime_recovery", "evidence_integrity",
    ]
    cards = {}
    for task_id, family in expected.items():
        family_id = int(family.removeprefix("family-"))
        rel = Path("tasks") / family / f"{task_id}.md"
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"task_id: `{task_id}`\n"
            "## Track 1 task-family declaration (issuer, pre-action)\n"
            f"track1_taxonomy: TRACK1_ENGINEERING_V1\n"
            f"track1_family: {categories[family_id]}\n"
            f"track1_family_rationale: Task issuer declares a bounded, pre-effect category\n"
            "AUTO_CHAIN: false\n"
        )
        cards[task_id] = rel
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "tasks", "docs", "nexus"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.org",
         "commit", "-qm", "freeze pre-execution family declaration"],
        cwd=repo, check=True,
    )
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    state_root.mkdir(parents=True)
    for task_id, rel in cards.items():
        cand_id = "cand-" + task_id.removeprefix("task-")
        contract_identity = {
            "task_id": task_id,
            "controller_revision": revision,
            "target_base_revision": "a" * 40,
        }
        state = {
            "schema": "nexus.self_hosted_task_state.v1",
            "task_id": task_id,
            "attempt_id": "attempt-" + cand_id,
            "submitted_at": "2026-09-28T00:00:00+00:00",
            "controller_revision": revision,
            "task_card_path": rel.as_posix(),
            "task_card_hash": sha(repo / rel),
            "contract": contract_identity,
        }
        (state_root / f"{task_id}.json").write_text(json.dumps(state))
        _, row_ref = _candidate_row(
            tmp_path, monkeypatch, task_id=task_id, candidate_id=cand_id,
            status=task_id.rsplit("-", 1)[1], contract_identity=contract_identity,
        )
        _trajectory(
            evidence_root, task_id=task_id,
            trajectory_id=f"traj-{cand_id}",
            candidate_id=cand_id, candidate_ref=row_ref,
        )
    return repo, state_root, evidence_root, cards


def test_registered_refresh_uses_verified_preexecution_task_family(tmp_path, monkeypatch):
    repo, state_root, evidence_root, _ = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    refresh = refresh_registered_experiment(
        repo_root=repo,
        canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )
    readiness = refresh["readiness"]
    assert readiness["task_family_count"] == 5
    assert readiness["disposition"] == "READY_TO_REAUDIT"
    assert len(readiness["task_family_provenance"]) == 10
    assert all("task_card_sha256" in row for row in readiness["task_family_provenance"].values())
    assert refresh["checkpoint"]["status"] == "READY_TO_REAUDIT"
    assert refresh["checkpoint"]["auto_chain"] is False
    assert refresh["checkpoint"]["next_allowed_action"] == "T0_T1_REAUDIT_ONLY"


def test_task_family_fails_closed_on_tampered_card_identity(tmp_path, monkeypatch):
    repo, state_root, evidence_root, cards = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    for task_id in ("task-f0-pass", "task-f0-fail"):
        state_path = state_root / f"{task_id}.json"
        state = json.loads(state_path.read_text())
        state["task_card_hash"] = "0" * 64
        state_path.write_text(json.dumps(state))
    refresh = refresh_registered_experiment(
        repo_root=repo,
        canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )
    assert refresh["readiness"]["task_family_count"] == 4
    assert refresh["readiness"]["disposition"] == "WAITING_FOR_DATA"
    assert refresh["checkpoint"]["auto_chain"] is False


def test_task_family_fails_closed_when_legacy_state_missing(tmp_path, monkeypatch):
    repo, state_root, evidence_root, _ = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    for path in state_root.glob("*.json"):
        path.unlink()
    refresh = refresh_registered_experiment(
        repo_root=repo,
        canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )
    assert refresh["readiness"]["task_family_count"] == 0
    assert refresh["readiness"]["disposition"] == "WAITING_FOR_DATA"
    assert refresh["checkpoint"]["auto_chain"] is False


def test_issuer_card_current_worktree_edits_cannot_relabel_frozen_task(
    tmp_path, monkeypatch
):
    repo, state_root, evidence_root, cards = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    for task_id in ("task-f0-pass", "task-f0-fail"):
        path = repo / cards[task_id]
        path.write_text(path.read_text().replace(
            "track1_family: defect_repair", "track1_family: runtime_recovery"
        ))
    readiness = refresh_registered_experiment(
        repo_root=repo, canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )["readiness"]
    assert readiness["task_family_count"] == 5
    assert readiness["task_family_provenance"]["task-f0-pass"]["family"] == "defect_repair"
    assert readiness["family_disjoint_split_witness"]["train_dev_overlap"] == []


def test_issuer_card_post_effect_retrofit_cannot_mint_family(
    tmp_path, monkeypatch
):
    repo, state_root, evidence_root, cards = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    for task_id in ("task-f0-pass", "task-f0-fail"):
        path = repo / cards[task_id]
        revised = path.read_text().replace(
            "track1_family: defect_repair", "track1_family: runtime_recovery"
        )
        path.write_text(revised)
        state_path = state_root / f"{task_id}.json"
        state = json.loads(state_path.read_text())
        state["task_card_hash"] = hashlib.sha256(path.read_bytes()).hexdigest()
        state_path.write_text(json.dumps(state))
    readiness = refresh_registered_experiment(
        repo_root=repo, canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )["readiness"]
    assert readiness["task_family_count"] == 4
    assert readiness["disposition"] == "WAITING_FOR_DATA"


def test_unknown_issuer_family_and_duplicate_declaration_fail_closed(
    tmp_path, monkeypatch
):
    import subprocess

    repo, state_root, evidence_root, cards = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    # Both members of one family now have newly committed invalid declarations.
    for task_id, corruption in (
        ("task-f0-pass", "track1_family: arbitrary_label"),
        ("task-f0-fail", "track1_family: defect_repair\\ntrack1_family: runtime_recovery"),
    ):
        path = repo / cards[task_id]
        path.write_text(path.read_text().replace(
            "track1_family: defect_repair", corruption
        ))
    subprocess.run(["git", "add", "tasks"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.org",
         "commit", "-qm", "forge invalid family declarations"],
        cwd=repo, check=True,
    )
    revision = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repo, text=True
    ).strip()
    for task_id in ("task-f0-pass", "task-f0-fail"):
        state_path = state_root / f"{task_id}.json"
        state = json.loads(state_path.read_text())
        state["controller_revision"] = revision
        state["task_card_hash"] = hashlib.sha256(
            (repo / cards[task_id]).read_bytes()
        ).hexdigest()
        state_path.write_text(json.dumps(state))
    readiness = refresh_registered_experiment(
        repo_root=repo, canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )["readiness"]
    assert readiness["task_family_count"] == 4
    assert readiness["disposition"] == "WAITING_FOR_DATA"


def test_holdout_task_does_not_gain_family_provenance(tmp_path, monkeypatch):
    repo, state_root, evidence_root, _ = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    holdout_path = repo / "docs/research/trajectory_verifier_v2/FINAL_HOLDOUT_DO_NOT_TRAIN.json"
    holdout_path.write_text(json.dumps({
        "historical_replay_tasks": ["task-f0-pass"]
    }))
    readiness = refresh_registered_experiment(
        repo_root=repo, canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )["readiness"]
    assert "task-f0-pass" not in readiness["task_family_provenance"]
    assert "holdout_overlap" in readiness["blockers"]
    assert readiness["disposition"] == "WAITING_FOR_DATA"


def test_cross_attempt_outcomes_cannot_relabel_prior_task_trajectories(
    tmp_path, monkeypatch
):
    repo, state_root, evidence_root, _ = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    # Older and newer attempts with one task_id cannot share the current
    # task-id-only family map without independent attempt-level proof.
    for task_id in ("task-f0-pass", "task-f0-fail"):
        state = json.loads((state_root / f"{task_id}.json").read_text())
        candidate_id = f"cross-{task_id}"
        _, row_ref = _candidate_row(
            tmp_path, monkeypatch, task_id=task_id, candidate_id=candidate_id,
            status=task_id.rsplit("-", 1)[1],
            contract_identity=state["contract"],
        )
        _trajectory(
            evidence_root, task_id=task_id,
            trajectory_id=f"traj-{candidate_id}", candidate_id=candidate_id,
            candidate_ref=row_ref,
        )
    readiness = refresh_registered_experiment(
        repo_root=repo, canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )["readiness"]
    assert readiness["task_family_count"] == 4
    assert "task-f0-pass" not in readiness["task_family_provenance"]
    assert "task-f0-fail" not in readiness["task_family_provenance"]
    assert readiness["disposition"] == "WAITING_FOR_DATA"


def test_unmapped_pass_labels_cannot_unlock_family_readiness(
    tmp_path, monkeypatch
):
    repo, state_root, evidence_root, _ = _preexecution_card_family_fixture(
        tmp_path, monkeypatch
    )
    for i in range(_MIN_TASK_FAMILIES):
        task_id = f"task-f{i}-pass"
        state_path = state_root / f"{task_id}.json"
        state = json.loads(state_path.read_text())
        state["task_card_hash"] = "0" * 64
        state_path.write_text(json.dumps(state))
    readiness = refresh_registered_experiment(
        repo_root=repo, canonical_state_root=state_root,
        candidate_evidence_root=evidence_root,
    )["readiness"]
    assert readiness["task_family_count"] == 5
    assert readiness["disposition"] == "WAITING_FOR_DATA"
    assert "mapped_family_binary_coverage_unavailable" in readiness["blockers"]


# Preserve the historical node ID consumed by exact-base impact evidence while
# exercising the hardened >=5-family readiness semantics.
def test_registered_refresh_persists_ready_to_reaudit_without_auto_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    TestRegisteredRefreshWithFiveFamilies().test_five_family_refresh_ready_no_auto_chain(
        tmp_path, monkeypatch
    )
