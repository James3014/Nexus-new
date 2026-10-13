import importlib.util
import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[2]


CORE_ROOT: Path | None = None
SCRIPT_PATH = ROOT / "scripts" / "ops" / "nexus-hermes-core-completion"

LOADER = SourceFileLoader("nexus_hermes_core_completion", str(SCRIPT_PATH))
SPEC = importlib.util.spec_from_loader("nexus_hermes_core_completion", LOADER)
assert SPEC is not None
MOD = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(MOD)


_SYNTHETIC_EVIDENCE = """\
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any


def _hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


class ObservationStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"


@dataclass(frozen=True)
class AcceptanceContract:
    contract_id: str
    requirements_hash: str
    required_verifier_ids: tuple[str, ...]
    allowed_paths: tuple[str, ...]
    deletion_policy: str

    @property
    def hash(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class ChangeSet:
    change_set_id: str
    source_revision: str
    target_revision: str
    diff_hash: str
    paths: tuple[str, ...]
    deleted_paths: tuple[str, ...]

    @property
    def hash(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class VerificationPlan:
    plan_id: str
    acceptance_contract_hash: str
    change_set_hash: str
    required_verifier_ids: tuple[str, ...]

    @property
    def hash(self) -> str:
        return _hash(asdict(self))


@dataclass(frozen=True)
class Observation:
    verifier_id: str
    artifact_id: str
    artifact_hash: str
    status: ObservationStatus


@dataclass(frozen=True)
class EvidenceBundle:
    bundle_id: str
    acceptance_contract_hash: str
    change_set_hash: str
    verification_plan_hash: str
    observations: tuple[Observation, ...]
"""


_SYNTHETIC_COMPLETION = """\
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


def _hash(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class CompletionClaim:
    claim_id: str
    target_revision: str
    content_hashes: tuple[tuple[str, str], ...]
    verified_artifacts: tuple[tuple[str, str, str], ...]
    asserted_by: str
    claimed_complete: bool = True


@dataclass(frozen=True)
class _Analysis:
    claims_complete: bool
    claims_verified: bool
    verification_applies: bool
    reason_codes: tuple[str, ...]
    dispositions: tuple[Any, ...]

    @property
    def hash(self) -> str:
        return _hash(
            {
                "claims_complete": self.claims_complete,
                "claims_verified": self.claims_verified,
                "verification_applies": self.verification_applies,
                "reason_codes": self.reason_codes,
            }
        )


def analyze_completion_evidence(claim, contract, change_set, plan, evidence):
    del contract, change_set, plan
    reasons = []
    applies = True
    verified = claim is not None and bool(evidence.observations)
    if not verified:
        reasons.append("MISSING:verifier")
        return _Analysis(False, False, False, tuple(reasons), ())

    observation = evidence.observations[0]
    if observation.status.value != "PASS":
        verified = False
        applies = False
        reasons.append("CONTRADICTORY:verifier")

    paths = {
        artifact_id: path
        for _, artifact_id, path in claim.verified_artifacts
    }
    path = paths.get(observation.artifact_id)
    if path is None:
        verified = False
        reasons.append("IRRELEVANT:verifier")
    elif dict(claim.content_hashes).get(path) != observation.artifact_hash:
        verified = False
        reasons.append("STALE:verifier")

    complete = bool(claim.claimed_complete and verified)
    return _Analysis(complete, verified, applies, tuple(reasons), ())


def validate_completion_evidence_analysis(
    analysis,
    claim,
    contract,
    change_set,
    plan,
    evidence,
):
    del analysis, claim, contract, change_set, plan, evidence
    return True
"""


@pytest.fixture
def clean_core_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "synthetic-core"
    product = repo / "product"
    product.mkdir(parents=True)
    (product / "__init__.py").write_text("", encoding="utf-8")
    (product / "evidence.py").write_text(_SYNTHETIC_EVIDENCE, encoding="utf-8")
    (product / "completion.py").write_text(_SYNTHETIC_COMPLETION, encoding="utf-8")
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "synthetic core fixture"],
        check=True,
        capture_output=True,
    )
    return repo


@pytest.fixture
def require_usable_core(clean_core_repo: Path):
    global CORE_ROOT
    CORE_ROOT = clean_core_repo


@pytest.fixture
def clean_core_identity(require_usable_core):
    assert CORE_ROOT is not None
    commit, tree = MOD.prove_clean_core_repo(CORE_ROOT)
    return commit, tree


