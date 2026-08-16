from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from nexus.services.external_intelligence import ExternalIntelligenceStore
from nexus.services.external_intelligence_automation import (
    ISSUE_SCHEMA,
    AutomationError,
    AutomationStateStore,
    ExternalIntelligenceAutomation,
    IssueWorkItem,
    compact_publication_payload,
    parse_issue_contract,
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contract(task_card_ref: str, task_card_hash: str, **overrides):
    value = {
        "schema": ISSUE_SCHEMA,
        "task_id": "task-1",
        "revision": "r1",
        "main_sha": "a" * 40,
        "task_card_ref": task_card_ref,
        "task_card_hash": task_card_hash,
        "pipeline_mode": "FULL_PIPELINE",
        "execution_units": [
            {"unit_id": "u1", "mutation_paths": ["nexus/a.py"]},
            {"unit_id": "u2", "mutation_paths": ["tests/test_a.py"], "priority": 2},
        ],
        "unit_verifiers": {
            "u1": [{"id": "u1", "argv": ["python3", "-m", "pytest", "-q", "tests/test_a.py"]}],
            "u2": [{"id": "u2", "argv": ["python3", "-m", "pytest", "-q", "tests/test_a.py"]}],
        },
        "whole_verifiers": [{"id": "whole", "argv": ["git", "diff", "--check"]}],
        "requested_concurrency": 2,
        "ready": True,
        "contract_ready": True,
    }
    value.update(overrides)
    return value


def _body(contract: dict) -> str:
    return "issue prose\n```nexus-external-intelligence\n" + json.dumps(contract) + "\n```\n"


def _setup(tmp_path: Path, remote_url: str = "https://github.com/o/r.git", **contract_overrides):
    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "config", "user.name", "Test Runner"], cwd=repo, capture_output=True, check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    card = repo / "tasks" / "x.md"
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text("# task\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"], cwd=repo, capture_output=True, check=True
    )
    head_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    if remote_url:
        subprocess.run(
            ["git", "remote", "add", "origin", remote_url],
            cwd=repo,
            capture_output=True,
            check=True,
        )
        subprocess.run(
            ["git", "update-ref", "refs/remotes/origin/main", head_sha],
            cwd=repo,
            capture_output=True,
            check=True,
        )

    contract_args = {"main_sha": head_sha}
    contract_args.update(contract_overrides)
    contract = _contract("tasks/x.md", _sha(card), **contract_args)
    body = _body(contract)
    store = ExternalIntelligenceStore(tmp_path / "intel")
    return repo, card, contract, body, store


