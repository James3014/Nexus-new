from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from nexus.research.hybrid_replication_pipeline import (
    ADMISSION_MARKER,
    CAPTURE_MARKER,
    CONTRACT_DELTA_MARKER,
    READINESS_CONTROL_ACTIVATION_STATE,
    READINESS_CONTROL_DISPOSITION,
    AdmissionReceipt,
    AutomaticReplicationController,
    AutomaticReplicationStore,
    FrozenStackOutcome,
    GroundTruthEvidence,
    IssueAdmissionPolicy,
    RawRouteResult,
    RouteClassification,
    TaskSnapshot,
    build_admission_comment,
    build_capture_comment,
    build_contract_delta_comment,
    classify_opened_issue,
    parse_admission_comment,
    parse_capture_comment,
    parse_contract_delta_comment,
)


def test_capture_comment_round_trip_preserves_pre_execution_contract() -> None:
    snapshot = TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=1300,
        created_at="2026-10-01T00:00:00Z",
        captured_at="2026-10-01T00:00:03Z",
        issue_updated_at="2026-10-01T00:00:00Z",
        title="Bounded natural task",
        body="Implement the bounded change in nexus/services/example.py",
        pre_implementation_revision="1" * 40,
        default_branch="main",
        source_event_id="run:100:attempt:1",
    )

    comment = build_capture_comment(snapshot)

    assert CAPTURE_MARKER in comment
    recovered = parse_capture_comment(comment)
    assert recovered == snapshot
    assert recovered.contract_sha256
    assert recovered.capture_sha256


