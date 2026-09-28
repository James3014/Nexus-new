from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from nexus.research.clm_system_one.candidate_evidence_collector import (
    collect_candidate_group,
)


def _candidate(
    candidate_id: str,
    payload: str,
    *,
    verifier_status: str,
    selected: bool = False,
) -> dict:
    return {
        "candidate_id": candidate_id,
        "candidate_model": f"model-{candidate_id}",
        "candidate_source": "test",
        "candidate_payload": payload,
        "candidate_payload_sha256": hashlib.sha256(payload.encode()).hexdigest(),
        "candidate_state_hash": hashlib.sha256(f"state-{candidate_id}".encode()).hexdigest(),
        "verifier_status": verifier_status,
        "label_quality": "ISOLATED_VERIFIER",
        "verifier_evidence": {
            "verifier": "pytest",
            "verifier_invoked": True,
            "verifier_status": verifier_status,
            "exit_code": 0 if verifier_status == "pass" else 1,
        },
        "failure_reason_codes": [] if verifier_status == "pass" else ["verifier_failed"],
        "selected": selected,
    }


def _collect(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, candidates: list[dict]):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "100")
    result = collect_candidate_group(
        repo_root=tmp_path,
        task_id="task-1",
        attempt_id="attempt-1",
        collector_source="unit_test",
        source_revision="a" * 40,
        contract_identity={"problem": "fix x", "target_file": "x.py"},
        verifier_identity={"kind": "pytest", "command": ["pytest", "-q", "tests/test_x.py"]},
        candidates=candidates,
        winner_id="A",
    )
    return evidence_root, result


def test_collects_winner_and_loser_with_same_group_binding(tmp_path: Path, monkeypatch):
    root, result = _collect(
        tmp_path,
        monkeypatch,
        [
            _candidate("A", "patch-a", verifier_status="pass", selected=True),
            _candidate("B", "patch-b", verifier_status="fail"),
        ],
    )
    assert result.status == "COLLECTED"
    assert result.collected_count == 2
    assert result.eligible_count == 2
    rows = [json.loads((root / ref).read_text(encoding="utf-8")) for ref in result.row_refs]
    assert {row["candidate_id"] for row in rows} == {"A", "B"}
    assert {row["comparison_group_sha256"] for row in rows} == {result.group_sha256}
    assert {row["verifier_status"] for row in rows} == {"PASS", "FAIL"}
    assert [row["candidate_id"] for row in rows if row["selected"]] == ["A"]
    assert all(row["winner_id"] == "A" for row in rows)
    assert all(row["dataset_eligible"] is True for row in rows)
    assert all((root / row["candidate_payload_ref"]).exists() for row in rows)
    assert (root / result.manifest_ref).exists()


def test_unknown_verifier_is_preserved_but_not_dataset_eligible(tmp_path: Path, monkeypatch):
    root, result = _collect(
        tmp_path,
        monkeypatch,
        [_candidate("A", "patch-a", verifier_status="blocked")],
    )
    row = json.loads((root / result.row_refs[0]).read_text(encoding="utf-8"))
    assert row["verifier_status"] == "UNKNOWN"
    assert row["dataset_eligible"] is False


def test_duplicate_collection_is_idempotent(tmp_path: Path, monkeypatch):
    candidates = [
        _candidate("A", "patch-a", verifier_status="pass", selected=True),
        _candidate("B", "patch-b", verifier_status="fail"),
    ]
    root, first = _collect(tmp_path, monkeypatch, candidates)
    _, second = _collect(tmp_path, monkeypatch, candidates)
    assert first.row_sha256 == second.row_sha256
    assert first.row_refs == second.row_refs
    assert len(list((root / "groups" / first.group_sha256).glob("*.json"))) == 2


