"""Evidence coverage/reuse v1: producer declaration + transport (task_0002)."""
from __future__ import annotations
import copy, json, sys
from pathlib import Path
import pytest
from nexus.orchestrator.task_contract import SelfHostedTaskContract
EXACT_CONTROLLER_SHA = "a" * 40
EXACT_TARGET_SHA = "b" * 40
def _base_contract_kwargs(tmp_path, **overrides):
    values = {
        "task_id": "evcov-contract",
        "objective": "Capture a bounded candidate diff",
        "controller_revision": EXACT_CONTROLLER_SHA,
        "target_base_revision": EXACT_TARGET_SHA,
        "controller_repo_root": str(tmp_path / "controller"),
        "target_repo_root": str(tmp_path / "targets" / "evcov-contract"),
        "target_worktree_root": str(tmp_path / "targets"),
        "allowed_files": ["nexus/orchestrator/task_contract.py"],
        "forbidden_files": ["secrets/"],
        "verifier_commands": ["python3 -m pytest -q"],
        "protected_contracts": ["receipt-v1"],
    }
    values.update(overrides)
    return values
def _universe_dict(**overrides):
    values = {
        "universe_generation": 3,
        "subjects": [
            {"logical_subject_id": "pytest:unit", "evidence_kind": "test-report",
             "requirement_mode": "REQUIRED", "applicability": "APPLICABLE"},
            {"logical_subject_id": "lint:ruff", "evidence_kind": "lint-report",
             "requirement_mode": "CONDITIONALLY_REQUIRED", "applicability": "UNRESOLVED"},
        ],
    }
    values.update(overrides)
    return values
# --- legacy + new parse ---
def test_legacy_contract_parses_and_verifies_as_before(tmp_path):
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path))
    assert contract.expected_evidence is None
    assert contract.universe_identity is None
    dumped = contract.model_dump(mode="json")
    import hashlib
    payload = {k: v for k, v in dumped.items() if k not in ("contract_hash", "expected_evidence")}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert contract.contract_hash == hashlib.sha256(canonical).hexdigest()

def test_new_contract_parses_and_binds_universe(tmp_path):
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=_universe_dict()))
    assert contract.expected_evidence is not None
    assert contract.expected_evidence.universe_generation == 3
    assert [s.logical_subject_id for s in contract.expected_evidence.subjects] == ["lint:ruff", "pytest:unit"]
    assert contract.universe_identity is not None
    assert contract.universe_identity.startswith("sha256:")
    legacy = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path))
    assert contract.contract_hash != legacy.contract_hash
# --- invalid declarations ---
@pytest.mark.parametrize("mutate,match", [
    (lambda u: u["subjects"].__setitem__(0, {**u["subjects"][0], "logical_subject_id": "  "}), "nonblank"),
    (lambda u: u["subjects"].append(dict(u["subjects"][0])), "duplicate"),
    (lambda u: u["subjects"].__setitem__(0, {**u["subjects"][0], "requirement_mode": "BOGUS"}), "requirement_mode"),
    (lambda u: u["subjects"].__setitem__(0, {**u["subjects"][0], "requirement_mode": "REQUIRED", "applicability": "NOT_APPLICABLE"}), "REQUIRED"),
    (lambda u: u["subjects"].__setitem__(0, {**u["subjects"][0], "requirement_mode": "NOT_APPLICABLE", "applicability": "APPLICABLE"}), "NOT_APPLICABLE"),
    (lambda u: u.__setitem__("universe_generation", -1), "universe_generation"),
    (lambda u: u.__setitem__("universe_generation", "3"), "universe_generation"),
    (lambda u: u.__setitem__("subjects", []), "subjects"),
])
def test_invalid_declarations_rejected(tmp_path, mutate, match):
    universe = _universe_dict()
    mutate(universe)
    with pytest.raises(Exception, match=match):
        SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=universe))

