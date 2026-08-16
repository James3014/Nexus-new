from __future__ import annotations

import json
import subprocess

import pytest

from nexus.services.external_intelligence import (
    CLAIM_CEILING,
    CONTROL_CAPSULE_SCHEMA,
    ENVELOPE_SCHEMA,
    RECEIPT_SCHEMA,
    ExternalIntelligenceError,
    ExternalIntelligenceSidecar,
    ExternalIntelligenceStore,
    OpenCLIExternalIntelligenceTransport,
    TransportResult,
    build_context_pack,
    build_prompt,
    build_request,
    normalize_intake,
    parse_external_execution_envelope,
    project_refresh,
)


def record(**updates):
    value = {
        "repository": "James3014/Nexus-new",
        "item_type": "issue",
        "item_id": "321",
        "revision": "issue-rev-7",
        "main_sha": "a" * 40,
        "task_card_ref": "tasks/campaign/00-task.md",
        "task_card_hash": "b" * 64,
        "dependency_state": {"ready": True, "closed": [12]},
        "overlap_state": {"active_prs": []},
        "active_elsewhere": False,
        "needs_reconciliation": False,
        "contract_ready": True,
        "ready": True,
        "blocked_reasons": [],
    }
    value.update(updates)
    return value


def sources():
    return [
        {
            "kind": "task_card",
            "ref": "tasks/campaign/00-task.md",
            "revision": "b" * 64,
            "provenance": "git",
            "content": "Task contract\nAUTO_CHAIN: false\n",
        },
        {
            "kind": "source",
            "ref": "nexus/example.py",
            "revision": "a" * 40,
            "provenance": "git",
            "content": "def value():\n    return 1\n",
        },
    ]


def request_and_pack():
    intake = normalize_intake(record())
    pack = build_context_pack(sources())
    return build_request(intake, pack), pack


def envelope_for(request, **updates):
    identity = request["identity"]
    value = {
        "schema": ENVELOPE_SCHEMA,
        "binding": {
            "repository": identity["repository"],
            "item_type": identity["item_type"],
            "item_id": identity["item_id"],
            "revision": identity["revision"],
            "main_sha": identity["main_sha"],
            "task_card_ref": identity["task_card_ref"],
            "task_card_hash": identity["task_card_hash"],
            "context_pack_sha256": request["context_pack_sha256"],
        },
        "goal": "Implement the bounded task.",
        "root_cause": "Current implementation lacks the required bounded behavior.",
        "scope_signal": {
            "production_edit_paths": ["nexus/example.py"],
            "required_test_edit_paths": ["tests/test_example.py"],
            "conditional_migration_paths": [],
            "read_only_authorities": ["AGENTS.md"],
            "verification_only_paths": [],
            "forbidden_paths": ["nexus/orchestrator/unified_mcp_gateway.py"],
            "max_files": 2,
            "scope_confidence": "HIGH",
            "scope_block_conditions": ["task card scope expands"],
        },
        "implementation_signal": {
            "inspect_first": ["nexus/example.py"],
            "proven_facts": ["the target file is in scope"],
            "required_semantics": ["preserve existing API"],
            "suggested_direction": ["make the smallest bounded change"],
            "forbidden_behavior": ["do not change route authority"],
        },
        "verification_signal": {
            "red_probe": "pytest -q tests/test_example.py",
            "positive_probes": ["pytest -q tests/test_example.py"],
            "hostile_negative_probes": ["reject out-of-scope changes"],
            "impact_suites": [],
            "static_checks": ["git diff --check"],
            "false_green_conditions": ["empty diff"],
        },
        "worker_binding": {
            "assigned_thread": "UNASSIGNED",
            "persistent_thread": True,
            "create_subagent": False,
            "fallback_allowed": False,
        },
        "model_adaptation": {
            "role_contract": ["DeepSeek V4 Flash L2 Task Engineer, bounded single task"],
            "task_local_invariants": ["preserve the existing public API"],
            "known_failure_guards": ["avoid out-of-scope writes"],
            "execution_strategy": ["make the smallest bounded change with task-local judgment"],
            "forbidden_inferences": ["implementation-as-policy", "authority overreach"],
            "repair_policy": ["one evidence-guided same-unit repair", "no blind retry"],
        },
        "stop_conditions": ["scope expands", "worker transport unavailable"],
    }
    value.update(updates)
    return value


def test_intake_classification_precedence_and_exact_identity():
    executable = normalize_intake(record())
    assert executable["disposition"] == "EXECUTABLE"
    assert executable["claim_ceiling"] == CLAIM_CEILING
    assert executable["identity"]["repository"] == "James3014/Nexus-new"
    assert len(executable["identity_sha256"]) == 64

    assert normalize_intake(record(active_elsewhere=True))["disposition"] == "ACTIVE_ELSEWHERE"
    assert (
        normalize_intake(record(needs_reconciliation=True))["disposition"] == "NEEDS_RECONCILIATION"
    )
    assert (
        normalize_intake(record(blocked_reasons=["dependency blocked"]))["disposition"] == "BLOCKED"
    )
    assert normalize_intake(record(ready=False))["disposition"] == "BLOCKED"
    assert normalize_intake(record(contract_ready=False))["disposition"] == "NEEDS_CONTRACT_SLICE"
    assert normalize_intake(record(task_card_hash=""))["disposition"] == "NEEDS_CONTRACT_SLICE"