def test_payload_hash_mismatch_rejected(tmp_path: Path, monkeypatch):
    candidate = _candidate("A", "patch-a", verifier_status="pass")
    candidate["candidate_payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="candidate payload hash mismatch"):
        _collect(tmp_path, monkeypatch, [candidate])


def test_disabled_collection_has_no_files(tmp_path: Path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "0")
    result = collect_candidate_group(
        repo_root=tmp_path,
        task_id="task-1",
        attempt_id="attempt-1",
        collector_source="unit_test",
        source_revision="a" * 40,
        contract_identity={"problem": "fix x"},
        verifier_identity={"kind": "pytest"},
        candidates=[_candidate("A", "patch-a", verifier_status="pass")],
    )
    assert result.status == "SKIPPED"
    assert result.skipped_reason == "disabled"
    assert not evidence_root.exists()


def test_sampling_is_deterministic_and_does_not_run_any_verifier(tmp_path: Path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "0")
    result = collect_candidate_group(
        repo_root=tmp_path,
        task_id="task-1",
        attempt_id="attempt-1",
        collector_source="unit_test",
        source_revision="a" * 40,
        contract_identity={"problem": "fix x"},
        verifier_identity={"kind": "pytest"},
        candidates=[_candidate("A", "patch-a", verifier_status="pass")],
    )
    assert result.status == "SKIPPED"
    assert result.skipped_reason == "deterministic_sampling"
    assert not evidence_root.exists()


def test_state_hash_only_binds_but_is_not_training_eligible(tmp_path: Path, monkeypatch):
    candidate = _candidate("A", "", verifier_status="pass")
    candidate["candidate_payload_sha256"] = ""
    root, result = _collect(tmp_path, monkeypatch, [candidate])
    row = json.loads((root / result.row_refs[0]).read_text(encoding="utf-8"))
    assert row["binding_complete"] is True
    assert row["candidate_state_hash"]
    assert row["candidate_payload_ref"] == ""
    assert row["dataset_eligible"] is False


@pytest.mark.parametrize(
    ("contract_identity", "verifier_identity"),
    [
        ({}, {"kind": "pytest"}),
        ({"problem": "fix"}, {}),
        (None, {"kind": "pytest"}),
        ({"problem": "fix"}, None),
    ],
)
def test_empty_contract_or_verifier_identity_cannot_bind(
    tmp_path: Path,
    monkeypatch,
    contract_identity,
    verifier_identity,
):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    result = collect_candidate_group(
        repo_root=tmp_path,
        task_id="task-1",
        attempt_id="attempt-1",
        collector_source="unit_test",
        source_revision="a" * 40,
        contract_identity=contract_identity,
        verifier_identity=verifier_identity,
        candidates=[_candidate("A", "patch-a", verifier_status="pass")],
    )
    row = json.loads((evidence_root / result.row_refs[0]).read_text())
    assert row["binding_complete"] is False
    assert row["dataset_eligible"] is False


def test_pass_fail_without_verifier_evidence_is_not_dataset_eligible(tmp_path: Path, monkeypatch):
    candidate = _candidate("A", "patch-a", verifier_status="pass")
    candidate["verifier_evidence"] = {}
    root, result = _collect(tmp_path, monkeypatch, [candidate])
    row = json.loads((root / result.row_refs[0]).read_text())
    assert row["verifier_status"] == "PASS"
    assert row["dataset_eligible"] is False


def test_isolated_verifier_evidence_status_must_match_row(tmp_path: Path, monkeypatch):
    candidate = _candidate("A", "patch-a", verifier_status="pass")
    candidate["verifier_evidence"]["verifier_status"] = "fail"
    root, result = _collect(tmp_path, monkeypatch, [candidate])
    row = json.loads((root / result.row_refs[0]).read_text())
    assert row["verifier_status"] == "PASS"
    assert row["dataset_eligible"] is False


def test_mechanical_gate_requires_nonempty_gate_results(tmp_path: Path, monkeypatch):
    candidate = _candidate("A", "patch-a", verifier_status="pass")
    candidate["label_quality"] = "MECHANICAL_GATE"
    candidate["verifier_evidence"] = {
        "verifier_kind": "cli_pregate",
        "gate_results": [],
    }
    root, result = _collect(tmp_path, monkeypatch, [candidate])
    row = json.loads((root / result.row_refs[0]).read_text())
    assert row["dataset_eligible"] is False


@pytest.mark.parametrize(
    ("row_status", "gate_passed"),
    [
        ("pass", False),
        ("fail", True),
    ],
)
def test_mechanical_gate_status_must_match_aggregate_gate_truth(
    tmp_path: Path, monkeypatch, row_status: str, gate_passed: bool
):
    candidate = _candidate("A", "patch-a", verifier_status=row_status)
    candidate["label_quality"] = "MECHANICAL_GATE"
    candidate["verifier_evidence"] = {
        "verifier_kind": "cli_pregate",
        "gate_results": [
            {
                "cmd_sha256": hashlib.sha256(b"pytest -q").hexdigest(),
                "passed": gate_passed,
                "exit_code": 0 if gate_passed else 1,
            }
        ],
    }
    root, result = _collect(tmp_path, monkeypatch, [candidate])
    row = json.loads((root / result.row_refs[0]).read_text())
    assert row["verifier_status"] == row_status.upper()
    assert row["dataset_eligible"] is False


@pytest.mark.parametrize(
    ("row_status", "gate_results"),
    [
        (
            "pass",
            [
                {
                    "cmd_sha256": hashlib.sha256(b"pytest -q").hexdigest(),
                    "passed": True,
                    "exit_code": 0,
                }
            ],
        ),
        (
            "fail",
            [
                {
                    "cmd_sha256": hashlib.sha256(b"pytest -q").hexdigest(),
                    "passed": True,
                    "exit_code": 0,
                },
                {
                    "cmd_sha256": hashlib.sha256(b"ruff check").hexdigest(),
                    "passed": False,
                    "exit_code": 1,
                },
            ],
        ),
    ],
)
def test_mechanical_gate_matching_aggregate_truth_is_eligible(
    tmp_path: Path, monkeypatch, row_status: str, gate_results: list[dict]
):
    candidate = _candidate("A", "patch-a", verifier_status=row_status)
    candidate["label_quality"] = "MECHANICAL_GATE"
    candidate["verifier_evidence"] = {
        "verifier_kind": "cli_pregate",
        "gate_results": gate_results,
    }
    root, result = _collect(tmp_path, monkeypatch, [candidate])
    row = json.loads((root / result.row_refs[0]).read_text())
    assert row["dataset_eligible"] is True


@pytest.mark.parametrize("status", [None, "", "partial", "timeout", "blocked", "not_run"])
def test_non_terminal_verifier_outcome_is_unknown_and_ineligible(
    tmp_path: Path, monkeypatch, status
):
    candidate = _candidate("A", "patch-a", verifier_status="pass")
    candidate["verifier_status"] = status
    root, result = _collect(tmp_path, monkeypatch, [candidate])
    row = json.loads((root / result.row_refs[0]).read_text())
    assert row["verifier_status"] == "UNKNOWN"
    assert row["dataset_eligible"] is False


def test_group_binding_changes_when_authoritative_identity_drifts(tmp_path: Path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    candidate = _candidate("A", "patch-a", verifier_status="pass")

    def run(task_id, revision, contract, verifier):
        return collect_candidate_group(
            repo_root=tmp_path,
            task_id=task_id,
            attempt_id="attempt-1",
            collector_source="unit_test",
            source_revision=revision,
            contract_identity=contract,
            verifier_identity=verifier,
            candidates=[candidate],
        ).group_sha256

    base = run("task-1", "a" * 40, {"problem": "x"}, {"kind": "pytest"})
    assert run("task-2", "a" * 40, {"problem": "x"}, {"kind": "pytest"}) != base
    assert run("task-1", "b" * 40, {"problem": "x"}, {"kind": "pytest"}) != base
    assert run("task-1", "a" * 40, {"problem": "y"}, {"kind": "pytest"}) != base
    assert run("task-1", "a" * 40, {"problem": "x"}, {"kind": "cargo"}) != base


def test_group_binding_changes_when_candidate_set_changes(tmp_path: Path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    common = dict(
        repo_root=tmp_path,
        task_id="task-1",
        attempt_id="attempt-1",
        collector_source="unit_test",
        source_revision="a" * 40,
        contract_identity={"problem": "fix x"},
        verifier_identity={"kind": "pytest"},
    )
    first = collect_candidate_group(
        **common,
        candidates=[_candidate("A", "patch-a", verifier_status="pass")],
    )
    second = collect_candidate_group(
        **common,
        candidates=[_candidate("A", "patch-b", verifier_status="pass")],
    )
    assert first.group_sha256 != second.group_sha256
    assert first.manifest_ref != second.manifest_ref


def test_foreign_candidate_verifier_bundle_is_rejected(tmp_path: Path, monkeypatch):
    candidate = _candidate("A", "patch-a", verifier_status="pass")
    candidate["verifier_bundle_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="candidate verifier bundle mismatch"):
        _collect(tmp_path, monkeypatch, [candidate])


def test_invalid_later_candidate_leaves_no_partial_group(tmp_path: Path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    good = _candidate("A", "patch-a", verifier_status="pass")
    bad = _candidate("B", "patch-b", verifier_status="fail")
    bad["candidate_payload_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="candidate payload hash mismatch"):
        collect_candidate_group(
            repo_root=tmp_path,
            task_id="task-1",
            attempt_id="attempt-1",
            collector_source="unit_test",
            source_revision="a" * 40,
            contract_identity={"problem": "fix x"},
            verifier_identity={"kind": "pytest"},
            candidates=[good, bad],
        )
    assert not evidence_root.exists()


def test_invalid_candidate_state_hash_is_rejected(tmp_path: Path, monkeypatch):
    candidate = _candidate("A", "patch-a", verifier_status="pass")
    candidate["candidate_state_hash"] = "not-a-sha"
    with pytest.raises(ValueError, match="invalid candidate state hash"):
        _collect(tmp_path, monkeypatch, [candidate])


def test_invalid_explicit_source_revision_is_rejected(tmp_path: Path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    with pytest.raises(ValueError, match="invalid source revision"):
        collect_candidate_group(
            repo_root=tmp_path,
            task_id="task-1",
            attempt_id="attempt-1",
            collector_source="unit_test",
            source_revision="not-a-git-oid",
            contract_identity={"problem": "fix x"},
            verifier_identity={"kind": "pytest"},
            candidates=[_candidate("A", "patch-a", verifier_status="pass")],
        )
    assert not evidence_root.exists()


def test_existing_tampered_row_is_never_overwritten(tmp_path: Path, monkeypatch):
    root, first = _collect(
        tmp_path,
        monkeypatch,
        [_candidate("A", "patch-a", verifier_status="pass")],
    )
    row_path = root / first.row_refs[0]
    row_path.write_bytes(b"tampered\n")
    before = row_path.read_bytes()
    with pytest.raises(RuntimeError, match="immutable evidence collision"):
        _collect(
            tmp_path,
            monkeypatch,
            [_candidate("A", "patch-a", verifier_status="pass")],
        )
    assert row_path.read_bytes() == before


def test_exact_retry_does_not_create_extra_content_objects(tmp_path: Path, monkeypatch):
    candidates = [
        _candidate("A", "patch-a", verifier_status="pass", selected=True),
        _candidate("B", "patch-b", verifier_status="fail"),
    ]
    root, first = _collect(tmp_path, monkeypatch, candidates)

    def snapshot():
        return {
            "rows": sorted(
                p.relative_to(root).as_posix()
                for p in (root / "groups" / first.group_sha256).glob("*.json")
            ),
            "blobs": sorted(
                p.relative_to(root).as_posix() for p in (root / "blobs").rglob("*.txt")
            ),
            "verifier": sorted(
                p.relative_to(root).as_posix() for p in (root / "verifier").rglob("*.json")
            ),
            "complete": (root / first.manifest_ref).read_bytes(),
        }

    before = snapshot()
    _, second = _collect(tmp_path, monkeypatch, candidates)
    after = snapshot()
    assert first.group_sha256 == second.group_sha256
    assert first.row_sha256 == second.row_sha256
    assert before == after


def test_sampling_decision_is_stable_for_same_group_at_midrange_rate(tmp_path: Path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "50")
    kwargs = dict(
        repo_root=tmp_path,
        task_id="stable-sampling",
        attempt_id="attempt-1",
        collector_source="unit_test",
        source_revision="a" * 40,
        contract_identity={"problem": "fix x"},
        verifier_identity={"kind": "pytest"},
        candidates=[_candidate("A", "patch-a", verifier_status="pass")],
    )
    first = collect_candidate_group(**kwargs)
    second = collect_candidate_group(**kwargs)
    assert first.status == second.status
    assert first.skipped_reason == second.skipped_reason
    assert first.group_sha256 == second.group_sha256


def test_concurrent_identical_collection_is_idempotent(tmp_path: Path, monkeypatch):
    evidence_root = tmp_path / "evidence"
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ROOT", str(evidence_root))
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_ENABLED", "1")
    monkeypatch.setenv("NEXUS_CLM_CANDIDATE_EVIDENCE_RATE_PERCENT", "100")
    kwargs = dict(
        repo_root=tmp_path,
        task_id="concurrent-task",
        attempt_id="attempt-1",
        collector_source="unit_test",
        source_revision="a" * 40,
        contract_identity={"problem": "fix x"},
        verifier_identity={"kind": "pytest"},
        candidates=[
            _candidate("A", "patch-a", verifier_status="pass", selected=True),
            _candidate("B", "patch-b", verifier_status="fail"),
        ],
        winner_id="A",
    )
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _n: collect_candidate_group(**kwargs), range(16)))
    assert {result.group_sha256 for result in results} == {results[0].group_sha256}
    assert {result.row_sha256 for result in results} == {results[0].row_sha256}
    group_dir = evidence_root / "groups" / results[0].group_sha256
    assert len(list(group_dir.glob("*.json"))) == 2
    assert (group_dir / ".complete").exists()
    assert not list(evidence_root.rglob("*.tmp"))