def _make_valid_envelope(
    *,
    issue_number=1419,
    run_id="run-test-01",
    operation_id="agyop_valid123",
    source_revision="4f4e52787621e31adb00cd4e9136362d72a144e7",
    source_tree="git-tree:source123",
    target_revision="git-tree:target456",
    path="scripts/ops/nexus-hermes-core-completion",
    content_hash="sha256:1111111111111111111111111111111111111111111111111111111111111111",
    verifier_id="deterministic-pytest",
    verifier_status="PASS",
    verifier_artifact_hash=None,
    artifact_id="art-completion-01",
    verifier_artifact_id=None,
):
    obs_art_id = verifier_artifact_id or artifact_id
    art_hash = verifier_artifact_hash or content_hash
    artifacts = [
        {
            "artifact_id": artifact_id,
            "content_hash": content_hash,
            "path": path,
        }
    ]
    obs = {
        "artifact_id": obs_art_id,
        "artifact_hash": art_hash,
        "status": verifier_status,
        "verifier_id": verifier_id,
    }
    return MOD.materialize_work_product_envelope(
        issue_number=issue_number,
        run_id=run_id,
        operation_id=operation_id,
        source_revision=source_revision,
        source_tree=source_tree,
        target_revision=target_revision,
        artifacts=artifacts,
        verifier_observation=obs,
    )


def _valid_operation_evidence(
    *,
    operation_id="agyop_valid123",
    base_head="4f4e52787621e31adb00cd4e9136362d72a144e7",
):
    return {
        "schema": "nexus.agy_operation.v1",
        "operation_id": operation_id,
        "status": "COMPLETED",
        "phase": "TERMINAL",
        "exit_code": 0,
        "has_unresolved_external_effect": False,
        "permission_profile_sha256": "a" * 64,
        "permission_profile_kind": "READ_ONLY_RESEARCH",
        "effective_permissions": {
            "allow": ["read_file(/tmp/repo/**)"],
            "deny": ["write_file(*)", "command(*)"],
        },
        "write_paths": [],
        "scope_validation_state": "UNCONSTRAINED",
        "scope_violations": [],
        "source_attribution_state": "ATTRIBUTED",
        "base_head": base_head,
    }


def test_validate_operation_evidence_accepts_canonical_public_view():
    assert (
        MOD.validate_operation_evidence(
            _valid_operation_evidence(),
            expected_operation_id="agyop_valid123",
        )
        == []
    )


def test_read_operation_evidence_missing_binary_fails_closed(tmp_path):
    with pytest.raises(
        MOD.CoreCompletionError,
        match="OPERATION_EVIDENCE_UNAVAILABLE:FileNotFoundError",
    ):
        MOD.read_operation_evidence(
            "agyop_missing123",
            dispatch_bin=str(tmp_path / "missing-nexus-agy-dispatch"),
        )


def test_validate_operation_evidence_rejects_missing_permission_and_scope():
    evidence = _valid_operation_evidence()
    evidence["permission_profile_sha256"] = None
    evidence["effective_permissions"] = None
    evidence["scope_validation_state"] = None
    errors = MOD.validate_operation_evidence(
        evidence,
        expected_operation_id="agyop_valid123",
    )
    assert "OPERATION_PERMISSION_PROFILE_MISSING" in errors
    assert "OPERATION_EFFECTIVE_PERMISSIONS_MISSING" in errors
    assert "OPERATION_SCOPE_NOT_VERIFIED" in errors


def test_prove_clean_core_repo_success(clean_core_identity):
    commit, tree = clean_core_identity
    assert len(commit) == 40
    assert len(tree) == 40
    c2, t2 = MOD.prove_clean_core_repo(CORE_ROOT, expected_commit=commit, expected_tree=tree)
    assert c2 == commit
    assert t2 == tree


def test_prove_clean_core_repo_missing_dir(tmp_path):
    with pytest.raises(MOD.CoreCompletionError) as exc:
        MOD.prove_clean_core_repo(tmp_path / "nonexistent")
    assert "CORE_ROOT_MISSING" in str(exc.value)


def test_prove_clean_core_repo_not_a_git_repo(tmp_path):
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    with pytest.raises(MOD.CoreCompletionError) as exc:
        MOD.prove_clean_core_repo(empty_dir)
    assert "CORE_NOT_A_GIT_REPOSITORY" in str(exc.value)