def test_material_identity_changes_only_for_material_projection():
    base = normalize_intake(record())
    same = normalize_intake({**record(), "title": "display-only field"})
    changed_main = normalize_intake(record(main_sha="c" * 40))
    changed_overlap = normalize_intake(record(overlap_state={"active_prs": [99]}))
    assert base["identity_sha256"] == same["identity_sha256"]
    assert base["identity_sha256"] != changed_main["identity_sha256"]
    assert base["identity_sha256"] != changed_overlap["identity_sha256"]


def test_context_pack_is_deterministic_bounded_and_preserves_provenance():
    first = build_context_pack(reversed(sources()), max_bytes=40, per_source_bytes=24)
    second = build_context_pack(sources(), max_bytes=40, per_source_bytes=24)
    assert first == second
    assert sum(entry["included_bytes"] for entry in first["entries"]) <= 40
    assert first["entries"][0]["provenance"] == "git"
    assert all(len(entry["source_sha256"]) == 64 for entry in first["entries"])
    assert len(first["context_pack_sha256"]) == 64


def test_context_pack_utf8_truncation_never_breaks_encoding():
    pack = build_context_pack(
        [
            {
                "kind": "source",
                "ref": "x",
                "revision": "r",
                "provenance": "git",
                "content": "雪" * 50,
            }
        ],
        max_bytes=17,
        per_source_bytes=17,
    )
    content = pack["entries"][0]["content"]
    assert content.encode("utf-8").decode("utf-8") == content
    assert pack["entries"][0]["included_bytes"] <= 17
    assert pack["entries"][0]["truncated"] is True


def test_strict_envelope_parser_accepts_contract_and_rejects_drift():
    request, _ = request_and_pack()
    valid = envelope_for(request)
    assert parse_external_execution_envelope(json.dumps(valid))["schema"] == ENVELOPE_SCHEMA

    extra = dict(valid)
    extra["unexpected"] = True
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(json.dumps(extra))

    malformed = (
        json
        .dumps(valid)
        .replace("Implement the bounded task.", "bad\nline")
        .replace("\\n", "\n", 1)
    )
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(malformed)

    fenced = "```json\n" + json.dumps(valid) + "\n```"
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(fenced)


def test_prompt_binds_exact_identity_and_phase_ab_worker_boundary():
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    assert "BEGIN_UNTRUSTED_CONTEXT" in prompt and "END_UNTRUSTED_CONTEXT" in prompt
    assert request["identity"]["task_card_hash"] in prompt
    assert request["context_pack_sha256"] in prompt
    assert "INTAKE_PROJECTION=" in prompt
    assert "dependency_state" in prompt and "overlap_state" in prompt
    assert "assigned_thread must be UNASSIGNED" in prompt
    assert "create_subagent=false" in prompt
    assert "fallback_allowed=false" in prompt
    assert "standard json.loads" in prompt


def test_request_and_refresh_projection_reuse_vs_stale():
    request, _ = request_and_pack()
    previous = {"schema": RECEIPT_SCHEMA, "request": request}
    assert project_refresh(previous, request)["status"] == "REUSE"

    new_pack = build_context_pack(
        sources()
        + [
            {
                "kind": "test",
                "ref": "tests/x.py",
                "revision": "z",
                "provenance": "git",
                "content": "assert True",
            }
        ]
    )
    stale_context = build_request(normalize_intake(record()), new_pack)
    projection = project_refresh(previous, stale_context)
    assert projection["status"] == "STALE"
    assert "context_pack_sha256" in projection["changed_fields"]

    stale_main = build_request(normalize_intake(record(main_sha="d" * 40)), new_pack)
    assert "identity_sha256" in project_refresh(previous, stale_main)["changed_fields"]


def test_store_journals_before_dispatch_and_blocks_blind_replay(tmp_path):
    request, _ = request_and_pack()
    store = ExternalIntelligenceStore(tmp_path)
    attempt = store.prepare(request)
    assert attempt["state"] == "PREPARED" and attempt["retry_safe"] is True
    durable_request = json.loads(
        (tmp_path / "requests" / f"{request['request_sha256']}.json").read_text()
    )
    assert durable_request == request
    dispatched = store.mark_dispatching(attempt)
    assert dispatched["state"] == "DISPATCHING" and dispatched["retry_safe"] is False
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_RECONCILIATION_REQUIRED"):
        store.prepare(request)


