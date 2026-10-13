from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from nexus.services.external_intelligence_closure import parse_task_card_authority
from nexus.services.external_intelligence_core_binding import (
    CAPABILITY_DISCOVERY_INDEX_PATH,
    OPERATING_MODE_PATH,
    CoreAuthorityInputs,
    CoreBindingError,
    acceptance_contract_hash,
    binding_hash_for,
    build_acceptance_contract,
    build_capability_discovery_receipt,
    build_integration_authority,
    build_repository_mutation_binding,
    core_canonical_json,
    core_hash,
    derive_bound_envelope,
    envelope_canonical_json,
    envelope_sha256,
    parse_bound_execution_envelope_v2,
    validate_repository_mutation_binding,
    workspace_identity,
)

REPOSITORY = "James3014/Nexus-new"
ORIGIN = "git@github.com:James3014/Nexus-new.git"
CARD_REF = "tasks/eia-core-binding/00-card.md"
TARGET = "tests/test_core_bound.py"
CAPABILITY_ID = "chatgpt_web_semantic_transport"


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr or result.stdout
    return result.stdout.strip()


def bound_worker() -> dict[str, str]:
    return {
        "worker_id": "google/gemini-worker-a",
        "provider": "google_genai",
        "model": "google_genai/gemini-test",
        "role_ceiling": "bounded repair",
        "admission_evidence_ref": "admission-a",
        "admission_evidence_hash": "a" * 64,
        "selection_evidence_ref": "selection-a",
        "selection_evidence_hash": "b" * 64,
    }


def worker_sha(worker: dict[str, str]) -> str:
    return hashlib.sha256(envelope_canonical_json(worker).encode("utf-8")).hexdigest()


def card_text(
    *,
    lane: str | None = "DIRECT_DELEGATED",
    disposition: str | None = "EXTEND_EXISTING",
    capability_ids: str | None = CAPABILITY_ID,
) -> str:
    lines = [
        "# EIA Core binding card",
        "",
        "- task_id: `task-1`",
        "- status: `ACTIVE`",
        "- worker_may_approve: `false`",
        "- worker_may_integrate: `false`",
        "- worker_may_push: `false`",
        "- AUTO_CHAIN: `false`",
        "- allow_deletions: `false`",
    ]
    if lane is not None:
        lines.append(f"- execution_lane: `{lane}`")
    if disposition is not None:
        lines.append(f"- capability_disposition: `{disposition}`")
    if capability_ids is not None:
        lines.append(f"- capability_ids: `{capability_ids}`")
    lines += ["", "## Allowed files", "", f"- `{TARGET}`", ""]
    return "\n".join(lines)


