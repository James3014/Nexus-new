import json
from pathlib import Path


def test_automation_contract_does_not_activate_primary_cohort_in_wave1() -> None:
    payload = json.loads(
        Path("docs/research/hybrid_replication_v2/AUTOMATION_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["status"] == "SOURCE_READY_PENDING_LIVE_ACTIVATION"
    assert payload["activation"]["activation_state"] is None
    assert payload["activation"]["t_auto"] is None
    assert payload["activation"]["exclusion_set_sha256"] is None
    assert payload["activation"]["required_status"] == "AUTOMATIC_CAPTURE_READY"
    assert payload["activation"]["wave1_must_not_create_primary_scoring_boundary"] is True
    assert (
        payload["superseded_provisional_boundary"]["status"]
        == "PRE_AUTOMATION_PROVISIONAL_GENERATION"
    )
    assert payload["superseded_provisional_boundary"]["primary_scoring_allowed"] is False
    assert len(payload["candidate_repositories"]) == 8
    assert payload["frozen_incumbent"]["dm1_top_probability_min"] == 0.7
    assert payload["frozen_incumbent"]["dm1_margin_min"] == 0.3


def test_contract_records_task_granular_fail_close_and_campaign_exclusions() -> None:
    payload = json.loads(
        Path("docs/research/hybrid_replication_v2/AUTOMATION_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    assert payload["fail_close"] == {
        "protocol_loss_granularity": "TASK",
        "task_disposition": "PROTOCOL_EVIDENCE_ONLY_DO_NOT_COUNT",
        "generation_reset_only_for": [
            "EXECUTION_IDENTITY_DRIFT",
            "SYSTEMATIC_DEFECT_AFFECTING_ALL_TASKS",
        ],
        "generation_reset_for_single_task_protocol_loss": False,
    }
    exclusions = payload["primary_cohort_exclusions"]
    assert exclusions["campaign_task_keys"] == [
        "James3014/Nexus-new#1216",
        "James3014/Nexus-new#1196",
    ]
    assert exclusions["campaign_markers"] == [
        "#1216",
        "#1196",
        "NEXUS-HYBRID-REPLICATION",
        "hybrid replication",
        "hybrid-replication",
        "hybrid_replication",
    ]
    assert exclusions["disposition"] == "CAMPAIGN_META_WORK_EXCLUDED"
    assert payload["activation_manifest"] == {
        "schema": "nexus.hybrid_replication.activation_manifest.v1",
        "script": "scripts/ops/hybrid_replication_activation.py",
    }


def test_contract_campaign_exclusions_match_pipeline_policy_defaults() -> None:
    from nexus.research.hybrid_replication_pipeline import IssueAdmissionPolicy

    payload = json.loads(
        Path("docs/research/hybrid_replication_v2/AUTOMATION_CONTRACT.json").read_text(
            encoding="utf-8"
        )
    )
    defaults = IssueAdmissionPolicy.__dataclass_fields__
    exclusions = payload["primary_cohort_exclusions"]
    assert tuple(exclusions["campaign_task_keys"]) == defaults["campaign_task_keys"].default
    assert tuple(exclusions["campaign_markers"]) == defaults["campaign_markers"].default


def test_daemon_is_fail_closed_on_capture_and_admission_gaps() -> None:
    text = Path("scripts/ops/hybrid_replication_daemon.py").read_text(encoding="utf-8")
    assert "return 3" in text
    assert "return 4" in text
    assert '"missing_capture"' in text
    assert '"missing_admission"' in text
    assert "ExternalFrozenStackRunner" in text
    assert "ExternalGroundTruthResolver" in text
    assert text.index("advance_report = advance_all") < text.rindex(
        'if ingest_report["missing_capture"]'
    )
    assert "except Exception as exc" in text
    assert '"failures": failures' in text
    assert 'if advance_report["failures"]' in text
    assert '"task_key": task_key' in text