def test_opencli_transport_uses_stable_detail_not_ask_snapshot(monkeypatch):
    request, _ = request_and_pack()
    stable = json.dumps(envelope_for(request))
    calls = []

    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.args = args
            self.returncode = 0
            self.pid = 4321
            self.stdout = None
            self.stderr = None
            calls.append(args)

        def communicate(self, timeout=None):
            if self.args[2] == "ask":
                return json.dumps([
                    {"conversationId": "conv-1", "response": "ask-snapshot-invalid"}
                ]), ""
            return json.dumps([
                {"Role": "Assistant", "Text": stable, "Generating": False, "StableSeconds": 6}
            ]), ""

    monkeypatch.setattr(subprocess, "Popen", FakeProcess)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke("prompt")
    assert result.status == "INTELLIGENCE_COMPLETED"
    assert result.raw == stable
    assert result.conversation_id == "conv-1"
    assert [call[2] for call in calls] == ["ask", "detail"]
    assert result.safe_argv[3] == "<prompt>"


def test_opencli_transport_fails_closed_when_stable_read_invalid(monkeypatch):
    calls = []

    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.args = args
            self.returncode = 0
            self.pid = 4321
            self.stdout = None
            self.stderr = None
            calls.append(args)

        def communicate(self, timeout=None):
            if self.args[2] == "ask":
                return json.dumps([{"conversationId": "conv-1", "response": "looks-good"}]), ""
            return json.dumps([
                {"Role": "Assistant", "Text": "{}", "Generating": True, "StableSeconds": 0}
            ]), ""

    monkeypatch.setattr(subprocess, "Popen", FakeProcess)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke("prompt")
    assert result.status == "OPENCLI_STABLE_READ_FAILURE"
    assert result.retry_safe is False
    assert [call[2] for call in calls] == ["ask", "detail"]


def test_opencli_ask_failure_after_process_start_is_reconciled_not_retried(monkeypatch):
    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.args = args
            self.returncode = 3
            self.pid = 4321
            self.stdout = None
            self.stderr = None

        def communicate(self, timeout=None):
            return "partial", "failed"

    monkeypatch.setattr(subprocess, "Popen", FakeProcess)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke("prompt")
    assert result.status == "OPENCLI_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert result.retry_safe is False


def test_sidecar_does_not_dispatch_non_executable_intake(tmp_path):
    class NeverTransport:
        def invoke(self, prompt):
            raise AssertionError("transport must not run")

    sidecar = ExternalIntelligenceSidecar(
        transport=NeverTransport(), store=ExternalIntelligenceStore(tmp_path)
    )
    result = sidecar.analyze(record(active_elsewhere=True), sources())
    assert result["status"] == "NOT_DISPATCHED"
    assert result["intake"]["disposition"] == "ACTIVE_ELSEWHERE"


def test_sidecar_completes_receipt_builds_small_control_capsule_and_reuses(tmp_path):
    intake = normalize_intake(record())
    pack = build_context_pack(sources())
    request = build_request(intake, pack)
    raw = json.dumps(envelope_for(request), separators=(",", ":"))

    class Transport:
        calls = 0

        def invoke(self, prompt):
            self.calls += 1
            return TransportResult(
                "INTELLIGENCE_COMPLETED",
                raw,
                conversation_id="conv-42",
                retry_safe=False,
                safe_argv=("opencli", "chatgpt", "ask", "<prompt>"),
            )

    transport = Transport()
    sidecar = ExternalIntelligenceSidecar(
        transport=transport, store=ExternalIntelligenceStore(tmp_path)
    )
    receipt = sidecar.analyze(record(), sources())
    assert receipt["status"] == "COMPLETED"
    assert receipt["transport_status"] == "INTELLIGENCE_COMPLETED"
    assert receipt["claim_ceiling"] == CLAIM_CEILING
    assert receipt["refresh_projection"]["status"] == "NEW"
    assert receipt["envelope"]["worker_binding"]["assigned_thread"] == "UNASSIGNED"
    assert len(receipt["envelope_sha256"]) == 64
    durable_envelope = json.loads(
        (tmp_path / "envelopes" / f"{request['request_sha256']}.json").read_text()
    )
    assert durable_envelope == receipt["envelope"]
    capsule = receipt["control_capsule"]
    assert capsule["schema"] == CONTROL_CAPSULE_SCHEMA
    assert capsule["current_gate"] == "PRE_IMPLEMENTATION_INTELLIGENCE_READY"
    assert capsule["intelligence_envelope_sha256"] == receipt["envelope_sha256"]
    assert capsule["refresh_status"] == "NEW"
    assert capsule["next_action"].endswith("separate_worker_transport_gate")
    assert "scope_signal" not in capsule and "implementation_signal" not in capsule
    assert transport.calls == 1

    reused = sidecar.analyze(record(), sources())
    assert reused["reuse"] is True
    assert reused["receipt_id"] == receipt["receipt_id"]
    assert transport.calls == 1