class FakeSidecar:
    def __init__(self, store: ExternalIntelligenceStore, *, non_dispatched=False):
        self.store = store
        self.calls = []
        self.non_dispatched = non_dispatched

    def analyze(self, record, sources):
        self.calls.append((record, list(sources)))
        if self.non_dispatched:
            return {"status": "NOT_DISPATCHED", "intake": {"disposition": "BLOCKED"}}
        envelope = {"schema": "external_execution_envelope.v1", "x": 1}
        request_sha = "b" * 64
        path = self.store.root / "envelopes" / f"{request_sha}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(envelope, sort_keys=True, separators=(",", ":")), encoding="utf-8"
        )
        envelope_sha = hashlib.sha256(
            json.dumps(envelope, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            "status": "COMPLETED",
            "receipt_id": "receipt-1",
            "request": {"request_sha256": request_sha},
            "envelope_sha256": envelope_sha,
        }


class FakeC:
    def __init__(self, mode="ok"):
        self.calls = []
        self.mode = mode

    def run(self, units, lease):
        self.calls.append((units, lease))
        receipts = {
            unit["unit_id"]: {
                "status": "CANDIDATE_READY_FOR_VERIFICATION",
                "unit_id": unit["unit_id"],
            }
            for unit in units
        }
        if self.mode == "missing":
            receipts.pop("u2")
        if self.mode == "failed":
            receipts["u1"] = {"status": "WORKER_BLOCKED", "unit_id": "u1"}
        return {"receipts": receipts, "errors": {}, "run_sha256": "c" * 64}


class FakeD:
    def __init__(self):
        self.calls = []

    def close_task(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "status": "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE",
            "run_id": "d" * 64,
            "control_capsule": {
                "task_id": "task-1",
                "candidate_commit": "1" * 40,
                "candidate_tree": "2" * 40,
                "verification_state": "PASS",
                "current_gate": "PENDING_INDEPENDENT_ACCEPTANCE",
                "acceptance_packet_ref": "state/acceptance.json",
                "acceptance_packet_sha256": "3" * 64,
                "next_action": "independent_acceptance",
                "stop_condition": "acceptance_failed",
                "claim_ceiling": "TASK_CANDIDATE_VERIFIED_PENDING_INDEPENDENT_ACCEPTANCE",
                "secret_envelope": "must-not-leak",
            },
            "envelope": {"big": "secret"},
            "raw_prompt": "secret",
        }


def _automation(tmp_path, repo, store, sidecar=None, c=None, d=None):
    return ExternalIntelligenceAutomation(
        repository_root=repo,
        state_store=AutomationStateStore(tmp_path / "state"),
        intelligence_store=store,
        sidecar=sidecar or FakeSidecar(store),
        c_runtime=c or FakeC(),
        d_runtime=d or FakeD(),
    )


def test_contract_parser_strict_and_unknown_rejected(tmp_path):
    repo, card, contract, body, _ = _setup(tmp_path)
    assert parse_issue_contract(body)["task_id"] == "task-1"
    with pytest.raises(AutomationError):
        parse_issue_contract(body + _body(contract))
    bad = dict(contract, surprise=True)
    with pytest.raises(AutomationError):
        parse_issue_contract(_body(bad))
    bad2 = dict(contract, execution_units=[{"unit_id": "u1", "mutation_paths": []}])
    with pytest.raises(AutomationError):
        parse_issue_contract(_body(bad2))


def test_full_pipeline_opt_in_is_required_before_semantic_dispatch(tmp_path):
    repo, _, contract, _, store = _setup(tmp_path)
    contract.pop("pipeline_mode")
    sidecar = FakeSidecar(store)
    result = _automation(tmp_path, repo, store, sidecar=sidecar).run_issue(
        "o/r", 1, "title", _body(contract)
    )
    assert result["state"] == "BLOCKED"
    assert result["error"] == "ISSUE_CONTRACT_FULL_PIPELINE_OPT_IN_REQUIRED"
    assert result["semantic_dispatched"] is False
    assert sidecar.calls == []


def test_task_card_hash_mismatch_blocks_before_semantic_dispatch(tmp_path):
    repo, _, contract, body, store = _setup(tmp_path)
    contract["task_card_hash"] = "0" * 64
    body = _body(contract)
    sidecar = FakeSidecar(store)
    result = _automation(tmp_path, repo, store, sidecar=sidecar).run_issue("o/r", 1, "title", body)
    assert result["state"] == "BLOCKED"
    assert result["error"] == "TASK_CARD_HASH_MISMATCH"
    assert sidecar.calls == []


def test_malformed_contract_returns_blocked_without_crash(tmp_path):
    repo, _, _, _, store = _setup(tmp_path)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)
    result = automation.run_issue("o/r", 1, "title", "no machine block here")
    assert result["state"] == "BLOCKED"
    assert result["semantic_dispatched"] is False
    assert sidecar.calls == [] and c.calls == [] and d.calls == []


def test_ready_false_blocks_before_any_semantic_calls(tmp_path):
    repo, _, contract, _, store = _setup(tmp_path, ready=False)
    sidecar = FakeSidecar(store, non_dispatched=True)
    c = FakeC()
    d = FakeD()
    result = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d).run_issue(
        "o/r", 2, "title", _body(contract)
    )
    assert result["state"] == "BLOCKED"
    assert result["stage"] == "INTELLIGENCE"
    assert result["semantic_dispatched"] is False
    assert len(sidecar.calls) == 1
    assert c.calls == [] and d.calls == []


def test_not_ready_issue_does_not_reach_fanout(tmp_path):
    repo, _, contract, _, store = _setup(tmp_path, ready=False)
    sidecar = FakeSidecar(store, non_dispatched=True)
    c = FakeC()
    d = FakeD()
    result = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d).run_issue(
        "o/r", 2, "title", _body(contract)
    )
    assert result["state"] == "BLOCKED"
    assert result["stage"] == "INTELLIGENCE"
    assert len(sidecar.calls) == 1
    assert c.calls == [] and d.calls == []


