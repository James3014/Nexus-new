from pathlib import Path
import sys

from nexus.delivery.gate import evaluate_completion
from nexus.delivery.models import CompletionRequest
from nexus.delivery.models import CompletionStatus
from nexus.delivery.models import DeliveryProfile
from nexus.delivery.models import TaskLevel


def test_completion_gate_marks_feature_verified_when_all_commands_pass(
    tmp_path: Path,
) -> None:
    request = CompletionRequest(
        task_name="feature-pass",
        task_level=TaskLevel.FEATURE,
        verification_commands=[
            f"{sys.executable} -c \"print('ok-1')\"",
            f"{sys.executable} -c \"print('ok-2')\"",
        ],
        cwd=tmp_path,
    )

    result = evaluate_completion(request)

    assert result.status == CompletionStatus.VERIFIED
    assert result.failed_commands == 0
    assert result.passed_commands == 2


def test_completion_gate_marks_delivery_ready_when_artifact_exists(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "report.json"
    artifact.write_text("{}", encoding="utf-8")
    request = CompletionRequest(
        task_name="delivery-pass",
        task_level=TaskLevel.DELIVERY,
        verification_commands=[
            f"{sys.executable} -c \"print('ok-1')\"",
            f"{sys.executable} -c \"print('ok-2')\"",
        ],
        artifact_paths=[artifact],
        cwd=tmp_path,
    )

    result = evaluate_completion(request)

    assert result.status == CompletionStatus.DELIVERY_READY
    assert result.missing_artifacts == []


def test_completion_gate_stays_partially_verified_when_a_command_fails(
    tmp_path: Path,
) -> None:
    request = CompletionRequest(
        task_name="mixed-pass",
        task_level=TaskLevel.FEATURE,
        verification_commands=[
            f"{sys.executable} -c \"print('ok')\"",
            f"{sys.executable} -c \"import sys; sys.exit(2)\"",
        ],
        cwd=tmp_path,
    )

    result = evaluate_completion(request)

    assert result.status == CompletionStatus.PARTIALLY_VERIFIED
    assert result.failed_commands == 1


def test_completion_gate_requires_artifact_before_delivery_ready(
    tmp_path: Path,
) -> None:
    missing_artifact = tmp_path / "missing.json"
    request = CompletionRequest(
        task_name="delivery-missing-artifact",
        task_level=TaskLevel.DELIVERY,
        verification_commands=[
            f"{sys.executable} -c \"print('ok-1')\"",
            f"{sys.executable} -c \"print('ok-2')\"",
        ],
        artifact_paths=[missing_artifact],
        cwd=tmp_path,
    )

    result = evaluate_completion(request)

    assert result.status == CompletionStatus.VERIFIED
    assert result.missing_artifacts == [missing_artifact]


def test_completion_gate_blocks_live_profile_without_human_approval(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "live.json"
    artifact.write_text("{}", encoding="utf-8")
    request = CompletionRequest(
        task_name="live-without-approval",
        task_level=TaskLevel.FEATURE,
        delivery_profile=DeliveryProfile.LIVE_API,
        verification_commands=[f"{sys.executable} -c \"print('ok')\""],
        artifact_paths=[artifact],
        cwd=tmp_path,
    )

    result = evaluate_completion(request)

    assert result.gate_passed is False
    assert result.status == CompletionStatus.PARTIALLY_VERIFIED
    assert result.policy_failures == ["live_delivery_requires_human_approval"]


def test_completion_gate_allows_live_profile_with_approval_and_artifact(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "live.json"
    artifact.write_text("{}", encoding="utf-8")
    request = CompletionRequest(
        task_name="live-with-approval",
        task_level=TaskLevel.FEATURE,
        delivery_profile=DeliveryProfile.LIVE_BROWSER,
        verification_commands=[
            f"{sys.executable} -c \"print('ok-1')\"",
            f"{sys.executable} -c \"print('ok-2')\"",
        ],
        artifact_paths=[artifact],
        human_approval_refs=["approved-by:james"],
        cwd=tmp_path,
    )

    result = evaluate_completion(request)

    assert result.gate_passed is True
    assert result.delivery_profile == DeliveryProfile.LIVE_BROWSER
    assert result.policy_failures == []