def test_sidecar_refreshes_stale_material_identity_without_reusing_old_receipt(tmp_path):
    first_request = build_request(normalize_intake(record()), build_context_pack(sources()))
    first_raw = json.dumps(envelope_for(first_request), separators=(",", ":"))

    class FirstTransport:
        def invoke(self, prompt):
            return TransportResult("INTELLIGENCE_COMPLETED", first_raw, conversation_id="first")

    store = ExternalIntelligenceStore(tmp_path)
    first = ExternalIntelligenceSidecar(transport=FirstTransport(), store=store).analyze(
        record(), sources()
    )

    changed_record = record(main_sha="c" * 40, overlap_state={"active_prs": [88]})
    second_request = build_request(normalize_intake(changed_record), build_context_pack(sources()))
    second_raw = json.dumps(envelope_for(second_request), separators=(",", ":"))

    class SecondTransport:
        calls = 0

        def invoke(self, prompt):
            self.calls += 1
            return TransportResult("INTELLIGENCE_COMPLETED", second_raw, conversation_id="second")

    second_transport = SecondTransport()
    second = ExternalIntelligenceSidecar(transport=second_transport, store=store).analyze(
        changed_record, sources()
    )
    assert second_transport.calls == 1
    assert second["receipt_id"] != first["receipt_id"]
    assert second["refresh_projection"]["status"] == "STALE"
    assert second["refresh_projection"]["previous_receipt_id"] == first["receipt_id"]
    assert "identity_sha256" in second["refresh_projection"]["changed_fields"]
    assert second["control_capsule"]["refresh_status"] == "STALE"


def test_sidecar_rejects_binding_drift_and_worker_dispatch_claims(tmp_path):
    intake = normalize_intake(record())
    pack = build_context_pack(sources())
    request = build_request(intake, pack)

    bad_binding = envelope_for(request)
    bad_binding["binding"]["main_sha"] = "f" * 40

    class BadBindingTransport:
        def invoke(self, prompt):
            return TransportResult(
                "INTELLIGENCE_COMPLETED", json.dumps(bad_binding), conversation_id="c"
            )

    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_BINDING_MISMATCH"):
        ExternalIntelligenceSidecar(
            transport=BadBindingTransport(), store=ExternalIntelligenceStore(tmp_path / "binding")
        ).analyze(record(), sources())

    bad_worker = envelope_for(request)
    bad_worker["worker_binding"] = {
        "assigned_thread": "d1",
        "persistent_thread": True,
        "create_subagent": False,
        "fallback_allowed": False,
    }

    class BadWorkerTransport:
        def invoke(self, prompt):
            return TransportResult(
                "INTELLIGENCE_COMPLETED", json.dumps(bad_worker), conversation_id="c"
            )

    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_WORKER_BOUNDARY_VIOLATION"):
        ExternalIntelligenceSidecar(
            transport=BadWorkerTransport(), store=ExternalIntelligenceStore(tmp_path / "worker")
        ).analyze(record(), sources())


def test_sidecar_transport_uncertainty_is_reconciliation_not_retry(tmp_path):
    class UnknownTransport:
        def invoke(self, prompt):
            return TransportResult(
                "OPENCLI_OUTCOME_UNKNOWN", outcome_unknown=True, retry_safe=False
            )

    store = ExternalIntelligenceStore(tmp_path)
    sidecar = ExternalIntelligenceSidecar(transport=UnknownTransport(), store=store)
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_RECONCILIATION_REQUIRED"):
        sidecar.analyze(record(), sources())

    request, _ = request_and_pack()
    attempt = json.loads((tmp_path / "attempts" / f"{request['request_sha256']}.json").read_text())
    assert attempt["state"] == "OUTCOME_UNKNOWN"
    assert attempt["retry_safe"] is False


def test_prompt_requires_required_properties_and_forbidden_behavior():
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    assert "OUTPUT_COMPLETENESS" in prompt
    assert "every property declared in every `required` array of the SCHEMA" in prompt
    assert "no required property may be omitted" in prompt
    assert "emit [] rather than omitting the key" in prompt
    assert "implementation_signal MUST include all five keys" in prompt
    assert "forbidden_behavior" in prompt
    assert "inspect_first" in prompt and "proven_facts" in prompt
    assert "required_semantics" in prompt and "suggested_direction" in prompt
    assert "exactly the allowed keys and no extras" in prompt
    assert "do not include unescaped double-quote characters" in prompt
    assert "accepted by standard json.loads without repair" in prompt
    assert "SCHEMA=" in prompt and "BINDING=" in prompt


def test_envelope_parser_still_rejects_missing_forbidden_behavior():
    request, _ = request_and_pack()
    envelope = envelope_for(request)
    del envelope["implementation_signal"]["forbidden_behavior"]
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(json.dumps(envelope))