def make_bound_repo(
    tmp_path: Path,
    *,
    card: str | None = None,
    with_index: bool = True,
    with_mode: bool = True,
    origin: str | None = ORIGIN,
) -> SimpleNamespace:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "nexus-test@example.invalid")
    _git(repo, "config", "user.name", "Nexus Test")
    if origin is not None:
        _git(repo, "remote", "add", "origin", origin)
    card_path = repo / CARD_REF
    card_path.parent.mkdir(parents=True)
    card_path.write_text(card if card is not None else card_text(), encoding="utf-8")
    if with_index:
        index = repo / CAPABILITY_DISCOVERY_INDEX_PATH
        index.parent.mkdir(parents=True)
        index.write_text(
            json.dumps({
                "schema": "nexus.capability_discovery_index.v1",
                "status": "NAVIGATION_ONLY_NOT_AUTHORITY",
                "capabilities": [{"id": CAPABILITY_ID}, {"id": "repository_intelligence"}],
            }),
            encoding="utf-8",
        )
    if with_mode:
        mode = repo / OPERATING_MODE_PATH
        mode.parent.mkdir(parents=True)
        mode.write_text("mode: test\n", encoding="utf-8")
    (repo / "README.md").write_text("seed\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    card_hash = hashlib.sha256(card_path.read_bytes()).hexdigest()
    return SimpleNamespace(repo=repo, base=base, card_hash=card_hash)


def semantic_envelope(base: str, card_hash: str, worker: dict[str, str]) -> dict[str, Any]:
    return {
        "schema": "external_execution_envelope.v2",
        "binding": {
            "repository": REPOSITORY,
            "item_type": "issue",
            "item_id": "42",
            "revision": "r1",
            "main_sha": base,
            "task_card_ref": CARD_REF,
            "task_card_hash": card_hash,
            "context_pack_sha256": "c" * 64,
        },
        "selected_worker": dict(worker),
        "objective": "Add one bounded regression test.",
        "definition_of_done": ["one deterministic test"],
        "evidence_refs": [
            f"task_card:{CARD_REF}@" + "a" * 16,
            f"source_absence:{TARGET}@" + "b" * 16,
        ],
        "diagnosis": {
            "status": "PROVEN",
            "hypothesis": "the regression test is absent",
            "next_probe": "inspect the absent target",
        },
        "scope_signal": {
            "production_edit_paths": [],
            "required_test_edit_paths": [TARGET],
            "conditional_migration_paths": [],
            "read_only_authorities": [CARD_REF],
            "verification_only_paths": [TARGET],
            "forbidden_paths": [],
            "max_files": 1,
            "scope_confidence": "HIGH",
            "scope_block_conditions": ["no extra files"],
        },
        "inspect_first": [f"task_card:{CARD_REF}@" + "a" * 16],
        "required_semantics": ["deterministic"],
        "implementation_direction": ["create one test"],
        "verification_focus": ["pytest"],
        "failure_guards": ["no other paths"],
        "stop_and_escalate": ["scope expands"],
    }


def write_semantic_envelope(path: Path, envelope: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(envelope, sort_keys=True, indent=2), encoding="utf-8")
    return envelope_sha256(envelope)


def authority_inputs(
    base: str,
    card_hash: str,
    worker: dict[str, str],
    *,
    lane: str = "DIRECT_DELEGATED",
    unit_verifiers: dict[str, Any] | None = None,
    whole_verifiers: Any = None,
) -> CoreAuthorityInputs:
    return CoreAuthorityInputs(
        repository=REPOSITORY,
        issue_number=42,
        revision="r1",
        intent="Add one bounded regression test",
        issue_contract_sha256="d" * 64,
        item_identity_hash="e" * 64,
        task_id="task-1",
        task_card_ref=CARD_REF,
        task_card_hash=card_hash,
        main_sha=base,
        execution_lane=lane,
        capability_disposition="EXTEND_EXISTING",
        capability_ids=(CAPABILITY_ID,),
        capability_justification="",
        unit_verifiers=unit_verifiers
        if unit_verifiers is not None
        else {"u1": (("unit-pytest", ("python", "-m", "pytest", TARGET), 120.0),)},
        whole_verifiers=whole_verifiers
        if whole_verifiers is not None
        else (("whole-pytest", ("python", "-m", "pytest"), 300.0),),
        worker_binding_sha256=worker_sha(worker),
    )


def bound_unit_mapping(
    tmp_path: Path, scenario: SimpleNamespace, *, authority: CoreAuthorityInputs | None = None
) -> dict[str, Any]:
    worker = bound_worker()
    envelope = semantic_envelope(scenario.base, scenario.card_hash, worker)
    envelope_path = tmp_path / "intelligence" / "envelopes" / "semantic.json"
    sha = write_semantic_envelope(envelope_path, envelope)
    inputs = authority or authority_inputs(scenario.base, scenario.card_hash, worker)
    return {
        "task_id": "task-1",
        "unit_id": "u1",
        "envelope_ref": str(envelope_path),
        "envelope_sha256": sha,
        "expected_base_sha": scenario.base,
        "mutation_paths": [TARGET],
        "provider": "google_genai",
        "model": "google_genai/gemini-test",
        "selected_worker": worker,
        "core_authority": inputs.to_mapping(),
    }


def mint_binding(
    workspace: Path,
    base: str,
    inputs: CoreAuthorityInputs,
    *,
    operation_id: str = "f" * 64,
    attempt_id: str = "attempt-1",
    created_at: datetime | None = None,
    valid_for_seconds: float = 600.0,
) -> dict[str, Any]:
    index = _git(workspace, "cat-file", "blob", f"{base}:{CAPABILITY_DISCOVERY_INDEX_PATH}")
    mode = _git(workspace, "cat-file", "blob", f"{base}:{OPERATING_MODE_PATH}")
    receipt = build_capability_discovery_receipt(
        repository=inputs.repository,
        main_sha=base,
        index_bytes=index.encode("utf-8"),
        intent=inputs.intent,
        disposition=inputs.capability_disposition,
        matched_capability_ids=inputs.capability_ids,
        evidence={
            "architecture": [f"git:{base}:{CAPABILITY_DISCOVERY_INDEX_PATH}"],
            "source": [f"git:{base}:{TARGET}"],
            "history": ["github://James3014/Nexus-new/issues/42@r1"],
            "runtime": ["admission-a@" + "a" * 64],
        },
    )
    authority = build_integration_authority(
        inputs, operating_mode_sha256=hashlib.sha256((mode + "\n").encode()).hexdigest()
    )
    contract, contract_hash = build_acceptance_contract(
        inputs, unit_id="u1", mutation_paths=[TARGET], allow_deletions=False
    )
    return build_repository_mutation_binding(
        operation_id=operation_id,
        attempt_id=attempt_id,
        repository=inputs.repository,
        origin=ORIGIN,
        source_revision=base,
        source_tree=_git(workspace, "rev-parse", f"{base}^{{tree}}"),
        workspace_path=workspace,
        integration_authority=authority,
        capability_receipt_hash=core_hash(receipt),
        index_revision=base,
        acceptance_contract=contract,
        contract_hash=contract_hash,
        created_at=created_at or datetime.now(timezone.utc),
        valid_for_seconds=valid_for_seconds,
    )


def _validate(binding: dict[str, Any], workspace: Path, base: str, **overrides: Any) -> None:
    kwargs: dict[str, Any] = {
        "operation_id": "f" * 64,
        "attempt_id": "attempt-1",
        "repository": REPOSITORY,
        "expected_base": base,
        "observed_origin": ORIGIN,
        "observed_base_tree": _git(workspace, "rev-parse", f"{base}^{{tree}}"),
        "workspace_path": workspace,
        "allowed_paths": [TARGET],
    }
    kwargs.update(overrides)
    validate_repository_mutation_binding(binding, **kwargs)


# ---------------------------------------------------------------------------
# Golden vector pinned to nexus-open-swe-runtime tests/test_runtime.py::_v2_request
# ---------------------------------------------------------------------------

GOLDEN_ACCEPTANCE_CONTRACT_HASH = (
    "sha256:134803963fbd46d3cd0c0ecce937535ffffc74da769c797faa20adb23d36619f"
)
GOLDEN_BINDING_HASH = "sha256:58e39345d808f92e82478ad67d4ad471251a89f54a607e113f799bbbffca0671"
GOLDEN_NON_ASCII_CONTRACT_HASH = (
    "sha256:b4ef29a5a98c0881ba3ce8f2df79487f9a5a801a84f2292447b5b2bb9e73194a"
)


def _golden_contract() -> dict[str, Any]:
    return {
        "contract_id": "open-swe-test-contract",
        "requirements_hash": "sha256:" + "1" * 64,
        "required_verifier_ids": ["pytest"],
        "allowed_paths": ["a.py"],
        "deletion_policy": "FORBID",
    }


def _golden_binding() -> dict[str, Any]:
    contract = _golden_contract()
    return {
        "schema": "nexus.repository_mutation_binding.v1",
        "binding_id": "binding-test-1",
        "operation_id": "a" * 64,
        "attempt_id": "attempt-test-1",
        "repository": {
            "canonical_id": "James3014/Nexus-new",
            "origin": "git@github.com:James3014/Nexus-new.git",
            "source_revision": "git-commit:" + "b" * 40,
            "source_tree": "git-tree:" + "e" * 40,
            "workspace_identity": "sha256:" + hashlib.sha256(b"/workspace/golden").hexdigest(),
            "workspace_mode": "managed_worktree",
        },
        "integration_authority": {
            "execution_lane": "DIRECT_DELEGATED",
            "authority_ref": "owner-direct:test",
            "authority_hash": "sha256:" + "2" * 64,
        },
        "capability_discovery": {
            "required": True,
            "receipt_hash": "sha256:" + "3" * 64,
            "index_revision": "git-commit:" + "f" * 40,
        },
        "core": {
            "protocol_version": "0.1.0-experimental",
            "acceptance_contract": contract,
            "acceptance_contract_hash": acceptance_contract_hash(contract),
        },
        "freshness": {
            "created_at": "2026-09-15T00:00:00Z",
            "valid_until": None,
            "revalidate_before_first_effect": True,
        },
    }


def test_golden_vector_matches_runtime_fixture_hashes_byte_for_byte():
    binding = _golden_binding()
    assert binding["core"]["acceptance_contract_hash"] == GOLDEN_ACCEPTANCE_CONTRACT_HASH
    assert core_hash(binding) == GOLDEN_BINDING_HASH
    binding["binding_hash"] = core_hash(binding)
    assert binding_hash_for(binding) == GOLDEN_BINDING_HASH


def test_core_canonicalization_is_ascii_escaped_and_diverges_from_envelope_rule():
    contract = {**_golden_contract(), "contract_id": "eia/契約"}
    assert acceptance_contract_hash(contract) == GOLDEN_NON_ASCII_CONTRACT_HASH
    core_text = core_canonical_json(contract)
    envelope_text = envelope_canonical_json(contract)
    assert "\\u5951" in core_text and "契約" not in core_text
    assert "契約" in envelope_text
    assert core_text != envelope_text
    wrong = "sha256:" + hashlib.sha256(envelope_text.encode("utf-8")).hexdigest()
    assert wrong != core_hash(contract)
    with pytest.raises(ValueError):
        core_canonical_json({"value": float("nan")})


# ---------------------------------------------------------------------------
# Builders and fail-closed cases
# ---------------------------------------------------------------------------


def test_minted_binding_validates_and_pins_owner_authority(tmp_path):
    scenario = make_bound_repo(tmp_path)
    inputs = authority_inputs(scenario.base, scenario.card_hash, bound_worker())
    binding = mint_binding(scenario.repo, scenario.base, inputs)
    _validate(binding, scenario.repo, scenario.base)
    assert binding["integration_authority"]["execution_lane"] == "DIRECT_DELEGATED"
    assert binding["integration_authority"]["authority_ref"] == (
        f"github://{REPOSITORY}/issues/42@r1#task_card:{CARD_REF}@{scenario.card_hash[:16]}"
    )
    assert binding["binding_id"].startswith("eiab_") and len(binding["binding_id"]) == 37
    assert binding["repository"]["workspace_identity"] == workspace_identity(scenario.repo)
    contract = binding["core"]["acceptance_contract"]
    assert contract["contract_id"] == f"eia/{REPOSITORY}/issues/42/r1/task-1/u1"
    assert contract["required_verifier_ids"] == ["unit-pytest", "whole-pytest"]
    assert contract["allowed_paths"] == [TARGET]
    assert contract["deletion_policy"] == "FORBID"
    assert binding["freshness"]["revalidate_before_first_effect"] is True
    assert binding["capability_discovery"]["index_revision"] == f"git-commit:{scenario.base}"


@pytest.mark.parametrize(
    ("lane", "reason"),
    [("", "CORE_EXECUTION_LANE_REQUIRED"), ("RDC", "CORE_EXECUTION_LANE_INVALID")],
)
def test_missing_or_invalid_execution_lane_fails_closed(tmp_path, lane, reason):
    inputs = authority_inputs("1" * 40, "2" * 64, bound_worker(), lane=lane)
    with pytest.raises(CoreBindingError, match=reason):
        build_integration_authority(inputs, operating_mode_sha256="3" * 64)


def test_allow_deletions_fails_closed_before_contract():
    inputs = authority_inputs("1" * 40, "2" * 64, bound_worker())
    with pytest.raises(CoreBindingError, match="CORE_DELETION_POLICY_FORBID_REQUIRED"):
        build_acceptance_contract(
            inputs, unit_id="u1", mutation_paths=[TARGET], allow_deletions=True
        )


def test_duplicate_verifier_ids_fail_closed():
    inputs = authority_inputs(
        "1" * 40,
        "2" * 64,
        bound_worker(),
        whole_verifiers=(("unit-pytest", ("python", "-m", "pytest"), 120.0),),
    )
    with pytest.raises(CoreBindingError, match="CORE_VERIFIER_IDS_DUPLICATE"):
        build_acceptance_contract(
            inputs, unit_id="u1", mutation_paths=[TARGET], allow_deletions=False
        )


def test_contract_paths_must_equal_unit_paths(tmp_path):
    scenario = make_bound_repo(tmp_path)
    inputs = authority_inputs(scenario.base, scenario.card_hash, bound_worker())
    binding = mint_binding(scenario.repo, scenario.base, inputs)
    with pytest.raises(CoreBindingError, match="core_binding_scope"):
        _validate(binding, scenario.repo, scenario.base, allowed_paths=[TARGET, "other.py"])


def test_capability_index_missing_at_main_sha_fails_closed():
    with pytest.raises(CoreBindingError, match="CAPABILITY_DISCOVERY_INDEX_MISSING"):
        build_capability_discovery_receipt(
            repository=REPOSITORY,
            main_sha="1" * 40,
            index_bytes=None,
            intent="x",
            disposition="REUSE_EXISTING",
            matched_capability_ids=[CAPABILITY_ID],
            evidence={"architecture": ["a"], "source": ["s"], "history": ["h"], "runtime": ["r"]},
        )


@pytest.mark.parametrize(
    ("disposition", "ids", "justification", "reason"),
    [
        ("", [CAPABILITY_ID], "", "CAPABILITY_DISPOSITION_REQUIRED"),
        ("BLOCKED_UNKNOWN", [], "", "CAPABILITY_DISPOSITION_BLOCKS_MUTATION"),
        ("REUSE_EXISTING", None, "", "CAPABILITY_IDS_REQUIRED"),
        ("REUSE_EXISTING", [], "", "CAPABILITY_IDS_REQUIRED"),
        ("REUSE_EXISTING", ["invented_capability"], "", "CAPABILITY_IDS_NOT_IN_INDEX"),
        ("NEW_CAPABILITY_JUSTIFIED", [CAPABILITY_ID], "why", "CAPABILITY_NEW_MUST_NOT_CLAIM"),
        ("NEW_CAPABILITY_JUSTIFIED", [], "", "CAPABILITY_JUSTIFICATION_REQUIRED"),
    ],
)
def test_capability_discovery_owner_fields_fail_closed(disposition, ids, justification, reason):
    index = json.dumps({
        "schema": "nexus.capability_discovery_index.v1",
        "capabilities": [{"id": CAPABILITY_ID}],
    }).encode()
    with pytest.raises(CoreBindingError, match=reason):
        build_capability_discovery_receipt(
            repository=REPOSITORY,
            main_sha="1" * 40,
            index_bytes=index,
            intent="x",
            disposition=disposition,
            matched_capability_ids=ids,
            justification=justification,
            evidence={"architecture": ["a"], "source": ["s"], "history": ["h"], "runtime": ["r"]},
        )


def test_capability_receipt_matches_devspace_receipt_shape():
    index = json.dumps({
        "schema": "nexus.capability_discovery_index.v1",
        "capabilities": [{"id": CAPABILITY_ID}],
    }).encode()
    receipt = build_capability_discovery_receipt(
        repository=REPOSITORY,
        main_sha="1" * 40,
        index_bytes=index,
        intent="bounded test",
        disposition="NEW_CAPABILITY_JUSTIFIED",
        matched_capability_ids=[],
        justification="no donor covers this",
        evidence={"architecture": ["a"], "source": ["s"], "history": ["h"], "runtime": ["r"]},
    )
    assert receipt["indexSha256"] == hashlib.sha256(index).hexdigest()
    assert receipt["indexRevision"] == "1" * 40
    assert receipt["indexPath"] == CAPABILITY_DISCOVERY_INDEX_PATH
    assert receipt["newCapabilityJustification"] == "no donor covers this"
    assert set(receipt["evidence"]) == {"architecture", "source", "history", "runtime"}


def test_expired_valid_until_fails_closed(tmp_path):
    scenario = make_bound_repo(tmp_path)
    inputs = authority_inputs(scenario.base, scenario.card_hash, bound_worker())
    created = datetime.now(timezone.utc) - timedelta(hours=2)
    binding = mint_binding(
        scenario.repo, scenario.base, inputs, created_at=created, valid_for_seconds=60
    )
    with pytest.raises(CoreBindingError, match="core_binding_freshness"):
        _validate(binding, scenario.repo, scenario.base)


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"operation_id": "0" * 64}, "core_binding_operation"),
        ({"attempt_id": "attempt-2"}, "core_binding_operation"),
        ({"observed_origin": "git@github.com:other/repo.git"}, "core_binding_repository"),
        ({"observed_base_tree": "0" * 40}, "core_binding_source"),
        ({"expected_base": "0" * 40}, "core_binding_source"),
    ],
)
def test_revalidation_mirrors_runtime_reason_codes(tmp_path, override, reason):
    scenario = make_bound_repo(tmp_path)
    inputs = authority_inputs(scenario.base, scenario.card_hash, bound_worker())
    binding = mint_binding(scenario.repo, scenario.base, inputs)
    with pytest.raises(CoreBindingError, match=reason):
        _validate(binding, scenario.repo, scenario.base, **override)


