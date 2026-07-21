from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

from nexus.services.product_capability_closure import (
    BLOCKED_DEPENDENCY,
    EVIDENCE_INCOMPLETE,
    EXECUTION_FAILED,
    LIVE_EXECUTED_PASS,
    POLICY_SKIP_VERIFIED,
    PRODUCT_CAPABILITIES,
    VERIFIER_FAILED,
    summarize_origin_matrix,
    expected_resolution_type,
    verify_product_capability_resolution,
)
from nexus.services.capability_registry import coverage_counts_from_receipt


def _hash_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_record(
    capability: str = "codeintel",
    *,
    origin: str = "online",
    tmp_path: Path | None = None,
) -> dict[str, object]:
    resolution = expected_resolution_type(origin, capability)
    evidence_payload = {"capability": capability, "effect": "observed"}
    effect_payload = {"effect_type": "workspace_fingerprint", "value": "fp-1"}
    receipt_payload = {
        "capability": capability,
        "origin": origin,
        "run_id": f"run-{origin}-{capability}",
    }
    verifier_evidence = {"command": "pytest -q", "exit_code": 0}
    verifier_artifact = {"status": "VERIFIED", "capability": capability}
    task_id = "task-1"
    plan_id = "plan-1"
    rev_id = "rev-1"
    upstream_sha = _hash_payload({"root": "upstream"})
    run_root = tmp_path if tmp_path is not None else Path("/tmp/evidence-run-root")
    run_root.mkdir(parents=True, exist_ok=True)
    evidence_path = run_root / f"{capability}.json"
    evidence_path.write_text(json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")))
    evidence_physical_sha = hashlib.sha256(evidence_path.read_bytes()).hexdigest()
    evidence_json_sha = _hash_payload(evidence_payload)

    request_path = run_root / f"{capability}_request.json"
    request_path.write_text(json.dumps({"request": capability}, sort_keys=True, separators=(",", ":")))
    stderr_path = run_root / f"{capability}_stderr.txt"
    stderr_path.write_text("")
    evidence_refs_list: list[dict[str, object]] = [
        {
            "path": str(request_path),
            "sha256": _hash_payload({"request": capability}),
            "json_sha256": _hash_payload({"request": capability}),
            "content_kind": "json",
            "kind": "request",
            "payload": {"request": capability},
        },
        {
            "path": str(evidence_path),
            "sha256": evidence_physical_sha,
            "json_sha256": evidence_json_sha,
            "content_kind": "json",
            "kind": "stdout",
            "payload": evidence_payload,
        },
        {
            "path": str(stderr_path),
            "sha256": hashlib.sha256(b"").hexdigest(),
            "content_kind": "raw_bytes",
            "kind": "stderr",
        },
    ]

    record: dict[str, object] = {
        "task_id": task_id,
        "planner_decision_id": plan_id,
        "workspace_revision": rev_id,
        "upstream_receipt_sha256": upstream_sha,
        "execution_class": "provider_native",
        "provider_observation": "executed",
        "capability": capability,
        "origin": origin,
        "resolution_type": resolution,
        "planner_selected": True,
        "trigger_condition_met": True,
        "invoked": True,
        "skipped": False,
        "status": "INVOKED",
        "gate_passed": True,
        "physical_callable": "nexus.core.capability_executor_registry:codeintel",
        "provider": "production",
        "evidence_mode": "live_runtime",
        "run_root": str(run_root),
        "evidence_refs": evidence_refs_list,
        "observable_effect": {
            "effect_type": "workspace_fingerprint",
            "artifact_hash": _hash_payload(effect_payload),
            "artifact_payload": effect_payload,
        },
        "receipt_hash": _hash_payload(receipt_payload),
        "receipt_payload": receipt_payload,
        "receipt_hash_verified": True,
        "structured_evidence_verified": True,
        "verifier": {
            "invoked": True,
            "passed": True,
            "evidence_hash": _hash_payload(verifier_evidence),
            "evidence_payload": verifier_evidence,
            "artifact_hash": _hash_payload(verifier_artifact),
            "artifact_payload": verifier_artifact,
        },
        "public_claim_allowed": False,
        "route_surface_changed": False,
    }
    if origin == "local":
        record["task_id"] = task_id
        record["planner_decision_id"] = plan_id
        record["workspace_revision"] = rev_id

        packet_payload = {"packet_id": "pkt-1", "capability": capability, "task_id": task_id}
        packet_hash = _hash_payload(packet_payload)
        fragment_payload = {"fragment_id": "frag-1", "packet_hash": packet_hash}
        fragment_hash = _hash_payload(fragment_payload)
        final_prompt_payload = {"prompt_id": "prompt-1", "fragment_hash": fragment_hash}
        final_prompt_hash = _hash_payload(final_prompt_payload)
        online_candidate_payload = {"candidate_id": "cand-1", "final_prompt_hash": final_prompt_hash}
        online_candidate_hash = _hash_payload(online_candidate_payload)
        applied_artifact_payload = {"artifact_id": "art-1", "online_candidate_hash": online_candidate_hash}
        applied_artifact_hash = _hash_payload(applied_artifact_payload)
        verifier_artifact_payload = {"verifier_id": "ver-1", "applied_artifact_hash": applied_artifact_hash}
        verifier_artifact_hash = _hash_payload(verifier_artifact_payload)
        final_receipt_payload = {"receipt_id": "rec-1", "verifier_artifact_hash": verifier_artifact_hash}
        final_receipt_hash = _hash_payload(final_receipt_payload)

        record["assist_lineage"] = {
            "task_id": task_id,
            "planner_decision_id": plan_id,
            "workspace_revision": rev_id,
            "packet_payload": packet_payload,
            "packet_hash": packet_hash,
            "fragment_payload": fragment_payload,
            "fragment_hash": fragment_hash,
            "final_prompt_payload": final_prompt_payload,
            "final_prompt_hash": final_prompt_hash,
            "online_candidate_payload": online_candidate_payload,
            "online_candidate_hash": online_candidate_hash,
            "applied_artifact_payload": applied_artifact_payload,
            "applied_artifact_hash": applied_artifact_hash,
            "verifier_artifact_payload": verifier_artifact_payload,
            "verifier_artifact_hash": verifier_artifact_hash,
            "final_receipt_payload": final_receipt_payload,
            "final_receipt_hash": final_receipt_hash,
        }
    if capability in {"local_model_executor", "repair_loop"}:
        record["resolution_type"] = (
            "ONLINE_TO_LOCAL_GOVERNED_BRIDGE" if origin == "online" else "LOCAL_NATIVE"
        )
        record["local_execution"] = {
            "provider_family": "ollama",
            "model_name": "qwen-local",
            "model_called": True,
            "output_delivered": True,
            "candidate_isolated": True,
            "candidate_hash": "8" * 64,
            "selected_hash": "9" * 64,
            "applied_hash": "9" * 64,
            "network_invoked": False,
            "loop_entered": capability == "repair_loop",
        }
        if origin == "local":
            record.pop("assist_lineage", None)
    return record


def test_product_denominator_is_frozen_to_34_contract_nodes() -> None:
    assert len(PRODUCT_CAPABILITIES) == 34
    assert PRODUCT_CAPABILITIES == (
        "acceptance_check",
        "architecture_scout",
        "artifact_gate",
        "asi_constraint_extractor",
        "bdd_acceptance_skill",
        "belief",
        "benchmark",
        "claim_gate",
        "codeintel",
        "delivery_gate",
        "drone",
        "file_lock",
        "forecast_gate",
        "formal_report",
        "harness_preflight_sensor",
        "jit_validation",
        "lancedb",
        "learn_mode",
        "learn_phase_slo",
        "local_model_executor",
        "memory",
        "mempalace_gate",
        "meta_opt",
        "plan_quality_gate",
        "pregate",
        "prompt_compression",
        "repair_loop",
        "research",
        "sandbox",
        "semantic_failure_sensor",
        "semantic_searcher",
        "stress_test",
        "ultra_review",
        "xray",
    )


def test_valid_resolution_is_live_executed_pass(tmp_path: Path) -> None:
    verdict = verify_product_capability_resolution(_valid_record(tmp_path=tmp_path))
    assert verdict["status"] == LIVE_EXECUTED_PASS
    assert verdict["live_pass"] is True
    assert verdict["missing_evidence_reasons"] == []


def test_policy_skip_never_counts_as_live_pass(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.update(
        skipped=True,
        status="SKIPPED_POLICY_NOT_TRIGGERED",
        invoked=False,
        live_closure_pass=True,
    )
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == POLICY_SKIP_VERIFIED
    assert verdict["live_pass"] is False


def test_selected_not_executed_is_blocked(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.update(status="SELECTED_NOT_EXECUTED", invoked=False)
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == BLOCKED_DEPENDENCY
    assert "selected_not_executed" in verdict["missing_evidence_reasons"]


def test_blocker_evidence_never_counts_as_pass(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record["evidence_refs"] = ["blocker:online_not_invoked"]
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == BLOCKED_DEPENDENCY
    assert "blocker_evidence_present" in verdict["missing_evidence_reasons"]


def test_receipt_hash_mismatch_and_fixture_transport_fail_closed(tmp_path: Path) -> None:
    mismatch = _valid_record(tmp_path=tmp_path)
    mismatch["receipt_hash"] = "0" * 64
    verdict = verify_product_capability_resolution(mismatch)
    assert verdict["status"] == EVIDENCE_INCOMPLETE
    assert "receipt_hash_not_verified" in verdict["missing_evidence_reasons"]

    fixture = _valid_record(tmp_path=tmp_path)
    fixture.update(
        provider="fixture",
        physical_callable="test:fixture_invoker",
        live_closure_pass=True,
    )
    verdict = verify_product_capability_resolution(fixture)
    assert verdict["status"] == EVIDENCE_INCOMPLETE
    assert "synthetic_or_fixture_execution" in verdict["missing_evidence_reasons"]


def test_verifier_failure_is_not_terminal_pass(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record["verifier"] = {
        "invoked": True,
        "passed": False,
        "evidence_hash": "d" * 64,
        "artifact_hash": "e" * 64,
    }
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == VERIFIER_FAILED
    assert verdict["live_pass"] is False


def test_local_model_requires_real_call_isolation_hash_match_and_verifier(tmp_path: Path) -> None:
    record = _valid_record("local_model_executor", origin="local", tmp_path=tmp_path)
    local = dict(record["local_execution"])
    local["model_called"] = False
    record["local_execution"] = local
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == EXECUTION_FAILED
    assert "local_model_not_called" in verdict["missing_evidence_reasons"]

    record = _valid_record("repair_loop", origin="online", tmp_path=tmp_path)
    local = dict(record["local_execution"])
    local["applied_hash"] = "0" * 64
    record["local_execution"] = local
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == EVIDENCE_INCOMPLETE
    assert "selected_applied_hash_mismatch" in verdict["missing_evidence_reasons"]


def test_consumed_assist_without_result_lineage_is_not_attribution_pass(tmp_path: Path) -> None:
    record = _valid_record(origin="local", tmp_path=tmp_path)
    record["assist_lineage"] = {
        "packet_hash": "1" * 64,
        "consumption_status": "consumed",
    }
    verdict = verify_product_capability_resolution(record)
    assert verdict["status"] == EVIDENCE_INCOMPLETE
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_68_entry_matrix_requires_one_live_pass_per_origin_capability(tmp_path: Path) -> None:
    records = [
        _valid_record(capability, origin=origin, tmp_path=tmp_path)
        for origin in ("online", "local")
        for capability in PRODUCT_CAPABILITIES
    ]
    summary = summarize_origin_matrix(records)
    assert summary["online_origin_pass"] == 34
    assert summary["local_origin_pass"] == 34
    assert summary["matrix_pass"] == 68
    assert summary["matrix_total"] == 68
    assert summary["complete"] is True
    assert summary["receipt_hash_verified_count"] == 68
    assert summary["synthetic_live_pass"] == 0
    assert summary["public_claim_allowed"] is False

    bad = deepcopy(records)
    bad[0].update(
        skipped=True,
        invoked=False,
        status="SKIPPED_POLICY_NOT_TRIGGERED",
    )
    summary = summarize_origin_matrix(bad)
    assert summary["complete"] is False
    assert summary["matrix_pass"] == 67
    assert summary["policy_skip_pass_count"] == 0
    assert summary["policy_skip_count"] == 1

    bad_hash = deepcopy(records)
    bad_hash[0]["receipt_hash"] = "0" * 64
    summary = summarize_origin_matrix(bad_hash)
    assert summary["complete"] is False
    assert summary["receipt_hash_verified_count"] == 67


def test_runtime_coverage_keeps_surface_coverage_but_rejects_all_skip_live_green() -> None:
    receipt = {
        "context_trace": {"selected_capabilities": ["architecture_scout"]},
        "capabilities": [
            {
                "name": "architecture_scout",
                "status": "SKIPPED",
                "skipped": True,
                "skip_reason": "SKIPPED_POLICY_NOT_TRIGGERED",
                "evidence_refs": ["policy:architecture_scout:skip"],
                "gate_passed": True,
            }
        ],
    }
    coverage = coverage_counts_from_receipt(receipt)
    assert coverage["surface_coverage_ok"] is True
    assert coverage["real_execution_coverage_ok"] is False
    assert coverage["verified_outcome_ok"] is False
    assert coverage["strict_closure_complete"] is False
    assert coverage["policy_skip_count"] == 1
    assert coverage["live_execution_pass_count"] == 0


def test_runtime_coverage_rejects_blocker_and_fixture_evidence_as_live_execution() -> None:
    receipt = {
        "context_trace": {
            "selected_capabilities": ["artifact_gate", "sandbox", "xray"],
        },
        "capabilities": [
            {
                "name": "artifact_gate",
                "status": "INVOKED",
                "invoked": True,
                "gate_passed": True,
                "physical_callable": "online_nexus_context.evaluate_postflight_gate",
                "evidence_refs": [{"type": "blocker", "ref": "missing_artifact_lineage"}],
            },
            {
                "name": "sandbox",
                "status": "INVOKED",
                "invoked": True,
                "gate_passed": True,
                "physical_callable": "nexus.core.capability_executor_registry:sandbox",
                "evidence_refs": ["fixture:sandbox"],
            },
            {
                "name": "xray",
                "status": "INVOKED",
                "invoked": True,
                "gate_passed": True,
                "physical_callable": "",
                "evidence_refs": ["production:xray"],
            },
        ],
    }
    coverage = coverage_counts_from_receipt(receipt)
    assert coverage["surface_coverage_ok"] is True
    assert coverage["real_execution_coverage_ok"] is False
    assert coverage["verified_outcome_ok"] is False
    assert coverage["strict_closure_complete"] is False
    assert coverage["blocker_evidence_count"] == 1
    assert coverage["synthetic_execution_count"] == 1
    assert coverage["missing_physical_callable_count"] == 1
    assert coverage["live_execution_pass_count"] == 0


def test_p0_negative_control_1_tampered_packet_hash(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["assist_lineage"]["packet_hash"] = "0" * 64
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_p0_negative_control_2_missing_payload(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["assist_lineage"].pop("fragment_payload", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_p0_negative_control_3_task_id_mismatch(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["task_id"] = "task-alpha"
    record["assist_lineage"]["task_id"] = "task-beta"
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_p0_negative_control_4_planner_decision_id_mismatch(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["planner_decision_id"] = "plan-111"
    record["assist_lineage"]["planner_decision_id"] = "plan-222"
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_p0_negative_control_5_workspace_revision_mismatch(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["workspace_revision"] = "rev-old"
    record["assist_lineage"]["workspace_revision"] = "rev-new"
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_p0_negative_control_6_broken_edge_packet_to_fragment(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["assist_lineage"]["fragment_payload"] = {"fragment_id": "frag-1", "packet_hash": "f" * 64}
    record["assist_lineage"]["fragment_hash"] = _hash_payload(record["assist_lineage"]["fragment_payload"])
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_p0_negative_control_7_broken_edge_fragment_to_prompt(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["assist_lineage"]["final_prompt_payload"] = {"prompt_id": "prompt-1", "fragment_hash": "f" * 64}
    record["assist_lineage"]["final_prompt_hash"] = _hash_payload(record["assist_lineage"]["final_prompt_payload"])
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_p0_negative_control_8_broken_edge_candidate_to_artifact(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["assist_lineage"]["applied_artifact_payload"] = {"artifact_id": "art-1", "candidate_hash": "f" * 64}
    record["assist_lineage"]["applied_artifact_hash"] = _hash_payload(record["assist_lineage"]["applied_artifact_payload"])
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


def test_p0_negative_control_9_broken_edge_verifier_to_receipt(tmp_path: Path) -> None:
    record = _valid_record("codeintel", origin="local", tmp_path=tmp_path)
    record["assist_lineage"]["final_receipt_payload"] = {"receipt_id": "rec-1", "verifier_hash": "f" * 64}
    record["assist_lineage"]["final_receipt_hash"] = _hash_payload(record["assist_lineage"]["final_receipt_payload"])
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "assist_lineage_incomplete" in verdict["missing_evidence_reasons"]


# ─── B1R: v2 evidence contract negative controls ──────────────────────────────

def test_b1r_missing_execution_class_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.pop("execution_class", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "execution_class_missing" in verdict["missing_evidence_reasons"]


def test_b1r_unknown_execution_class_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record["execution_class"] = "made_up_class"
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "execution_class_unknown" in verdict["missing_evidence_reasons"][0]


def test_b1r_missing_provider_observation_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.pop("provider_observation", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "provider_observation_missing" in verdict["missing_evidence_reasons"]


def test_b1r_executed_claim_on_deterministic_runtime_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record["execution_class"] = "deterministic_runtime"
    record["provider_observation"] = "executed"
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "non_provider_native_cannot_claim_executed" in verdict["missing_evidence_reasons"][0]


def test_b1r_missing_evidence_mode_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.pop("evidence_mode", None)
    record.pop("run_root", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "evidence_mode_unknown" in verdict["missing_evidence_reasons"]


def test_b1r_legacy_live_provider_mode_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record["evidence_mode"] = "live_provider"
    record.pop("run_root", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "evidence_mode_unknown" in verdict["missing_evidence_reasons"]


def test_b1r_missing_run_root_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.pop("run_root", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "run_root_missing_for_live_runtime" in verdict["missing_evidence_reasons"]


def test_b1r_missing_workspace_revision_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.pop("workspace_revision", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "workspace_revision_missing" in verdict["missing_evidence_reasons"]


def test_b1r_missing_upstream_receipt_sha256_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.pop("upstream_receipt_sha256", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "upstream_receipt_sha256_missing" in verdict["missing_evidence_reasons"]


def test_b1r_missing_origin_capability_binding_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record.pop("origin", None)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "invalid_origin" in verdict["missing_evidence_reasons"]


def test_b1r_physical_stdout_mutation_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    refs = record["evidence_refs"]
    assert isinstance(refs, list) and len(refs) > 0
    ref = refs[0]
    assert isinstance(ref, dict)
    ev_path = Path(str(ref["path"]))
    original = ev_path.read_bytes()
    ev_path.write_bytes(b"MUTATED_" + original)
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False
    assert "physical_sha256_mismatch" in verdict["missing_evidence_reasons"]


def test_b1r_physical_stderr_missing_fails_closed(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    record["execution_class"] = "stage_owned"
    record["provider_observation"] = "consumed"
    # Remove stderr ref, keep request + stdout
    refs = [r for r in (record["evidence_refs"] or []) if isinstance(r, dict) and r.get("kind") != "stderr"]
    record["evidence_refs"] = refs
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is False, verdict["missing_evidence_reasons"]
    reasons = verdict["missing_evidence_reasons"]
    assert any("missing_physical_stderr_ref" in r for r in reasons)
    assert not any("missing_physical_request_ref" in r for r in reasons)


def test_b1r_raw_non_json_stdout_accepted_and_hash_verified(tmp_path: Path) -> None:
    record = _valid_record(tmp_path=tmp_path)
    raw_content = b"raw binary output not valid json"
    raw_path = tmp_path / "raw_stdout.bin"
    raw_path.write_bytes(raw_content)
    raw_physical_sha = hashlib.sha256(raw_content).hexdigest()
    request_ref = {"path": str(tmp_path / "req.json"), "sha256": _hash_payload({"r": 1}), "content_kind": "json", "kind": "request", "payload": {"r": 1}}
    (tmp_path / "req.json").write_text(json.dumps({"r": 1}, sort_keys=True, separators=(",", ":")))
    stderr_ref = {"path": str(tmp_path / "err.txt"), "sha256": hashlib.sha256(b"").hexdigest(), "content_kind": "raw_bytes", "kind": "stderr"}
    (tmp_path / "err.txt").write_text("")
    stdout_ref = {"path": str(raw_path), "sha256": raw_physical_sha, "content_kind": "raw_bytes", "kind": "stdout"}
    record["evidence_refs"] = [request_ref, stdout_ref, stderr_ref]
    verdict = verify_product_capability_resolution(record)
    assert verdict["live_pass"] is True, verdict["missing_evidence_reasons"]