def test_envelope_artifact_maps_units_without_scope_widening(tmp_path):
    repo, _, contract, body, store = _setup(tmp_path)
    c = FakeC()
    sidecar = FakeSidecar(store)
    result = _automation(tmp_path, repo, store, sidecar=sidecar, c=c).run_issue(
        "o/r", 3, "title", body
    )
    assert result["state"] == "COMPLETE"
    units, lease = c.calls[0]
    assert lease.requested_concurrency == 2
    assert [u["mutation_paths"] for u in units] == [["nexus/a.py"], ["tests/test_a.py"]]
    assert all(u["task_id"] == "task-1" for u in units)
    assert all(u["expected_base_sha"] == contract["main_sha"] for u in units)
    assert all(Path(u["envelope_ref"]).is_file() for u in units)
    assert len({u["envelope_sha256"] for u in units}) == 1
    assert {u["unit_id"] for u in units} == {"u1", "u2"}


def test_d_terminal_result_blocks_instead_of_complete(tmp_path):
    repo, _, contract, body, store = _setup(tmp_path)

    class TerminalD:
        def __init__(self):
            self.calls = []

        def close_task(self, **kwargs):
            self.calls.append(kwargs)
            return {"status": "REPAIR_BUDGET_EXHAUSTED", "run_id": "x" * 64, "control_capsule": {}}

    d = TerminalD()
    result = _automation(tmp_path, repo, store, d=d).run_issue("o/r", 5, "title", body)
    assert result["state"] == "BLOCKED"
    assert result["stage"] == "CLOSURE"
    assert result["semantic_dispatched"] is True
    assert result["closure_status"] == "REPAIR_BUDGET_EXHAUSTED"


@pytest.mark.parametrize("mode", ["missing", "failed"])
def test_incomplete_fanout_blocks_d(tmp_path, mode):
    repo, _, _, body, store = _setup(tmp_path)
    d = FakeD()
    result = _automation(tmp_path, repo, store, c=FakeC(mode), d=d).run_issue(
        "o/r", 4, "title", body
    )
    assert result["state"] in {"RECONCILIATION_REQUIRED", "BLOCKED"}
    assert d.calls == []


def test_d_gets_exact_verifiers_and_compact_publication(tmp_path):
    repo, _, contract, body, store = _setup(tmp_path)
    d = FakeD()
    result = _automation(tmp_path, repo, store, d=d).run_issue("o/r", 5, "title", body)
    assert result["state"] == "COMPLETE"
    call = d.calls[0]
    assert call["unit_verifiers"] == contract["unit_verifiers"]
    assert call["whole_verifiers"] == contract["whole_verifiers"]
    assert call["external_intelligence_refs"] == ["receipt-1"]
    publication = result["publication"]
    rendered = json.dumps(publication)
    assert publication["candidate_commit"] == "1" * 40
    assert "secret_envelope" not in rendered
    assert "raw_prompt" not in rendered


def test_complete_identity_reuses_without_external_calls(tmp_path):
    repo, _, contract, body, store = _setup(tmp_path)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)
    first = automation.run_issue("o/r", 6, "title", body)
    second = automation.run_issue("o/r", 6, "title", body)
    assert first["state"] == "COMPLETE"
    assert second["reuse"] is True
    assert len(sidecar.calls) == len(c.calls) == len(d.calls) == 1


@pytest.mark.parametrize("state", ["INTELLIGENCE_DISPATCHING", "FANOUT_DISPATCHING"])
def test_recoverable_dispatching_state_resumes_pipeline(tmp_path, state):
    repo, _, contract, body, store = _setup(tmp_path)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)
    item = IssueWorkItem("o/r", 7, "title", body, contract)
    automation.state_store.save(item, state)

    result = automation.run_issue("o/r", 7, "title", body)

    assert result["state"] == "COMPLETE"
    assert len(sidecar.calls) == 1
    assert len(c.calls) == 1
    assert len(d.calls) == 1
    assert automation.state_store.load(item)["state"] == "COMPLETE"


def test_recoverable_reconciliation_required_resumes_from_fanout(tmp_path):
    repo, _, contract, body, store = _setup(tmp_path)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)
    item = IssueWorkItem("o/r", 8, "title", body, contract)
    automation.state_store.save(
        item,
        "RECONCILIATION_REQUIRED",
        prior_state="FANOUT_DISPATCHING",
        semantic_dispatched=True,
    )

    result = automation.run_issue("o/r", 8, "title", body)

    assert result["state"] == "COMPLETE"
    assert len(sidecar.calls) == 1
    assert len(c.calls) == 1
    assert len(d.calls) == 1