def test_prove_clean_core_repo_dirty(tmp_path):
    repo = tmp_path / "core_repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-b", "main", str(repo)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "Test"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "test@test"], check=True)
    (repo / "f.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-m", "init"], check=True)

    # Clean check passes
    c, t = MOD.prove_clean_core_repo(repo)
    assert len(c) == 40

    # Add untracked dirty file
    (repo / "dirty.txt").write_text("dirty\n")
    with pytest.raises(MOD.CoreCompletionError) as exc:
        MOD.prove_clean_core_repo(repo)
    assert "CORE_REPO_DIRTY" in str(exc.value)


def test_prove_clean_core_repo_commit_and_tree_mismatch(clean_core_identity):
    commit, tree = clean_core_identity
    with pytest.raises(MOD.CoreCompletionError) as exc:
        MOD.prove_clean_core_repo(CORE_ROOT, expected_commit="0" * 40)
    assert "CORE_COMMIT_MISMATCH" in str(exc.value)

    with pytest.raises(MOD.CoreCompletionError) as exc:
        MOD.prove_clean_core_repo(CORE_ROOT, expected_commit=commit, expected_tree="0" * 40)
    assert "CORE_TREE_MISMATCH" in str(exc.value)


def test_materialize_envelope_properties():
    envelope = _make_valid_envelope()
    assert envelope["schema"] == MOD.WORK_PRODUCT_ENVELOPE_SCHEMA
    assert envelope["envelope_hash"].startswith("sha256:")
    assert envelope["evidence_binding_identity"].startswith("sha256:")

    valid, errors = MOD.validate_work_product_envelope(envelope)
    assert valid is True
    assert errors == []


def test_validate_envelope_tampered_hash():
    envelope = _make_valid_envelope()
    envelope["envelope_hash"] = "sha256:" + "0" * 64
    valid, errors = MOD.validate_work_product_envelope(envelope)
    assert valid is False
    assert "ENVELOPE_HASH_MISMATCH" in errors


def test_validate_envelope_tampered_binding_identity():
    envelope = _make_valid_envelope()
    envelope["evidence_binding_identity"] = "sha256:" + "0" * 64
    envelope["envelope_hash"] = MOD.canonical_hash(envelope)
    valid, errors = MOD.validate_work_product_envelope(envelope)
    assert valid is False
    assert "BINDING_IDENTITY_MISMATCH" in errors


def test_validate_envelope_mismatched_context():
    envelope = _make_valid_envelope(
        issue_number=1419,
        run_id="run-1",
        operation_id="agyop_1",
        source_revision="rev-1",
        source_tree="git-tree:tree-1",
    )
    valid, errors = MOD.validate_work_product_envelope(
        envelope,
        expected_issue=999,
        expected_run_id="run-2",
        expected_operation_id="agyop_2",
        expected_source_revision="rev-2",
        expected_source_tree="tree-2",
    )
    assert valid is False
    assert "WRONG_ISSUE_NUMBER" in errors
    assert "WRONG_RUN_ID" in errors
    assert "WRONG_OPERATION_ID" in errors
    assert "WRONG_SOURCE_REVISION" in errors
    assert "WRONG_SOURCE_TREE" in errors


def test_evaluate_core_completion_positive(clean_core_identity):
    commit, tree = clean_core_identity
    envelope = _make_valid_envelope()
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=envelope,
        expected_issue=1419,
        expected_run_id="run-test-01",
        expected_operation_id="agyop_valid123",
        expected_source_tree="source123",
        expected_core_commit=commit,
        expected_core_tree=tree,
        operation_evidence=_valid_operation_evidence(),
    )
    assert result["claims_complete"] is True
    assert result["verification_applies"] is True
    assert result["claims_verified"] is True
    assert result["reason_codes"] == []
    assert result["core_commit"] == commit
    assert result["core_tree"] == tree
    assert result["analysis_hash"].startswith("sha256:")
    assert MOD.validate_core_completion_result(result) is True


def test_evaluate_core_completion_red_no_semantic_work_product(require_usable_core):
    # Terminal COMPLETED but empty artifacts => NOT COMPLETE
    envelope = _make_valid_envelope()
    envelope["artifacts"] = []
    envelope["envelope_hash"] = MOD.canonical_hash(envelope)
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=envelope,
    )
    assert result["claims_verified"] is False
    assert "NO_SEMANTIC_WORK_PRODUCT" in result["reason_codes"]