def test_revalidation_detects_workspace_identity_and_binding_tamper(tmp_path):
    scenario = make_bound_repo(tmp_path)
    inputs = authority_inputs(scenario.base, scenario.card_hash, bound_worker())
    binding = mint_binding(scenario.repo, scenario.base, inputs)
    with pytest.raises(CoreBindingError, match="core_binding_workspace"):
        _validate(binding, scenario.repo, scenario.base, workspace_path=tmp_path)
    tampered = json.loads(json.dumps(binding))
    tampered["integration_authority"]["execution_lane"] = "DIRECT_CANONICAL"
    with pytest.raises(CoreBindingError, match="core_binding_hash"):
        _validate(tampered, scenario.repo, scenario.base)


def test_bound_envelope_derivation_keeps_semantic_envelope_immutable(tmp_path):
    scenario = make_bound_repo(tmp_path)
    worker = bound_worker()
    semantic = semantic_envelope(scenario.base, scenario.card_hash, worker)
    semantic_sha = envelope_sha256(semantic)
    before = envelope_canonical_json(semantic)
    binding = mint_binding(
        scenario.repo, scenario.base, authority_inputs(scenario.base, scenario.card_hash, worker)
    )
    bound = derive_bound_envelope(semantic, binding)
    assert envelope_canonical_json(semantic) == before
    assert "repository_mutation_binding" not in semantic
    parsed_semantic, parsed_binding, bound_sha = parse_bound_execution_envelope_v2(
        json.dumps(bound, indent=2), semantic_envelope_sha256=semantic_sha
    )
    assert parsed_semantic == semantic
    assert parsed_binding == binding
    assert bound_sha == envelope_sha256(bound) != semantic_sha
    with pytest.raises(CoreBindingError, match="ALREADY_BOUND"):
        derive_bound_envelope(bound, binding)
    with pytest.raises(CoreBindingError, match="SEMANTIC_MISMATCH"):
        parse_bound_execution_envelope_v2(
            json.dumps({**bound, "objective": "widened"}), semantic_envelope_sha256=semantic_sha
        )
    tampered = json.loads(json.dumps(bound))
    tampered["repository_mutation_binding"]["attempt_id"] = "other"
    with pytest.raises(CoreBindingError, match="core_binding_hash"):
        parse_bound_execution_envelope_v2(
            json.dumps(tampered), semantic_envelope_sha256=semantic_sha
        )
    with pytest.raises(CoreBindingError, match="BINDING_MISSING"):
        parse_bound_execution_envelope_v2(
            json.dumps(semantic), semantic_envelope_sha256=semantic_sha
        )