def test_closure_dispatching_remains_fail_closed_and_d_is_not_replayed(tmp_path):
    repo, _, contract, body, store = _setup(tmp_path)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)
    item = IssueWorkItem("o/r", 9, "title", body, contract)
    automation.state_store.save(item, "CLOSURE_DISPATCHING")

    result = automation.run_issue("o/r", 9, "title", body)

    assert result["state"] == "RECONCILIATION_REQUIRED"
    assert result["prior_state"] == "CLOSURE_DISPATCHING"
    assert sidecar.calls == [] and c.calls == [] and d.calls == []
    second = automation.run_issue("o/r", 9, "title", body)
    assert second["state"] == "RECONCILIATION_REQUIRED"
    assert second["prior_state"] == "CLOSURE_DISPATCHING"
    assert sidecar.calls == [] and c.calls == [] and d.calls == []


def test_verifier_specs_use_d_compatible_id_key(tmp_path):
    from nexus.services.external_intelligence_closure import VerifierSpec

    repo, _, contract, body, store = _setup(tmp_path)
    for unit_id in contract["unit_verifiers"]:
        for spec in contract["unit_verifiers"][unit_id]:
            parsed = VerifierSpec.from_value(spec)
            assert parsed.verifier_id == unit_id
            assert parsed.argv == tuple(spec["argv"])
    for spec in contract["whole_verifiers"]:
        parsed = VerifierSpec.from_value(spec)
        assert parsed.argv == tuple(spec["argv"])


def test_e1_accepted_contract_feeds_real_c_execution_units(tmp_path):
    from nexus.services.external_intelligence_fanout import ExecutionUnit

    repo, _, contract, body, store = _setup(tmp_path)
    parsed = parse_issue_contract(body)
    for unit in parsed["execution_units"]:
        built = ExecutionUnit.from_mapping({
            "task_id": parsed["task_id"],
            "unit_id": unit["unit_id"],
            "envelope_ref": "state/envelopes/dummy.json",
            "envelope_sha256": "b" * 64,
            "expected_base_sha": parsed["main_sha"],
            "mutation_paths": unit["mutation_paths"],
            "dependencies_ready": unit.get("dependencies_ready", True),
            "priority": unit.get("priority", 0),
            "allow_deletions": unit.get("allow_deletions", False),
        })
        assert built.task_id == parsed["task_id"]
        assert built.unit_id == unit["unit_id"]
        assert built.mutation_paths == tuple(unit["mutation_paths"])
        assert built.expected_base_sha == parsed["main_sha"]
        assert built.dependencies_ready == unit.get("dependencies_ready", True)
        assert built.allow_deletions == unit.get("allow_deletions", False)


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (
            lambda c: c["unit_verifiers"].update({"u1": [{"verifier_id": "u1", "argv": ["true"]}]}),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({"u1": [{"id": "u1", "argv": []}]}),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({"u1": [{"id": "u1", "argv": [""]}]}),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({
                "u1": [{"id": "u1", "argv": ["true"], "timeout": True}]
            }),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({
                "u1": [{"id": "u1", "argv": ["true"], "timeout": 0}]
            }),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({
                "u1": [{"id": "u1", "argv": ["true"], "timeout": 1801}]
            }),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({
                "u1": [{"id": "u1", "argv": ["true"], "owner_unit": 5}]
            }),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["whole_verifiers"].append({"id": "x"}),
            "ISSUE_CONTRACT_WHOLE_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["whole_verifiers"].append({"id": "x", "argv": ["echo", "a\x00b"]}),
            "ISSUE_CONTRACT_WHOLE_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["whole_verifiers"].append({"id": "x", "argv": ["echo"] * 65}),
            "ISSUE_CONTRACT_WHOLE_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["whole_verifiers"].append({"id": "x", "argv": ["a" * 4097]}),
            "ISSUE_CONTRACT_WHOLE_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({"u1": [{"id": "bad id", "argv": ["true"]}]}),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({"u1": [{"id": "bad/id", "argv": ["true"]}]}),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({"u1": [{"id": "x" * 161, "argv": ["true"]}]}),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
        (
            lambda c: c["unit_verifiers"].update({
                "u1": [{"id": "u1", "argv": ["true"], "owner_unit": "bad owner"}]
            }),
            "ISSUE_CONTRACT_UNIT_VERIFIERS_INVALID",
        ),
    ],
)
def test_verifier_spec_strict_validation(tmp_path, mutate, expected):
    repo, _, contract, _, _ = _setup(tmp_path)
    mutate(contract)
    with pytest.raises(AutomationError) as exc:
        parse_issue_contract(_body(contract))
    assert str(exc.value) == expected


