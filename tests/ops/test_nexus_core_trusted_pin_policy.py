from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "scripts" / "ci" / "nexus_core_trusted_pin_policy.py"
SPEC = importlib.util.spec_from_file_location("nexus_core_trusted_pin_policy", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def _workflow(pin: str, *, extra: str = "") -> bytes:
    return (
        "name: Nexus Core issue completion\n"
        "jobs:\n"
        "  verify:\n"
        "    env:\n"
        f"      NEXUS_CORE_TOOL_PIN: {pin}\n"
        "    steps:\n"
        "      - run: echo trusted\n"
        f"{extra}"
    ).encode("utf-8")


def test_unchanged_workflow_passes() -> None:
    pin = "1" * 40
    doc = _workflow(pin)

    result = policy.validate_pin_update(doc, doc)

    assert result == {
        "schema": "nexus.core.trusted_pin_policy.v1",
        "status": "PASS",
        "change_kind": "UNCHANGED",
        "base_pin": pin,
        "candidate_pin": pin,
    }


def test_exact_pin_only_update_passes() -> None:
    old_pin = "1" * 40
    new_pin = "2" * 40

    result = policy.validate_pin_update(
        _workflow(old_pin),
        _workflow(new_pin),
    )

    assert result["change_kind"] == "PIN_ONLY"
    assert result["base_pin"] == old_pin
    assert result["candidate_pin"] == new_pin


@pytest.mark.parametrize(
    "candidate",
    [
        _workflow("2" * 40, extra="      - run: echo candidate-owned-change\n"),
        _workflow("2" * 40).replace(b"echo trusted", b"echo bypass"),
        _workflow("2" * 40).replace(b"  verify:", b"  verify-renamed:"),
    ],
)
def test_non_pin_workflow_changes_fail_closed(candidate: bytes) -> None:
    with pytest.raises(
        policy.PinPolicyError,
        match="NEXUS_CORE_WORKFLOW_CHANGE_NOT_PIN_ONLY",
    ):
        policy.validate_pin_update(_workflow("1" * 40), candidate)


def test_second_pin_field_fails_closed() -> None:
    candidate = _workflow("2" * 40) + b"      NEXUS_CORE_TOOL_PIN: " + b"3" * 40 + b"\n"

    with pytest.raises(
        policy.PinPolicyError,
        match="NEXUS_CORE_PIN_FIELD_COUNT_INVALID:2",
    ):
        policy.validate_pin_update(_workflow("1" * 40), candidate)


@pytest.mark.parametrize(
    "bad_line",
    [
        "      NEXUS_CORE_TOOL_PIN: not-a-sha\n",
        "      NEXUS_CORE_TOOL_PIN: ABCDEF0123456789ABCDEF0123456789ABCDEF01\n",
        "      OTHER_FIELD: " + "2" * 40 + "\n",
    ],
)
def test_malformed_or_missing_pin_fails_closed(bad_line: str) -> None:
    candidate = (
        "name: Nexus Core issue completion\n"
        "jobs:\n"
        "  verify:\n"
        "    env:\n" + bad_line + "    steps:\n"
        "      - run: echo trusted\n"
    ).encode("utf-8")

    with pytest.raises(policy.PinPolicyError, match="NEXUS_CORE_PIN_FIELD_COUNT_INVALID"):
        policy.validate_pin_update(_workflow("1" * 40), candidate)


def test_committed_workflow_uses_single_canonical_pin_field_and_policy() -> None:
    workflow = (
        REPO_ROOT / ".github" / "workflows" / "nexus-core-issue-completion.yml"
    ).read_bytes()

    pin, _normalized = policy._pin_and_normalized(workflow)

    assert len(pin) == 40
    text = workflow.decode("utf-8")
    assert "scripts/ci/nexus_core_trusted_pin_policy.py" in text
    assert "steps.trusted-core.outputs.core_pin" in text
    assert "merge-base --is-ancestor" in text


def test_committed_workflow_force_binds_exact_pr_base_ref() -> None:
    workflow = (REPO_ROOT / ".github" / "workflows" / "nexus-core-issue-completion.yml").read_text(
        encoding="utf-8"
    )

    forced = (
        "git fetch --no-tags origin "
        '"+${{ github.event.pull_request.base.sha }}:'
        'refs/remotes/origin/${{ github.event.pull_request.base.ref }}"'
    )
    unforced = (
        "git fetch --no-tags origin "
        '"${{ github.event.pull_request.base.sha }}:'
        'refs/remotes/origin/${{ github.event.pull_request.base.ref }}"'
    )

    assert forced in workflow
    assert unforced not in workflow