def test_model_adaptation_valid_envelope_parses():
    request, _ = request_and_pack()
    valid = envelope_for(request)
    parsed = parse_external_execution_envelope(json.dumps(valid))
    assert parsed["model_adaptation"]["role_contract"] == [
        "DeepSeek V4 Flash L2 Task Engineer, bounded single task"
    ]
    assert set(parsed["model_adaptation"]) == {
        "role_contract",
        "task_local_invariants",
        "known_failure_guards",
        "execution_strategy",
        "forbidden_inferences",
        "repair_policy",
    }


def test_model_adaptation_missing_object_fails_closed():
    request, _ = request_and_pack()
    envelope = envelope_for(request)
    del envelope["model_adaptation"]
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(json.dumps(envelope))


def test_model_adaptation_missing_key_fails_closed():
    request, _ = request_and_pack()
    envelope = envelope_for(request)
    del envelope["model_adaptation"]["repair_policy"]
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(json.dumps(envelope))


def test_model_adaptation_extra_key_fails_closed():
    request, _ = request_and_pack()
    envelope = envelope_for(request)
    envelope["model_adaptation"]["unexpected_field"] = ["x"]
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(json.dumps(envelope))


def test_model_adaptation_wrong_type_fails_closed():
    request, _ = request_and_pack()
    envelope = envelope_for(request)
    envelope["model_adaptation"] = {
        "role_contract": "not-an-array",
        "task_local_invariants": [],
        "known_failure_guards": [],
        "execution_strategy": [],
        "forbidden_inferences": [],
        "repair_policy": [],
    }
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(json.dumps(envelope))


def test_model_adaptation_non_string_item_fails_closed():
    request, _ = request_and_pack()
    envelope = envelope_for(request)
    envelope["model_adaptation"]["execution_strategy"] = ["action", 42]
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        parse_external_execution_envelope(json.dumps(envelope))


def test_prompt_instructs_deepseek_model_adaptation_brief_not_governance_dump():
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    assert "MODEL_ADAPTATION" in prompt
    assert "DeepSeek V4 Flash L2 Task Engineer" in prompt
    assert "do not paste broad governance text" in prompt
    assert "model_adaptation must include all six keys" in prompt
    assert (
        "role_contract, task_local_invariants, known_failure_guards, execution_strategy, forbidden_inferences, repair_policy"
        in prompt
    )
    assert "derived from current task-local evidence only" in prompt
    assert (
        "task-relevant failure families, never mechanically include every historical failure family"
        in prompt
    )
    assert "leave bounded task-local engineering judgment" in prompt
    assert "implementation-as-policy" in prompt and "authority overreach" in prompt
    assert "one evidence-guided same-unit repair" in prompt
    assert "no blind retry or auto-chain" in prompt
    assert "not a full policy or governance dump" in prompt


def test_prompt_keeps_phase_ab_worker_boundary_and_scope_semantics_with_model_adaptation():
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    assert "assigned_thread must be UNASSIGNED" in prompt
    assert "persistent_thread=true" in prompt
    assert "create_subagent=false" in prompt
    assert "fallback_allowed=false" in prompt
    assert "The binding object MUST exactly equal the supplied binding" in prompt
    assert "exactly the allowed keys and no extras" in prompt
    assert "implementation_signal MUST include all five keys" in prompt
    assert "SCHEMA=" in prompt


class TimeoutReconcileFake:
    """Fake subprocess.Popen emulating ask-timeout + read-only history/detail reconciliation."""

    def __init__(self, args, **kwargs):
        self.args = args
        self.returncode = 0
        self.pid = 4321
        self.stdout = None
        self.stderr = None
        self.calls = []

    def communicate(self, timeout=None):
        cmd = self.args[2]
        if cmd == "ask":
            if timeout is not None:
                raise subprocess.TimeoutExpired(cmd=self.args, timeout=timeout)
            return "", ""
        if cmd == "history":
            return json.dumps(self._history_rows()), ""
        if cmd == "detail":
            if "--wait" in self.args:
                return json.dumps(self._stable_detail()), ""
            return json.dumps(self._scan_detail(self.args[3])), ""
        return "", ""

    def _history_rows(self):
        raise NotImplementedError

    def _scan_detail(self, conversation_id):
        raise NotImplementedError

    def _stable_detail(self):
        raise NotImplementedError


def test_nonzero_ask_reconcile_recovers_exactly_one_matching_conversation(monkeypatch):
    request, pack = request_and_pack()
    stable = json.dumps(envelope_for(request))
    prompt = build_prompt(request, pack)
    ask_seen = []

    class Fake(TimeoutReconcileFake):
        def __init__(self, args, **kwargs):
            super().__init__(args, **kwargs)
            if args[2] == "ask":
                self.returncode = 3
                ask_seen.append(args)

        def communicate(self, timeout=None):
            if self.args[2] == "ask":
                return "partial", "bridge disconnected after dispatch"
            return super().communicate(timeout=timeout)

        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-match", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": prompt,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            return [{"Role": "Assistant", "Text": stable, "Generating": False, "StableSeconds": 6}]

    monkeypatch.setattr(subprocess, "Popen", Fake)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "INTELLIGENCE_COMPLETED"
    assert result.raw == stable
    assert result.conversation_id == "conv-match"
    assert result.retry_safe is False
    assert len(ask_seen) == 1