@pytest.mark.parametrize(
    "field,value",
    [
        ("task_id", "bad task"),
        ("unit_id", "bad unit"),
        ("unit_id", "_starts_underscore"),
        ("unit_id", "x" * 121),
    ],
)
def test_c_identity_slug_rejection(tmp_path, field, value):
    repo, _, contract, _, _ = _setup(tmp_path)
    if field == "task_id":
        contract["task_id"] = value
    else:
        contract["execution_units"][0]["unit_id"] = value
        contract["unit_verifiers"] = {value: contract["unit_verifiers"].pop("u1")}
    with pytest.raises(AutomationError):
        parse_issue_contract(_body(contract))


@pytest.mark.parametrize(
    "bad_path",
    [
        "../x.py",
        "a/../x.py",
        "/x.py",
        "foo\\bar.py",
        "a\x00b.py",
    ],
)
def test_mutation_path_rejection(tmp_path, bad_path):
    repo, _, contract, _, _ = _setup(tmp_path)
    contract["execution_units"][0]["mutation_paths"] = [bad_path]
    with pytest.raises(AutomationError):
        parse_issue_contract(_body(contract))


def test_duplicate_mutation_path_rejection(tmp_path):
    repo, _, contract, _, _ = _setup(tmp_path)
    contract["execution_units"][0]["mutation_paths"] = ["nexus/a.py", "nexus/a.py"]
    with pytest.raises(AutomationError):
        parse_issue_contract(_body(contract))


@pytest.mark.parametrize(
    "field,bad",
    [
        ("main_sha", "xyz"),
        ("main_sha", "a" * 39),
        ("task_card_hash", "xyz"),
        ("task_card_hash", "a" * 63),
    ],
)
def test_identity_hash_format_rejection(tmp_path, field, bad):
    repo, _, contract, _, _ = _setup(tmp_path)
    contract[field] = bad
    with pytest.raises(AutomationError):
        parse_issue_contract(_body(contract))


@pytest.mark.parametrize(
    "field,value",
    [
        ("dependencies_ready", "false"),
        ("allow_deletions", "false"),
        ("priority", "2"),
        ("priority", True),
        ("requested_concurrency", True),
    ],
)
def test_execution_unit_optional_fields_reject_coercion(tmp_path, field, value):
    repo, _, contract, _, _ = _setup(tmp_path)
    if field == "requested_concurrency":
        contract[field] = value
    else:
        contract["execution_units"][0][field] = value
    with pytest.raises(AutomationError):
        parse_issue_contract(_body(contract))


def test_valid_optional_unit_fields_parse_without_coercion(tmp_path):
    repo, _, contract, _, _ = _setup(tmp_path)
    contract["execution_units"][0].update({
        "dependencies_ready": False,
        "allow_deletions": True,
        "priority": 0,
    })
    parsed = parse_issue_contract(_body(contract))
    unit = parsed["execution_units"][0]
    assert unit["dependencies_ready"] is False
    assert unit["allow_deletions"] is True
    assert unit["priority"] == 0
    assert parsed["requested_concurrency"] == 2


def test_publication_payload_only_reads_capsule():
    payload = compact_publication_payload({
        "status": "PASS",
        "control_capsule": {
            "task_id": "t",
            "candidate_commit": "a",
            "candidate_tree": "b",
            "current_gate": "g",
            "acceptance_packet_ref": "r",
            "acceptance_packet_sha256": "s",
            "next_action": "n",
            "stop_if": ["x"],
            "claim_ceiling": "c",
            "envelope": "secret",
        },
        "raw_prompt": "secret",
    })
    rendered = json.dumps(payload)
    assert "secret" not in rendered
    assert "envelope" not in rendered


def test_source_does_not_hardcode_profile_id():
    source = Path("nexus/services/external_intelligence_automation.py").read_text(encoding="utf-8")
    assert "64b57tak" not in source


def test_source_binding_positive_matching_lineage_passes(tmp_path):
    repo, _, contract, body, store = _setup(
        tmp_path, remote_url="https://github.com/James3014/Nexus-new.git"
    )
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)
    result = automation.run_issue("James3014/Nexus-new", 101, "title", body)
    assert result["state"] == "COMPLETE"
    assert result["semantic_dispatched"] is True
    assert len(sidecar.calls) == 1
    assert len(c.calls) == 1
    assert len(d.calls) == 1