def test_oversized_declarations_rejected(tmp_path):
    too_long = "x" * 513
    universe = _universe_dict(subjects=[{"logical_subject_id": too_long, "evidence_kind": "k", "requirement_mode": "REQUIRED", "applicability": "APPLICABLE"}])
    with pytest.raises(Exception, match="512"):
        SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=universe))
    many = [{"logical_subject_id": f"ns:sub-{i}", "evidence_kind": "k", "requirement_mode": "CONDITIONALLY_REQUIRED", "applicability": "UNRESOLVED"} for i in range(257)]
    with pytest.raises(Exception):
        SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=_universe_dict(subjects=many)))

def test_conditionally_required_allows_all_applicability(tmp_path):
    for applicability in ("APPLICABLE", "NOT_APPLICABLE", "UNRESOLVED"):
        c = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=_universe_dict(subjects=[{"logical_subject_id": "ns:sub", "evidence_kind": "k", "requirement_mode": "CONDITIONALLY_REQUIRED", "applicability": applicability}])))
        assert c.expected_evidence.subjects[0].applicability.value == applicability

def test_verifier_id_exact_equivalence_coupling(tmp_path):
    cmd = "python3 -m pytest -q"
    good = _universe_dict(subjects=[{"logical_subject_id": cmd, "evidence_kind": "test-report", "requirement_mode": "REQUIRED", "applicability": "APPLICABLE"}])
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=good))
    assert contract.expected_evidence is not None
    bad = _universe_dict(subjects=[{"logical_subject_id": cmd, "evidence_kind": "test-report", "requirement_mode": "CONDITIONALLY_REQUIRED", "applicability": "UNRESOLVED"}])
    with pytest.raises(Exception, match="must be REQUIRED/APPLICABLE"):
        SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=bad))
    assert set(contract.verifier_commands) == {cmd}

def test_namespaced_ids_impose_no_coupling(tmp_path):
    universe = _universe_dict(subjects=[{"logical_subject_id": "custom:arena-1", "evidence_kind": "k", "requirement_mode": "CONDITIONALLY_REQUIRED", "applicability": "UNRESOLVED"}])
    c = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=universe))
    assert c.expected_evidence is not None
# --- canonical hash behavior ---
def test_canonical_hash_mutation_sensitive_and_order_insensitive(tmp_path):
    u1 = _universe_dict()
    u2 = _universe_dict(subjects=list(reversed(_universe_dict()["subjects"])))
    c1 = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=u1))
    c2 = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=u2))
    assert c1.contract_hash == c2.contract_hash
    assert c1.universe_identity == c2.universe_identity
    c3 = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=_universe_dict(universe_generation=4)))
    assert c3.contract_hash != c1.contract_hash
    mutated_kind = _universe_dict(subjects=[{**_universe_dict()["subjects"][0], "evidence_kind": "other-kind"}, _universe_dict()["subjects"][1]])
    c4 = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=mutated_kind))
    assert c4.contract_hash != c1.contract_hash

def test_persisted_readback_preserves_normalized_declaration(tmp_path):
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=_universe_dict()))
    dumped = contract.model_dump(mode="json")
    dumped.pop("contract_hash", None)
    reloaded = SelfHostedTaskContract.model_validate(json.loads(json.dumps(dumped)))
    assert reloaded.model_dump(mode="json")["expected_evidence"] == dumped["expected_evidence"]
    assert reloaded.contract_hash == contract.contract_hash
    assert reloaded.universe_identity == contract.universe_identity
# --- transport projection ---
def _import_transport():
    from nexus.orchestrator.canonical_core_transport import project_expected_evidence_universe
    return project_expected_evidence_universe

def test_transport_projection_preserves_universe_verbatim(tmp_path):
    project = _import_transport()
    universe = _universe_dict(subjects=list(reversed(_universe_dict()["subjects"])))
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=universe))
    projected = project(contract)
    assert projected is not None
    assert projected["universe_generation"] == 3
    assert [s["logical_subject_id"] for s in projected["expected_subjects"]] == ["lint:ruff", "pytest:unit"]
    assert projected["expected_subjects"] == [
        {"logical_subject_id": "lint:ruff", "evidence_kind": "lint-report", "requirement_mode": "CONDITIONALLY_REQUIRED", "applicability": "UNRESOLVED"},
        {"logical_subject_id": "pytest:unit", "evidence_kind": "test-report", "requirement_mode": "REQUIRED", "applicability": "APPLICABLE"},
    ]