def test_timeout_reconcile_recovers_exactly_one_matching_conversation(monkeypatch):
    request, pack = request_and_pack()
    stable = json.dumps(envelope_for(request))
    prompt = build_prompt(request, pack)

    class Fake(TimeoutReconcileFake):
        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-match", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": prompt,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            return [{"Role": "Assistant", "Text": stable, "Generating": False, "StableSeconds": 6}]

    monkeypatch.setattr(subprocess, "Popen", Fake)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "INTELLIGENCE_COMPLETED"
    assert result.raw == stable
    assert result.conversation_id == "conv-match"
    assert result.retry_safe is False


def test_timeout_reconcile_zero_matches_returns_outcome_unknown(monkeypatch):
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)

    class Fake(TimeoutReconcileFake):
        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-other", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": "unrelated prompt",
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            raise AssertionError("stable detail must not be reached")

    monkeypatch.setattr(subprocess, "Popen", Fake)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "OPENCLI_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True


def test_timeout_reconcile_multiple_matches_returns_outcome_unknown(monkeypatch):
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)

    class Fake(TimeoutReconcileFake):
        def _history_rows(self):
            return [
                {"Index": 1, "Id": "conv-a", "Title": "t", "Url": "u"},
                {"Index": 2, "Id": "conv-b", "Title": "t", "Url": "u"},
            ]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": prompt,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            raise AssertionError("stable detail must not be reached for ambiguous match")

    monkeypatch.setattr(subprocess, "Popen", Fake)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "OPENCLI_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True


def test_timeout_reconcile_unstable_detail_fails_closed(monkeypatch):
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)

    class Fake(TimeoutReconcileFake):
        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-match", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": prompt,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            return [
                {"Role": "Assistant", "Text": "in progress", "Generating": True, "StableSeconds": 0}
            ]

    monkeypatch.setattr(subprocess, "Popen", Fake)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "OPENCLI_STABLE_READ_FAILURE"
    assert result.retry_safe is False


def test_timeout_reconcile_similar_title_but_different_prompt_does_not_match(monkeypatch):
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)

    class Fake(TimeoutReconcileFake):
        def _history_rows(self):
            return [
                {
                    "Index": 1,
                    "Id": "conv-similar",
                    "Title": "External Intelligence Pre-Implementation",
                    "Url": "u",
                }
            ]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": "completely different prompt text",
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            raise AssertionError("stable detail must not be reached for non-matching prompt")

    monkeypatch.setattr(subprocess, "Popen", Fake)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "OPENCLI_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True


def test_timeout_reconcile_malformed_envelope_still_rejected_by_sidecar(tmp_path, monkeypatch):
    request, pack = request_and_pack()
    malformed = json.dumps({"schema": ENVELOPE_SCHEMA, "binding": request["identity"], "goal": "x"})
    prompt = build_prompt(request, pack)

    class Fake(TimeoutReconcileFake):
        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-match", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": prompt,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            return [
                {"Role": "Assistant", "Text": malformed, "Generating": False, "StableSeconds": 6}
            ]

    monkeypatch.setattr(subprocess, "Popen", Fake)
    store = ExternalIntelligenceStore(tmp_path)
    sidecar = ExternalIntelligenceSidecar(
        transport=OpenCLIExternalIntelligenceTransport(executable="opencli"), store=store
    )
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        sidecar.analyze(record(), sources())
    request, _ = request_and_pack()
    assert not (tmp_path / "envelopes" / f"{request['request_sha256']}.json").exists()
    assert not (tmp_path / "receipts" / f"{request['request_sha256']}.json").exists()


def test_sidecar_restart_reconciles_dispatching_attempt_without_second_ask(tmp_path):
    intake = normalize_intake(record())
    pack = build_context_pack(sources())
    request = build_request(intake, pack)
    valid = json.dumps(envelope_for(request))
    store = ExternalIntelligenceStore(tmp_path)
    attempt = store.prepare(request)
    store.mark_dispatching(attempt)

    class Transport:
        invoke_calls = 0
        reconcile_calls = 0

        def invoke(self, prompt):
            self.invoke_calls += 1
            raise AssertionError("restart must not resend semantic ask")

        def reconcile(self, prompt):
            self.reconcile_calls += 1
            return TransportResult(
                "INTELLIGENCE_COMPLETED",
                valid,
                conversation_id="conv-recovered",
                retry_safe=False,
                safe_argv=("opencli", "chatgpt", "ask", "<prompt>"),
            )

    transport = Transport()
    result = ExternalIntelligenceSidecar(transport=transport, store=store).analyze(
        record(), sources()
    )
    assert result["status"] == "COMPLETED"
    assert result["conversation_id"] == "conv-recovered"
    assert transport.invoke_calls == 0
    assert transport.reconcile_calls == 1
    final_attempt = store.load_attempt(request)
    assert final_attempt["state"] == "COMPLETED"
    assert final_attempt["retry_safe"] is False