def test_source_binding_sha_object_missing_blocks(tmp_path):
    repo, _, contract, body, store = _setup(
        tmp_path, remote_url="https://github.com/James3014/Nexus-new.git", main_sha="0" * 40
    )
    body = _body(contract)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)
    result = automation.run_issue("James3014/Nexus-new", 102, "title", body)
    assert result["state"] == "BLOCKED"
    assert result["error"] == "MAIN_SHA_OBJECT_MISSING"
    assert result["semantic_dispatched"] is False
    assert sidecar.calls == [] and c.calls == [] and d.calls == []


def test_source_binding_repository_mismatch_blocks(tmp_path):
    repo, _, contract, body, store = _setup(
        tmp_path, remote_url="https://github.com/James3014/Nexus-new.git"
    )
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)
    result = automation.run_issue("James3014/Nexus-other", 103, "title", body)
    assert result["state"] == "BLOCKED"
    assert result["error"] == "REPOSITORY_IDENTITY_MISMATCH"
    assert result["semantic_dispatched"] is False
    assert sidecar.calls == [] and c.calls == [] and d.calls == []


def test_source_binding_shared_db_unrelated_lineage_blocks_v7_regression(tmp_path):
    repo, _, contract, _, store = _setup(
        tmp_path, remote_url="https://github.com/James3014/Nexus-new.git"
    )

    subprocess.run(
        ["git", "checkout", "--orphan", "unrelated-branch"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "unrelated lineage commit"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    unrelated_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(["git", "checkout", "main"], cwd=repo, capture_output=True, check=True)

    cat_check = subprocess.run(
        ["git", "cat-file", "-t", unrelated_sha],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    assert cat_check.stdout.strip() == "commit"

    contract["main_sha"] = unrelated_sha
    body = _body(contract)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)

    result = automation.run_issue("James3014/Nexus-new", 104, "title", body)
    assert result["state"] == "BLOCKED"
    assert result["error"] == "MAIN_SHA_LINEAGE_MISMATCH"
    assert result["semantic_dispatched"] is False
    assert sidecar.calls == [] and c.calls == [] and d.calls == []


def test_source_binding_remote_tracking_ref_missing_blocks(tmp_path):
    repo, _, contract, body, store = _setup(tmp_path, remote_url="")
    subprocess.run(
        ["git", "remote", "add", "origin", "https://github.com/James3014/Nexus-new.git"],
        cwd=repo,
        capture_output=True,
        check=True,
    )
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)

    result = automation.run_issue("James3014/Nexus-new", 105, "title", body)
    assert result["state"] == "BLOCKED"
    assert result["error"] == "REMOTE_TRACKING_MAIN_NOT_FOUND"
    assert result["semantic_dispatched"] is False
    assert sidecar.calls == [] and c.calls == [] and d.calls == []


def test_source_binding_not_a_commit_object_blocks(tmp_path):
    repo, _, contract, _, store = _setup(
        tmp_path, remote_url="https://github.com/James3014/Nexus-new.git"
    )
    tree_sha = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    contract["main_sha"] = tree_sha
    body = _body(contract)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)

    result = automation.run_issue("James3014/Nexus-new", 106, "title", body)
    assert result["state"] == "BLOCKED"
    assert result["error"] == "MAIN_SHA_NOT_COMMIT"
    assert result["semantic_dispatched"] is False
    assert sidecar.calls == [] and c.calls == [] and d.calls == []


def test_source_binding_ancestor_commit_passes(tmp_path):
    repo, _, contract, _, store = _setup(
        tmp_path, remote_url="https://github.com/James3014/Nexus-new.git"
    )
    first_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    card2 = repo / "tasks" / "y.md"
    card2.write_text("# second\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True, check=True)
    subprocess.run(
        ["git", "commit", "-m", "second commit"], cwd=repo, capture_output=True, check=True
    )
    second_sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()
    subprocess.run(
        ["git", "update-ref", "refs/remotes/origin/main", second_sha],
        cwd=repo,
        capture_output=True,
        check=True,
    )

    contract["main_sha"] = first_sha
    body = _body(contract)
    sidecar = FakeSidecar(store)
    c = FakeC()
    d = FakeD()
    automation = _automation(tmp_path, repo, store, sidecar=sidecar, c=c, d=d)

    result = automation.run_issue("James3014/Nexus-new", 107, "title", body)
    assert result["state"] == "COMPLETE"
    assert result["semantic_dispatched"] is True
    assert len(sidecar.calls) == 1
