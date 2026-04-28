from nexus.orchestrator.evidence_policy import build_temp_evidence_payload
from nexus.orchestrator.evidence_policy import code_impact_report_paths
from nexus.orchestrator.evidence_policy import derive_claim_bundle
from nexus.orchestrator.evidence_policy import has_code_impact_report
from nexus.orchestrator.evidence_policy import missing_pre_gate_requirements
from nexus.orchestrator.evidence_policy import task_requires_code_impact
from nexus.orchestrator.task_contract import Evidence
from nexus.orchestrator.task_contract import EvidenceRequirement
from nexus.orchestrator.task_contract import DeliveryProfile
from nexus.orchestrator.task_contract import Task


def _task() -> Task:
    return Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["docs/readme.md"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest", "nexus acceptance-check"],
    )


def test_missing_pre_gate_requirements_defers_acceptance_requirements():
    task = _task()
    assert missing_pre_gate_requirements(task) == [EvidenceRequirement.PYTEST]


def test_build_temp_evidence_payload_only_includes_pytest_artifacts():
    task = _task()
    task.add_evidence(Evidence(command="pytest -q tests/unit", exit_code=0, output_summary="3 passed"))
    task.add_evidence(Evidence(command="nexus acceptance-check", exit_code=0, output_summary="acceptance ok"))

    payload = build_temp_evidence_payload(task)

    assert payload["evidence_bundle"]["test_artifacts"] == ["3 passed"]
    assert payload["evidence_bundle"]["command_artifacts"] == [
        "pytest -q tests/unit",
        "nexus acceptance-check",
    ]


def test_derive_claim_bundle_stays_unverified_when_requirements_missing():
    task = _task()
    task.add_evidence(Evidence(command="pytest -q tests/unit", exit_code=0, output_summary="3 passed"))

    bundle = derive_claim_bundle(task, "Done", "diff --git a/file1.py b/file1.py")

    assert bundle["claim_state"] == "UNVERIFIED"
    assert bundle["confidence_level"] == "LOW"
    assert bundle["unmet_evidence_requirements"] == [EvidenceRequirement.ACCEPTANCE_CHECK]


def test_live_delivery_profile_human_approval_is_pre_gate_requirement():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        delivery_profile=DeliveryProfile.LIVE_BROWSER,
        allowed_files=["docs/readme.md"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest"],
    )
    task.add_evidence(Evidence(command="pytest -q tests/unit", exit_code=0, output_summary="3 passed"))

    assert missing_pre_gate_requirements(task) == [EvidenceRequirement.HUMAN_APPROVAL]


def test_code_change_requires_code_impact_before_delivery_gate():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["nexus/orchestrator/task_contract.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest"],
    )
    task.add_evidence(Evidence(command="pytest -q tests/nexus/orchestrator", exit_code=0, output_summary="3 passed"))

    assert task_requires_code_impact(task) is True
    assert missing_pre_gate_requirements(task) == [EvidenceRequirement.CODE_IMPACT]

    task.add_evidence(Evidence(command="nexus code:impact --files nexus/orchestrator/task_contract.py", exit_code=0, output_summary="impact ok"))
    assert missing_pre_gate_requirements(task) == [EvidenceRequirement.CODE_IMPACT]


def test_code_change_accepts_code_impact_report_artifact(tmp_path):
    report = tmp_path / "impact.json"
    report.write_text('{"schema_version":"codeintel-v1"}', encoding="utf-8")
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["nexus/orchestrator/task_contract.py"],
        done_criteria=["tests pass"],
        evidence_requirements=["pytest"],
    )
    task.add_evidence(Evidence(command="pytest -q tests/nexus/orchestrator", exit_code=0, output_summary="3 passed"))
    task.add_evidence(
        Evidence(
            command=f"nexus code impact --files nexus/orchestrator/task_contract.py --report-file {report}",
            exit_code=0,
            output_summary="impact ok",
        )
    )

    assert code_impact_report_paths(task) == [str(report)]
    assert has_code_impact_report(task) is True
    assert missing_pre_gate_requirements(task) == []


def test_doc_only_change_does_not_require_code_impact():
    task = Task(
        task_id="TASK-001",
        owner="Agent-1",
        allowed_files=["docs/readme.md"],
        done_criteria=["docs updated"],
        evidence_requirements=["pytest"],
    )
    task.add_evidence(Evidence(command="pytest -q tests/docs", exit_code=0, output_summary="3 passed"))

    assert task_requires_code_impact(task) is False
    assert missing_pre_gate_requirements(task) == []