def test_timeout_reconcile_valid_envelope_completes_with_exactly_one_ask(tmp_path, monkeypatch):
    request, pack = request_and_pack()
    valid = json.dumps(envelope_for(request))
    prompt = build_prompt(request, pack)
    ask_seen = []

    class Fake(TimeoutReconcileFake):
        def __init__(self, args, **kwargs):
            super().__init__(args, **kwargs)
            if args[2] == "ask":
                ask_seen.append(args)

        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-match", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": prompt,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            return [{"Role": "Assistant", "Text": valid, "Generating": False, "StableSeconds": 6}]

    monkeypatch.setattr(subprocess, "Popen", Fake)
    store = ExternalIntelligenceStore(tmp_path)
    sidecar = ExternalIntelligenceSidecar(
        transport=OpenCLIExternalIntelligenceTransport(executable="opencli"), store=store
    )
    result = sidecar.analyze(record(), sources())
    assert result["status"] == "COMPLETED"
    assert result["transport_status"] == "INTELLIGENCE_COMPLETED"
    assert len(ask_seen) == 1
    request, _ = request_and_pack()
    assert (tmp_path / "envelopes" / f"{request['request_sha256']}.json").exists()
    assert (tmp_path / "receipts" / f"{request['request_sha256']}.json").exists()


def test_prompt_emits_exactly_one_request_marker_before_untrusted_context():
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    marker = f"NEXUS_REQUEST_SHA256={request['request_sha256']}"
    assert prompt.count(marker) == 1
    assert prompt.find(marker) < prompt.find("BEGIN_UNTRUSTED_CONTEXT")
    assert prompt.find(marker) > 0
    assert marker.startswith("NEXUS_REQUEST_SHA256=")
    sha_part = marker[len("NEXUS_REQUEST_SHA256=") :]
    assert len(sha_part) == 64
    assert all(c in "0123456789abcdef" for c in sha_part)


def test_build_prompt_fails_closed_on_missing_request_sha():
    request, pack = request_and_pack()
    request = dict(request)
    request.pop("request_sha256", None)
    with pytest.raises(ExternalIntelligenceError, match="INVALID_REQUEST_IDENTITY"):
        build_prompt(request, pack)


def test_build_prompt_fails_closed_on_malformed_request_sha():
    request, pack = request_and_pack()
    request = dict(request)
    request["request_sha256"] = "not-a-valid-sha"
    with pytest.raises(ExternalIntelligenceError, match="INVALID_REQUEST_IDENTITY"):
        build_prompt(request, pack)


def test_marker_match_survives_live_display_reflow():
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    marker = f"NEXUS_REQUEST_SHA256={request['request_sha256']}"
    reflowed = prompt.replace("`required`", "required").replace("\\n", " ").rstrip() + "\n顯示更多"
    assert prompt != reflowed
    assert marker in reflowed
    transport = OpenCLIExternalIntelligenceTransport(executable="opencli")
    assert transport._prompt_matches(reflowed, prompt) is True


def test_marker_match_rejects_different_request():
    request, pack = request_and_pack()
    other_request, _ = request_and_pack()
    other_request = build_request(normalize_intake(record(item_id="999")), pack)
    prompt = build_prompt(request, pack)
    other_prompt = build_prompt(other_request, pack)
    transport = OpenCLIExternalIntelligenceTransport(executable="opencli")
    assert transport._prompt_matches(other_prompt, prompt) is False


def test_marker_match_rejects_no_marker():
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    transport = OpenCLIExternalIntelligenceTransport(executable="opencli")
    assert transport._prompt_matches("no marker here", prompt) is False


def test_reconcile_history_window_is_bounded_by_default():
    transport = OpenCLIExternalIntelligenceTransport(executable="opencli")
    assert transport.history_limit == 5
    assert transport._history_argv()[3:5] == ["--limit", "5"]


def test_timeout_reconcile_same_marker_two_conversations_returns_outcome_unknown(monkeypatch):
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    ask_seen = []

    class Fake(TimeoutReconcileFake):
        def __init__(self, args, **kwargs):
            super().__init__(args, **kwargs)
            if args[2] == "ask":
                ask_seen.append(args)

        def _history_rows(self):
            return [
                {"Index": 1, "Id": "conv-a", "Title": "t", "Url": "u"},
                {"Index": 2, "Id": "conv-b", "Title": "t", "Url": "u"},
            ]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": prompt,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            raise AssertionError("stable detail must not be reached for multiple matches")

    monkeypatch.setattr(subprocess, "Popen", Fake)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "OPENCLI_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert len(ask_seen) == 1