def test_transport_projection_legacy_absent(tmp_path):
    project = _import_transport()
    assert project(SelfHostedTaskContract(**_base_contract_kwargs(tmp_path))) is None

def test_transport_output_mutation_does_not_mutate_contract(tmp_path):
    project = _import_transport()
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=_universe_dict()))
    before = copy.deepcopy(contract.model_dump(mode="json")["expected_evidence"])
    projected = project(contract)
    projected["expected_subjects"].append({"logical_subject_id": "evil", "evidence_kind": "x", "requirement_mode": "REQUIRED", "applicability": "APPLICABLE"})
    projected["expected_subjects"][0]["evidence_kind"] = "MUTATED"
    assert contract.model_dump(mode="json")["expected_evidence"] == before

def test_transport_does_not_author_universe():
    project = _import_transport()
    assert project({}) is None
    assert project({"task_id": "x"}) is None
# --- Core provenance fail-closed ---
def test_wrong_core_revision_marked_fail_closed():
    from nexus.orchestrator.canonical_core_transport import core_provenance_status
    status = core_provenance_status({"available": True, "source_root": "/tmp/fake-core", "expected_revision": "f" * 40, "observed_commit": "a" * 40, "observed_tree": "b" * 40})
    assert status["fail_closed"] is True
    assert status["status"] == "CORE_REVISION_MISMATCH"
    assert status["observed_commit"] == "a" * 40
    assert status["expected_revision"] != status["observed_commit"]

def test_missing_observed_core_identity_marked_unavailable():
    from nexus.orchestrator.canonical_core_transport import core_provenance_status, read_observed_core_identity
    status = core_provenance_status({"available": False, "reason": "CORE_IDENTITY_UNREADABLE", "expected_revision": "f" * 40, "observed_commit": None, "observed_tree": None})
    assert status["status"] == "CORE_IDENTITY_UNAVAILABLE"
    assert status["fail_closed"] is True
    assert status["observed_commit"] is None
    missing = read_observed_core_identity(core_root=Path("/nonexistent-core-root-xyz"))
    assert missing["available"] is False
    assert missing["observed_commit"] is None
# --- verify_candidate projection ---
def _fake_200(transport, captured):
    def fake_verify(request):
        captured.update(request)
        return (200, {"protocol_version": request["protocol_version"], "schema": transport.GENERIC_VERIFICATION_RESPONSE_SCHEMA_ID,
            "verification": {"status": "VERIFIED", "reason_codes": [], "integrity": "VALID"},
            "hashes": {"acceptance_contract_hash": transport.acceptance_contract_hash(request["acceptance_contract"]),
                "change_set_hash": transport.change_set_hash(request["change_set"]),
                "verification_plan_hash": transport.verification_plan_hash(request["verification_plan"]),
                "evidence_bundle_hash": transport.evidence_bundle_hash(request["evidence_bundle"]),
                "change_manifest_hash": transport.change_manifest_hash(request["change_manifest"])},
            "certification": None})
    return fake_verify

def _manifest():
    return {"source_tree": "git-tree:" + "a" * 40, "target_tree": "git-tree:" + "b" * 40,
        "entries": [{"path": "nexus/orchestrator/task_contract.py", "change_type": "MODIFY", "before_oid": "a" * 40, "after_oid": "b" * 40, "before_mode": "100644", "after_mode": "100644"}]}

def _prep():
    return {"session_id": "cms_" + "0" * 32, "binding_hash": "sha256:" + "0" * 64, "attempt_id": "attempt-evcov-1"}