def test_task_card_core_fields_parse_and_absent_fields_keep_defaults():
    authority = parse_task_card_authority(
        card_text(capability_ids=f"{CAPABILITY_ID},repository_intelligence")
    )
    assert authority.execution_lane == "DIRECT_DELEGATED"
    assert authority.capability_disposition == "EXTEND_EXISTING"
    assert authority.capability_ids == (CAPABILITY_ID, "repository_intelligence")
    assert parse_task_card_authority(card_text(capability_ids="none")).capability_ids == ()
    legacy = parse_task_card_authority(card_text(lane=None, disposition=None, capability_ids=None))
    assert legacy.execution_lane == ""
    assert legacy.capability_disposition == ""
    assert legacy.capability_ids is None
    assert legacy.is_executable and legacy.allowed_files == (TARGET,)


def test_core_authority_inputs_round_trip_and_reject_malformed():
    inputs = authority_inputs("1" * 40, "2" * 64, bound_worker())
    assert CoreAuthorityInputs.from_mapping(inputs.to_mapping()) == inputs
    with pytest.raises(CoreBindingError, match="CORE_AUTHORITY_REQUIRED"):
        CoreAuthorityInputs.from_mapping(None)
    with pytest.raises(CoreBindingError, match="CORE_AUTHORITY_MAIN_SHA_INVALID"):
        CoreAuthorityInputs.from_mapping({**inputs.to_mapping(), "main_sha": "nothex"})