def test_evaluate_core_completion_negative_none_envelope(require_usable_core):
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=None,
    )
    assert result["claims_verified"] is False
    assert "EMPTY_WORK_PRODUCT_ENVELOPE" in result["reason_codes"]


def test_evaluate_core_completion_negative_stale_artifact_hash(require_usable_core):
    # Observed artifact hash differs from claimed content hash => REJECTED_STALE
    envelope = _make_valid_envelope(
        content_hash="sha256:1111111111111111111111111111111111111111111111111111111111111111",
        verifier_artifact_hash="sha256:2222222222222222222222222222222222222222222222222222222222222222",
    )
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=envelope,
    )
    assert result["claims_verified"] is False
    assert any("STALE:verifier" in code for code in result["reason_codes"])


def test_evaluate_core_completion_negative_verifier_fail(require_usable_core):
    envelope = _make_valid_envelope(verifier_status="FAIL")
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=envelope,
    )
    assert result["claims_verified"] is False
    assert result["verification_applies"] is False


def test_evaluate_core_completion_negative_irrelevant_verifier(require_usable_core):
    # Observation artifact id does not match any claimed artifact
    envelope = _make_valid_envelope(
        verifier_artifact_id="art-other-unrelated",
    )
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=envelope,
    )
    assert result["claims_verified"] is False
    assert any("IRRELEVANT:verifier" in code for code in result["reason_codes"])


def test_evaluate_core_completion_negative_wrong_issue(require_usable_core):
    envelope = _make_valid_envelope(issue_number=1392)
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=envelope,
        expected_issue=1419,
    )
    assert result["claims_verified"] is False
    assert "WRONG_ISSUE_NUMBER" in result["reason_codes"]


def test_evaluate_core_completion_negative_wrong_source_tree(require_usable_core):
    envelope = _make_valid_envelope(source_tree="git-tree:source123")
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=envelope,
        expected_source_tree="git-tree:other999",
    )
    assert result["claims_verified"] is False
    assert "WRONG_SOURCE_TREE" in result["reason_codes"]


def test_evaluate_core_completion_negative_core_commit_mismatch(require_usable_core):
    envelope = _make_valid_envelope()
    result = MOD.evaluate_core_completion(
        core_root=CORE_ROOT,
        envelope=envelope,
        expected_core_commit="0" * 40,
    )
    assert result["claims_verified"] is False
    assert "CORE_COMMIT_MISMATCH" in result["reason_codes"]


def test_cli_materialize_and_evaluate(tmp_path, require_usable_core):
    env_file = tmp_path / "envelope.json"
    artifacts = [
        {
            "artifact_id": "art-01",
            "content_hash": "sha256:" + "1" * 64,
            "path": "scripts/ops/nexus-hermes-core-completion",
        }
    ]
    obs = {
        "artifact_id": "art-01",
        "artifact_hash": "sha256:" + "1" * 64,
        "status": "PASS",
        "verifier_id": "pytest",
    }
    mat_proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "materialize",
            "--issue-number",
            "1419",
            "--run-id",
            "run-cli-test",
            "--operation-id",
            "agyop_cli123",
            "--source-revision",
            "4f4e52787621e31adb00cd4e9136362d72a144e7",
            "--source-tree",
            "tree-src",
            "--target-revision",
            "tree-tgt",
            "--artifacts",
            json.dumps(artifacts),
            "--verifier-observation",
            json.dumps(obs),
            "--output",
            str(env_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert mat_proc.returncode == 0
    assert env_file.is_file()

    operation_evidence_file = tmp_path / "operation-evidence.json"
    operation_evidence_file.write_text(
        json.dumps(_valid_operation_evidence(operation_id="agyop_cli123")),
        encoding="utf-8",
    )

    eval_proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "evaluate",
            "--core-root",
            str(CORE_ROOT),
            "--envelope",
            str(env_file),
            "--expected-issue",
            "1419",
            "--expected-run-id",
            "run-cli-test",
            "--expected-operation-id",
            "agyop_cli123",
            "--expected-source-tree",
            "tree-src",
            "--operation-evidence",
            str(operation_evidence_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert eval_proc.returncode == 0
    payload = json.loads(eval_proc.stdout)
    assert payload["claims_verified"] is True
    assert payload["analysis_hash"].startswith("sha256:")