def _req(tmp_path, cid):
    return {"contract_id": cid, "allowed_files": ["nexus/orchestrator/task_contract.py"], "verifier_commands": ["python3 -m pytest -q"], "deletion_policy": "FORBID", "controller_repo_root": str(tmp_path)}

def test_verify_candidate_projection_carries_provenance_and_universe(tmp_path, monkeypatch):
    import nexus.orchestrator.canonical_core_transport as transport
    import hashlib as _hl
    def _sh(b):
        import hashlib as _h2
        return "sha256:" + _h2.sha256(b).hexdigest()
    monkeypatch.setattr(transport, "CORE_AVAILABLE", True, raising=False)
    monkeypatch.setattr(transport, "acceptance_contract_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    monkeypatch.setattr(transport, "change_set_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    monkeypatch.setattr(transport, "verification_plan_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    monkeypatch.setattr(transport, "evidence_bundle_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    monkeypatch.setattr(transport, "change_manifest_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    captured = {}
    monkeypatch.setattr(transport, "verify_generic_changeset", _fake_200(transport, captured), raising=False)
    monkeypatch.setattr(transport, "read_observed_core_identity", lambda: {"available": True, "source_root": "/tmp/fake-core", "expected_revision": transport.CANONICAL_CORE_REVISION, "observed_commit": "c" * 40, "observed_tree": "d" * 40, "revision_match": False}, raising=False)
    port = transport.CanonicalNexusCoreTransportPort(db_path=str(tmp_path / "prov.sqlite"))
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=_universe_dict()))
    projection = port.verify_candidate(preparation=_prep(), contract=contract, request=_req(tmp_path, "evcov-contract"), candidate={"candidate_state_hash": "sha256:" + "1" * 64}, change_manifest=_manifest())
    assert captured["acceptance_contract"]["expected_subjects"][0]["logical_subject_id"] == "lint:ruff"
    assert captured["acceptance_contract"]["universe_generation"] == 3
    assert projection["expected_evidence_projection"]["universe_generation"] == 3
    assert projection["core_source_identity"]["observed_commit"] == "c" * 40
    assert projection["core_provenance"]["status"] == "CORE_REVISION_MISMATCH"
    assert projection["core_provenance"]["fail_closed"] is True

def test_verify_candidate_legacy_request_has_no_universe(tmp_path, monkeypatch):
    import nexus.orchestrator.canonical_core_transport as transport
    import hashlib as _hl
    def _sh(b):
        import hashlib as _h2
        return "sha256:" + _h2.sha256(b).hexdigest()
    monkeypatch.setattr(transport, "CORE_AVAILABLE", True, raising=False)
    monkeypatch.setattr(transport, "acceptance_contract_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    monkeypatch.setattr(transport, "change_set_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    monkeypatch.setattr(transport, "verification_plan_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    monkeypatch.setattr(transport, "evidence_bundle_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    monkeypatch.setattr(transport, "change_manifest_hash", lambda v: _sh(json.dumps(v, sort_keys=True).encode()), raising=False)
    captured = {}
    monkeypatch.setattr(transport, "verify_generic_changeset", _fake_200(transport, captured), raising=False)
    monkeypatch.setattr(transport, "read_observed_core_identity", lambda: {"available": False, "reason": "CORE_IDENTITY_UNREADABLE", "expected_revision": transport.CANONICAL_CORE_REVISION, "observed_commit": None, "observed_tree": None}, raising=False)
    port = transport.CanonicalNexusCoreTransportPort(db_path=str(tmp_path / "legacy.sqlite"))
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path))
    projection = port.verify_candidate(preparation=_prep(), contract=contract, request=_req(tmp_path, "evcov-legacy"), candidate={"candidate_state_hash": "sha256:" + "2" * 64}, change_manifest=_manifest())
    assert "expected_subjects" not in captured["acceptance_contract"]
    assert "universe_generation" not in captured["acceptance_contract"]
    assert projection["expected_evidence_projection"] is None
    assert projection["core_provenance"]["status"] == "CORE_IDENTITY_UNAVAILABLE"
    assert projection["core_provenance"]["fail_closed"] is True
# --- old/new interop order determination ---
def _stub_old_consumer_rejects_unknown_keys(payload):
    allowed = {"contract_id", "requirements_hash", "required_verifier_ids", "allowed_paths", "deletion_policy"}
    return "REJECTED" if (set(payload) - allowed) else "ACCEPTED"

def test_new_producer_old_consumer_requires_core_first(tmp_path):
    project = _import_transport()
    contract = SelfHostedTaskContract(**_base_contract_kwargs(tmp_path, expected_evidence=_universe_dict()))
    projected = project(contract)
    assert projected is not None
    wire_contract = {"contract_id": "c", "requirements_hash": "sha256:" + "f" * 64, "required_verifier_ids": ["python3 -m pytest -q"], "allowed_paths": ["nexus/orchestrator/task_contract.py"], "deletion_policy": "FORBID", "expected_subjects": projected["expected_subjects"], "universe_generation": projected["universe_generation"]}
    assert _stub_old_consumer_rejects_unknown_keys(wire_contract) == "REJECTED"
    legacy_wire = {k: v for k, v in wire_contract.items() if k in ("contract_id", "requirements_hash", "required_verifier_ids", "allowed_paths", "deletion_policy")}
    assert _stub_old_consumer_rejects_unknown_keys(legacy_wire) == "ACCEPTED"

def test_new_producer_old_consumer_physical_core_rejects_universe():
    import subprocess
    code = (
        "from product.adapters.generic_verification import _validate_contract;"
        "import json;"
        "uni={\"contract_id\":\"c\",\"requirements_hash\":\"sha256:\"+\"f\"*64,\"required_verifier_ids\":[\"v\"],\"allowed_paths\":[\"a.py\"],\"deletion_policy\":\"FORBID\","
        "\"expected_subjects\":[{\"logical_subject_id\":\"s\",\"evidence_kind\":\"k\",\"requirement_mode\":\"REQUIRED\",\"applicability\":\"APPLICABLE\"}],\"universe_generation\":1};"
        "leg={\"contract_id\":\"c\",\"requirements_hash\":\"sha256:\"+\"f\"*64,\"required_verifier_ids\":[\"v\"],\"allowed_paths\":[\"a.py\"],\"deletion_policy\":\"FORBID\"};"
        "print(json.dumps([_validate_contract(uni), _validate_contract(leg)]))"
    )
    out = subprocess.check_output(["/Users/james/workspace/Nexus-new/.venv/bin/python", "-c", code], cwd="/Users/james/workspace/nexus-core", text=True)
    assert json.loads(out) == ["acceptance_contract", None]

def test_old_producer_new_consumer_accepts_legacy():
    import subprocess
    code = (
        "from product.adapters.generic_verification import _validate_contract;"
        "import json;"
        "leg={\"contract_id\":\"c\",\"requirements_hash\":\"sha256:\"+\"f\"*64,\"required_verifier_ids\":[\"v\"],\"allowed_paths\":[\"a.py\"],\"deletion_policy\":\"FORBID\"};"
        "uni={\"contract_id\":\"c\",\"requirements_hash\":\"sha256:\"+\"f\"*64,\"required_verifier_ids\":[\"v\"],\"allowed_paths\":[\"a.py\"],\"deletion_policy\":\"FORBID\","
        "\"expected_subjects\":[{\"logical_subject_id\":\"s\",\"evidence_kind\":\"k\",\"requirement_mode\":\"REQUIRED\",\"applicability\":\"APPLICABLE\"}],\"universe_generation\":1};"
        "print(json.dumps([_validate_contract(leg), _validate_contract(uni)]))"
    )
    out = subprocess.check_output(["/Users/james/workspace/Nexus-new/.venv/bin/python", "-c", code], cwd="/Users/james/workspace/nexus-core-evidence-reuse", text=True)
    assert json.loads(out) == [None, None]