def _foreign_gzip_capture_comment(snapshot: TaskSnapshot) -> tuple[str, dict[str, object]]:
    payload = snapshot.to_capture_payload()
    compressed = bytearray(base64.b64decode(str(payload["body_gzip_base64"])))
    assert len(compressed) >= 10
    compressed[9] = 3 if compressed[9] != 3 else 19
    payload["body_gzip_base64"] = base64.b64encode(bytes(compressed)).decode("ascii")
    unsigned = dict(payload)
    unsigned.pop("capture_sha256")
    payload["capture_sha256"] = hashlib.sha256(
        json.dumps(
            unsigned,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    comment = (
        f"{CAPTURE_MARKER}\n"
        "Authority: `RESEARCH_OBSERVATION_ONLY / NO_ENGINEERING_AUTHORITY`\n\n"
        "```json\n" + json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n```"
    )
    return comment, payload


def test_capture_parser_preserves_foreign_gzip_envelope_identity() -> None:
    snapshot = _snapshot(1301)
    comment, payload = _foreign_gzip_capture_comment(snapshot)

    recovered = parse_capture_comment(comment)

    assert recovered.capture_sha256 == payload["capture_sha256"]
    assert recovered.contract_sha256 == payload["contract_sha256"]
    assert recovered.body == snapshot.body
    assert recovered.to_capture_payload() == payload


def test_controller_preserves_foreign_capture_identity_through_store(tmp_path: Path) -> None:
    original = _snapshot(1302)
    comment, payload = _foreign_gzip_capture_comment(original)
    snapshot = parse_capture_comment(comment)
    store = AutomaticReplicationStore(tmp_path)
    store.capture(snapshot, admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")
    observed: dict[str, str] = {}

    def stack_runner(recovered: TaskSnapshot) -> FrozenStackOutcome:
        observed["capture_sha256"] = recovered.capture_sha256
        return _c_outcome()

    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="4" * 64,
        stack_runner=stack_runner,
        terminal_resolver=lambda _: None,
        clock=lambda: "2026-10-02T00:00:00Z",
    )

    result = controller.advance(snapshot.task_key)

    assert result["phase"] == "RAW_SEALED"
    assert observed["capture_sha256"] == payload["capture_sha256"]
    assert result["capture_sha256"] == payload["capture_sha256"]


def _snapshot(issue: int = 1300) -> TaskSnapshot:
    return TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=issue,
        created_at="2026-10-01T00:00:00Z",
        captured_at="2026-10-01T00:00:03Z",
        issue_updated_at="2026-10-01T00:00:00Z",
        title="Bounded natural task",
        body="Implement the bounded change",
        pre_implementation_revision="1" * 40,
        default_branch="main",
        source_event_id=f"run:{issue}:attempt:1",
    )


def test_state_machine_requires_raw_seal_before_ground_truth(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot()
    store.capture(snapshot, admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")

    route = RouteClassification(
        stratum="C",
        reason="strong semantic work under frozen contract",
        capture_sha256=snapshot.capture_sha256,
        frozen_policy_sha256="2" * 64,
        decided_at="2026-10-01T00:01:00Z",
    )
    store.freeze_route(snapshot.task_key, route)

    with pytest.raises(ValueError, match="raw_seal_required_before_ground_truth"):
        store.bind_ground_truth(
            snapshot.task_key,
            GroundTruthEvidence(
                terminal_state="PASS",
                terminal_at="2026-10-01T00:30:00Z",
                evidence_refs=("pr:1301",),
            ),
        )

    raw = RawRouteResult.create(
        route="C",
        provider="openai",
        requested_model="gpt-5.6-luna",
        resolved_model="gpt-5.6-luna",
        model_call_count=1,
        input_tokens=120,
        uncached_input_tokens=100,
        output_tokens=30,
        wall_time_seconds=4.2,
        failures=(),
        retries=0,
        fallbacks=(),
        raw_response={"decision": "implementation-guidance"},
    )
    seal = store.seal_raw(snapshot.task_key, raw)
    assert seal["raw_sha256"]

    ground = store.bind_ground_truth(
        snapshot.task_key,
        GroundTruthEvidence(
            terminal_state="PASS",
            terminal_at="2026-10-01T00:30:00Z",
            evidence_refs=("pr:1301",),
        ),
    )
    assert ground["phase"] == "GROUND_TRUTH_BOUND"

    with pytest.raises(FileExistsError):
        store.seal_raw(snapshot.task_key, raw)


def test_watchdog_reports_missing_capture_without_backfilling(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    store.capture(_snapshot(1300), admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")

    report = store.reconcile_expected_work_items([
        ("James3014/Nexus-new", 1300),
        ("James3014/devspace", 401),
    ])

    assert report["status"] == "INTAKE_GAP"
    assert report["missing"] == ["James3014/devspace#401"]
    assert store.load_task("James3014/devspace#401") is None


def test_duplicate_capture_is_idempotent_but_conflicting_capture_fails(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot()
    first = store.capture(snapshot, admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")
    second = store.capture(snapshot, admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")
    assert first == second

    conflicting = TaskSnapshot.create(
        repository=snapshot.repository,
        issue_number=snapshot.issue_number,
        created_at=snapshot.created_at,
        captured_at="2026-10-01T00:00:04Z",
        issue_updated_at=snapshot.issue_updated_at,
        title=snapshot.title,
        body=snapshot.body + " changed",
        pre_implementation_revision=snapshot.pre_implementation_revision,
        default_branch=snapshot.default_branch,
        source_event_id="run:conflict",
    )
    with pytest.raises(ValueError, match="capture_identity_conflict"):
        store.capture(conflicting, admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")


def test_opened_issue_is_admitted_automatically_at_event_time() -> None:
    snapshot = _snapshot(1302)
    policy = IssueAdmissionPolicy(
        prospective_boundary="2026-10-01T00:00:00Z",
        experiment_control_task="James3014/Nexus-new#1216",
        candidate_repositories=(
            "James3014/Nexus-new",
            "James3014/devspace",
        ),
        excluded_task_keys=(),
    )
    result = classify_opened_issue(snapshot, policy)
    assert result == "ADMITTED_PRIMARY_FRESH_TASK"


def test_cross_repo_issue_is_preserved_but_not_primary_admitted() -> None:
    snapshot = TaskSnapshot.create(
        repository="James3014/Nexus-new",
        issue_number=1303,
        created_at="2026-10-01T00:00:00Z",
        captured_at="2026-10-01T00:00:03Z",
        issue_updated_at="2026-10-01T00:00:00Z",
        title="Coordinate Nexus-new and devspace mutation",
        body="Change James3014/Nexus-new and James3014/devspace together.",
        pre_implementation_revision="1" * 40,
        default_branch="main",
        source_event_id="run:1303",
    )
    policy = IssueAdmissionPolicy(
        prospective_boundary="2026-10-01T00:00:00Z",
        experiment_control_task="James3014/Nexus-new#1216",
        candidate_repositories=(
            "James3014/Nexus-new",
            "James3014/devspace",
        ),
        excluded_task_keys=(),
    )
    assert classify_opened_issue(snapshot, policy) == "CROSS_REPO_SCOPE_GAP"


def test_issue_edit_is_contract_delta_not_snapshot_rewrite() -> None:
    snapshot = _snapshot(1304)
    comment = build_contract_delta_comment(
        snapshot=snapshot,
        edited_at="2026-10-01T00:10:00Z",
        issue_updated_at="2026-10-01T00:10:00Z",
        title=snapshot.title,
        body=snapshot.body + " plus a bounded clarification",
        source_event_id="run:1304:edit:1",
    )
    assert CONTRACT_DELTA_MARKER in comment
    assert snapshot.capture_sha256 in comment
    recovered = parse_contract_delta_comment(comment)
    assert recovered["original_capture_sha256"] == snapshot.capture_sha256
    assert recovered["body"].endswith("plus a bounded clarification")


def test_frozen_stack_outcome_enforces_a_b_c_contract() -> None:
    a = FrozenStackOutcome(
        stratum="A",
        deterministic_receipt={"status": "PASS"},
        candidate_packet=None,
        jev_raw_response=None,
        dm1_decision=None,
        strong_online_raw_response=None,
        raw_result=RawRouteResult.create(
            route="A",
            provider="deterministic",
            requested_model="",
            resolved_model="",
            model_call_count=0,
            input_tokens=0,
            uncached_input_tokens=0,
            output_tokens=0,
            wall_time_seconds=0.1,
            failures=(),
            retries=0,
            fallbacks=(),
            raw_response={"status": "PASS"},
        ),
    )
    a.validate()

    b = FrozenStackOutcome(
        stratum="B",
        deterministic_receipt={"status": "INSUFFICIENT"},
        candidate_packet={"candidate_ids": ["x", "y"]},
        jev_raw_response={"choice": "x", "probabilities": {"x": 0.82, "y": 0.18}},
        dm1_decision={"choice": "x", "top_probability": 0.82, "margin": 0.64},
        strong_online_raw_response=None,
        raw_result=RawRouteResult.create(
            route="B",
            provider="jev",
            requested_model="jev-latest",
            resolved_model="jev-1.13.0",
            model_call_count=1,
            input_tokens=80,
            uncached_input_tokens=80,
            output_tokens=8,
            wall_time_seconds=0.04,
            failures=(),
            retries=0,
            fallbacks=(),
            raw_response={"choice": "x"},
        ),
    )
    b.validate()

    c = FrozenStackOutcome(
        stratum="C",
        deterministic_receipt={"status": "INSUFFICIENT"},
        candidate_packet=None,
        jev_raw_response=None,
        dm1_decision=None,
        strong_online_raw_response={"answer": "semantic result"},
        raw_result=RawRouteResult.create(
            route="C",
            provider="openai",
            requested_model="gpt-5.6-luna",
            resolved_model="gpt-5.6-luna",
            model_call_count=1,
            input_tokens=100,
            uncached_input_tokens=90,
            output_tokens=20,
            wall_time_seconds=2.0,
            failures=(),
            retries=0,
            fallbacks=(),
            raw_response={"answer": "semantic result"},
        ),
    )
    c.validate()


def test_low_margin_b_requires_strong_online_fallback() -> None:
    bad = FrozenStackOutcome(
        stratum="B",
        deterministic_receipt={"status": "INSUFFICIENT"},
        candidate_packet={"candidate_ids": ["x", "y"]},
        jev_raw_response={"choice": "x"},
        dm1_decision={"choice": "x", "top_probability": 0.69, "margin": 0.40},
        strong_online_raw_response=None,
        raw_result=RawRouteResult.create(
            route="B",
            provider="jev",
            requested_model="jev-latest",
            resolved_model="jev-1.13.0",
            model_call_count=1,
            input_tokens=80,
            uncached_input_tokens=80,
            output_tokens=8,
            wall_time_seconds=0.04,
            failures=(),
            retries=0,
            fallbacks=(),
            raw_response={"choice": "x"},
        ),
    )
    with pytest.raises(ValueError, match="b_fallback_required"):
        bad.validate()


def _c_outcome() -> FrozenStackOutcome:
    return FrozenStackOutcome(
        stratum="C",
        deterministic_receipt={"status": "INSUFFICIENT"},
        candidate_packet=None,
        jev_raw_response=None,
        dm1_decision=None,
        strong_online_raw_response={"answer": "semantic result"},
        raw_result=RawRouteResult.create(
            route="C",
            provider="openai",
            requested_model="gpt-5.6-luna",
            resolved_model="gpt-5.6-luna",
            model_call_count=1,
            input_tokens=100,
            uncached_input_tokens=90,
            output_tokens=20,
            wall_time_seconds=2.0,
            failures=(),
            retries=0,
            fallbacks=(),
            raw_response={"answer": "semantic result"},
        ),
    )


def test_controller_routes_and_seals_once_across_restart(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(1310)
    store.capture(snapshot, admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")
    calls = {"stack": 0}

    def stack_runner(_: TaskSnapshot) -> FrozenStackOutcome:
        calls["stack"] += 1
        return _c_outcome()

    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="4" * 64,
        stack_runner=stack_runner,
        terminal_resolver=lambda _: None,
        clock=lambda: "2026-10-01T00:02:00Z",
    )
    result = controller.advance(snapshot.task_key)
    assert result["phase"] == "RAW_SEALED"
    assert calls["stack"] == 1

    restarted = AutomaticReplicationController(
        store=AutomaticReplicationStore(tmp_path),
        frozen_policy_sha256="4" * 64,
        stack_runner=stack_runner,
        terminal_resolver=lambda _: None,
        clock=lambda: "2026-10-01T00:03:00Z",
    )
    result = restarted.advance(snapshot.task_key)
    assert result["phase"] == "RAW_SEALED"
    assert calls["stack"] == 1


def test_controller_joins_terminal_only_after_raw_seal(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(1311)
    store.capture(snapshot, admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")
    terminal = GroundTruthEvidence(
        terminal_state="PASS",
        terminal_at="2026-10-01T00:30:00Z",
        evidence_refs=("pr:1312", "verifier:pass"),
    )
    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="5" * 64,
        stack_runner=lambda _: _c_outcome(),
        terminal_resolver=lambda _: terminal,
        clock=lambda: "2026-10-01T00:02:00Z",
    )
    result = controller.advance(snapshot.task_key)
    assert result["phase"] == "SCORED"
    assert result["raw_seal"]["raw_sha256"]
    assert result["ground_truth"]["sha256"]
    assert result["score"]["sha256"]
    score_path = tmp_path / "tasks" / "James3014__Nexus-new--1311" / "score.json"
    score = json.loads(score_path.read_text(encoding="utf-8"))
    assert score["raw_sha256"] == result["raw_seal"]["raw_sha256"]
    assert score["ground_truth_sha256"] == result["ground_truth"]["sha256"]
    assert score["terminal_state"] == "PASS"
    assert score["quality"]["terminal_state"] == "PASS"
    assert score["quality"]["evidence_refs"] == ["pr:1312", "verifier:pass"]
    assert score["route"] == "C"


def test_admission_receipt_round_trip_is_bound_to_capture() -> None:
    snapshot = _snapshot(1313)
    receipt = AdmissionReceipt.create(
        snapshot=snapshot,
        disposition="ADMITTED_PRIMARY_FRESH_TASK",
        activation_boundary="2026-10-01T00:00:00Z",
        activation_state="AUTOMATIC_CAPTURE_READY",
        exclusion_set_sha256="6" * 64,
        issue_state_at_admission="open",
        implementation_pr_numbers=(),
        tracked_parent_issue_number=None,
        tracked_parent_created_at=None,
        admitted_at="2026-10-01T00:00:03Z",
    )
    comment = build_admission_comment(receipt)
    assert ADMISSION_MARKER in comment
    assert parse_admission_comment(comment) == receipt


def test_provisional_capture_can_promote_only_with_matching_admission(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(1314)
    state = store.capture(snapshot, admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE")
    assert state["phase"] == "CAPTURED_PROVISIONAL"

    receipt = AdmissionReceipt.create(
        snapshot=snapshot,
        disposition="ADMITTED_PRIMARY_FRESH_TASK",
        activation_boundary="2026-10-01T00:00:00Z",
        activation_state="AUTOMATIC_CAPTURE_READY",
        exclusion_set_sha256="6" * 64,
        issue_state_at_admission="open",
        implementation_pr_numbers=(),
        tracked_parent_issue_number=None,
        tracked_parent_created_at=None,
        admitted_at="2026-10-01T00:00:03Z",
    )
    promoted = store.apply_admission(receipt)
    assert promoted["phase"] == "ADMITTED"
    assert promoted["admission_receipt_sha256"] == receipt.receipt_sha256


def test_admission_requires_explicit_automatic_capture_ready() -> None:
    snapshot = _snapshot(1315)
    with pytest.raises(ValueError, match="automatic_capture_ready_required"):
        AdmissionReceipt.create(
            snapshot=snapshot,
            disposition="ADMITTED_PRIMARY_FRESH_TASK",
            activation_boundary="2026-10-01T00:00:00Z",
            activation_state="SOURCE_READY_PENDING_LIVE_ACTIVATION",
            exclusion_set_sha256="6" * 64,
            issue_state_at_admission="open",
            implementation_pr_numbers=(),
            tracked_parent_issue_number=None,
            tracked_parent_created_at=None,
            admitted_at="2026-10-01T00:00:03Z",
        )


def test_readiness_control_admission_is_explicitly_excluded_and_executable(
    tmp_path: Path,
) -> None:
    snapshot = _snapshot(1317)
    receipt = AdmissionReceipt.create(
        snapshot=snapshot,
        disposition=READINESS_CONTROL_DISPOSITION,
        activation_boundary=snapshot.captured_at,
        activation_state=READINESS_CONTROL_ACTIVATION_STATE,
        exclusion_set_sha256="6" * 64,
        issue_state_at_admission="open",
        implementation_pr_numbers=(),
        tracked_parent_issue_number=None,
        tracked_parent_created_at=None,
        admitted_at=snapshot.captured_at,
    )
    assert parse_admission_comment(build_admission_comment(receipt)) == receipt

    store = AutomaticReplicationStore(tmp_path)
    store.capture(snapshot, admission_disposition="PRE_AUTOMATION_PROVISIONAL_CAPTURE")
    promoted = store.apply_admission(receipt)
    assert promoted["phase"] == "ADMITTED"
    assert promoted["admission_disposition"] == READINESS_CONTROL_DISPOSITION

    controller = AutomaticReplicationController(
        store=store,
        frozen_policy_sha256="5" * 64,
        stack_runner=lambda _: _c_outcome(),
        terminal_resolver=lambda _: GroundTruthEvidence(
            terminal_state="PASS",
            terminal_at="2026-10-07T00:10:00Z",
            evidence_refs=("control:terminal",),
        ),
        clock=lambda: "2026-10-07T00:00:02Z",
    )
    assert controller.advance(snapshot.task_key)["phase"] == "SCORED"


def test_primary_admission_cannot_use_readiness_control_pending_state() -> None:
    snapshot = _snapshot(1318)
    with pytest.raises(ValueError, match="automatic_capture_ready_required"):
        AdmissionReceipt.create(
            snapshot=snapshot,
            disposition="ADMITTED_PRIMARY_FRESH_TASK",
            activation_boundary=snapshot.captured_at,
            activation_state=READINESS_CONTROL_ACTIVATION_STATE,
            exclusion_set_sha256="6" * 64,
            issue_state_at_admission="open",
            implementation_pr_numbers=(),
            tracked_parent_issue_number=None,
            tracked_parent_created_at=None,
            admitted_at=snapshot.captured_at,
        )


def test_existing_implementation_pr_blocks_prospective_admission() -> None:
    snapshot = _snapshot(1316)
    policy = IssueAdmissionPolicy(
        prospective_boundary="2026-10-01T00:00:00Z",
        experiment_control_task="James3014/Nexus-new#1216",
        candidate_repositories=("James3014/Nexus-new",),
    )
    assert (
        classify_opened_issue(
            snapshot,
            policy,
            issue_state_at_admission="open",
            implementation_pr_numbers=(1317,),
        )
        == "INTAKE_PROTOCOL_LOSS_IMPLEMENTATION_PRESENT"
    )


def test_terminal_issue_blocks_prospective_admission() -> None:
    snapshot = _snapshot(1318)
    policy = IssueAdmissionPolicy(
        prospective_boundary="2026-10-01T00:00:00Z",
        experiment_control_task="James3014/Nexus-new#1216",
        candidate_repositories=("James3014/Nexus-new",),
    )
    assert (
        classify_opened_issue(
            snapshot,
            policy,
            issue_state_at_admission="closed",
        )
        == "INTAKE_PROTOCOL_LOSS_TERMINAL_BEFORE_ADMISSION"
    )


def test_explicit_parent_created_before_boundary_is_not_reaged() -> None:
    snapshot = _snapshot(1319)
    policy = IssueAdmissionPolicy(
        prospective_boundary="2026-10-01T00:00:00Z",
        experiment_control_task="James3014/Nexus-new#1216",
        candidate_repositories=("James3014/Nexus-new",),
    )
    assert (
        classify_opened_issue(
            snapshot,
            policy,
            tracked_parent_created_at="2026-09-30T23:59:59Z",
        )
        == "EXCLUDE_PARENT_TASK_PRE_BOUNDARY"
    )


def test_ground_truth_details_are_sealed_with_terminal_identity(tmp_path: Path) -> None:
    store = AutomaticReplicationStore(tmp_path)
    snapshot = _snapshot(1320)
    store.capture(snapshot, admission_disposition="ADMITTED_PRIMARY_FRESH_TASK")
    store.freeze_route(
        snapshot.task_key,
        RouteClassification(
            stratum="C",
            reason="strong semantic work",
            capture_sha256=snapshot.capture_sha256,
            frozen_policy_sha256="7" * 64,
            decided_at="2026-10-01T00:01:00Z",
        ),
    )
    store.seal_raw(
        snapshot.task_key,
        RawRouteResult.create(
            route="C",
            provider="openai",
            requested_model="gpt-5.6-luna",
            resolved_model="gpt-5.6-luna",
            model_call_count=1,
            input_tokens=10,
            uncached_input_tokens=10,
            output_tokens=2,
            wall_time_seconds=0.5,
            failures=(),
            retries=0,
            fallbacks=(),
            raw_response={"summary": "bounded"},
        ),
    )
    state = store.bind_ground_truth(
        snapshot.task_key,
        GroundTruthEvidence(
            terminal_state="CLOSED_WITH_MERGED_PR",
            terminal_at="2026-10-01T00:30:00Z",
            evidence_refs=("pr:1321@" + "b" * 40,),
            details={
                "changed_files": ["nexus/example.py"],
                "checks": [{"name": "test", "state": "success"}],
            },
        ),
    )
    assert state["ground_truth"]["details"]["changed_files"] == ["nexus/example.py"]
