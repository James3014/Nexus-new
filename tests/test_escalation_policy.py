from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from nexus.core.escalation import EscalationPolicy, TaskMetadata, derive_task_metadata


def test_prefers_gemini_repair_on_early_rounds_for_internal_work():
    policy = EscalationPolicy()

    decision = policy.decide(
        attempt=1,
        task=TaskMetadata(language="python", task_scale="medium"),
        failure_summary="unit test still failing",
        repeated_failure=False,
    )

    assert decision.action == "gemini_repair"
    assert decision.actor == "gemini"
    assert decision.allow_codex_patch is False


def test_requests_felo_research_when_external_signal_is_strong():
    policy = EscalationPolicy()

    decision = policy.decide(
        attempt=2,
        task=TaskMetadata(
            language="python",
            task_scale="medium",
            has_external_dependency_signal=True,
            stacktrace_pattern="fastapi dependency override http 500",
        ),
        failure_summary="framework behavior unclear",
        repeated_failure=True,
    )

    assert decision.action == "felo_research"
    assert decision.actor == "felo"
    assert decision.allow_codex_patch is False


def test_escalates_to_codex_patch_after_threshold():
    policy = EscalationPolicy(codex_patch_threshold=3)

    decision = policy.decide(
        attempt=3,
        task=TaskMetadata(language="python", task_scale="large"),
        failure_summary="same failing assertion after multiple retries",
        repeated_failure=True,
    )

    assert decision.action == "codex_patch"
    assert decision.actor == "codex"
    assert decision.allow_codex_patch is True


def test_respects_docs_driven_metadata_without_loop_specific_state():
    policy = EscalationPolicy()

    decision = policy.decide(
        attempt=2,
        task=TaskMetadata(
            source_kind="docs",
            language="python",
            task_scale="large",
            is_new_feature=True,
            stacktrace_pattern="sdk protocol mismatch",
        ),
        failure_summary="third-party sdk behavior mismatch",
        repeated_failure=True,
    )

    assert decision.reason_codes
    assert "source_docs" in decision.reason_codes
    assert decision.action in {"felo_research", "gemini_repair", "codex_patch"}


def test_scores_phase_signal_higher_than_minor_context_signals():
    policy = EscalationPolicy()

    score = policy.score_task(
        phase="R",
        task=TaskMetadata(
            language="python",
            task_scale="small",
            is_new_feature=True,
            stacktrace_pattern="",
        ),
    )

    assert score["phase_weight"] > score["task_scale_weight"]
    assert score["phase_weight"] > score["new_feature_weight"]


def test_derives_docs_driven_metadata_from_files_and_diff():
    task = derive_task_metadata(
        ["docs/08_MIGRATION_RUNBOOK_V1_5_2_PLUS.md", "docs/15_MIGRATION_SAFETY_VALIDATOR_PLAN.md"],
        "add validator gatekeeper and external API fallback",
    )

    assert task.source_kind == "docs"
    assert task.has_external_dependency_signal is True


def test_derives_python_refactor_signal_from_code_diff():
    task = derive_task_metadata(
        ["scripts/core/context_hub.py", "scripts/codex_loop_brain.py"],
        "refactor extract repair strategy and rename helper",
    )

    assert task.language == "python"
    assert task.is_large_refactor is True