def test_timeout_reconcile_zero_marker_matches_returns_outcome_unknown(monkeypatch):
    request, pack = request_and_pack()
    prompt = build_prompt(request, pack)
    ask_seen = []

    class Fake(TimeoutReconcileFake):
        def __init__(self, args, **kwargs):
            super().__init__(args, **kwargs)
            if args[2] == "ask":
                ask_seen.append(args)

        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-other", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": "reflowed unrelated prompt 顯示更多",
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            raise AssertionError("stable detail must not be reached for zero matches")

    monkeypatch.setattr(subprocess, "Popen", Fake)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "OPENCLI_OUTCOME_UNKNOWN"
    assert result.outcome_unknown is True
    assert len(ask_seen) == 1


def test_timeout_reconcile_marker_unique_stable_valid_envelope_completes(tmp_path, monkeypatch):
    request, pack = request_and_pack()
    valid = json.dumps(envelope_for(request))
    prompt = build_prompt(request, pack)
    ask_seen = []

    class Fake(TimeoutReconcileFake):
        def __init__(self, args, **kwargs):
            super().__init__(args, **kwargs)
            if args[2] == "ask":
                ask_seen.append(args)

        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-match", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            reflowed = (
                prompt.replace("`required`", "required").replace("\\n", " ").rstrip() + "\n顯示更多"
            )
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": reflowed,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            return [{"Role": "Assistant", "Text": valid, "Generating": False, "StableSeconds": 6}]

    monkeypatch.setattr(subprocess, "Popen", Fake)
    store = ExternalIntelligenceStore(tmp_path)
    sidecar = ExternalIntelligenceSidecar(
        transport=OpenCLIExternalIntelligenceTransport(executable="opencli"), store=store
    )
    result = sidecar.analyze(record(), sources())
    assert result["status"] == "COMPLETED"
    assert result["transport_status"] == "INTELLIGENCE_COMPLETED"
    assert len(ask_seen) == 1
    request, _ = request_and_pack()
    assert (tmp_path / "envelopes" / f"{request['request_sha256']}.json").exists()
    assert (tmp_path / "receipts" / f"{request['request_sha256']}.json").exists()


def test_timeout_reconcile_marker_unique_malformed_envelope_rejected(tmp_path, monkeypatch):
    request, pack = request_and_pack()
    malformed = json.dumps({"schema": ENVELOPE_SCHEMA, "binding": request["identity"], "goal": "x"})
    prompt = build_prompt(request, pack)
    ask_seen = []

    class Fake(TimeoutReconcileFake):
        def __init__(self, args, **kwargs):
            super().__init__(args, **kwargs)
            if args[2] == "ask":
                ask_seen.append(args)

        def _history_rows(self):
            return [{"Index": 1, "Id": "conv-match", "Title": "t", "Url": "u"}]

        def _scan_detail(self, conversation_id):
            return [
                {
                    "Index": 1,
                    "Role": "User",
                    "Text": prompt,
                    "Generating": False,
                    "StableSeconds": 0,
                }
            ]

        def _stable_detail(self):
            return [
                {"Role": "Assistant", "Text": malformed, "Generating": False, "StableSeconds": 6}
            ]

    monkeypatch.setattr(subprocess, "Popen", Fake)
    store = ExternalIntelligenceStore(tmp_path)
    sidecar = ExternalIntelligenceSidecar(
        transport=OpenCLIExternalIntelligenceTransport(executable="opencli"), store=store
    )
    with pytest.raises(ExternalIntelligenceError, match="INTELLIGENCE_PARSE_FAILED"):
        sidecar.analyze(record(), sources())
    assert len(ask_seen) == 1
    request, _ = request_and_pack()
    assert not (tmp_path / "envelopes" / f"{request['request_sha256']}.json").exists()
    assert not (tmp_path / "receipts" / f"{request['request_sha256']}.json").exists()


def test_normal_ask_path_with_marker_unchanged(monkeypatch):
    request, pack = request_and_pack()
    stable = json.dumps(envelope_for(request))
    prompt = build_prompt(request, pack)
    calls = []

    class FakeProcess:
        def __init__(self, args, **kwargs):
            self.args = args
            self.returncode = 0
            self.pid = 4321
            self.stdout = None
            self.stderr = None
            calls.append(args)

        def communicate(self, timeout=None):
            if self.args[2] == "ask":
                return json.dumps([
                    {"conversationId": "conv-1", "response": "ask-snapshot-invalid"}
                ]), ""
            return json.dumps([
                {"Role": "Assistant", "Text": stable, "Generating": False, "StableSeconds": 6}
            ]), ""

    monkeypatch.setattr(subprocess, "Popen", FakeProcess)
    result = OpenCLIExternalIntelligenceTransport(executable="opencli").invoke(prompt)
    assert result.status == "INTELLIGENCE_COMPLETED"
    assert result.raw == stable
    assert result.conversation_id == "conv-1"
    assert [call[2] for call in calls] == ["ask", "detail"]
