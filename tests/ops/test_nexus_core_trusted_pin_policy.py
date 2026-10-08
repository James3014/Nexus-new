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


def test_committed_workflow_uses_single_canonical_pin_across_two_job_gate() -> None:
    """Since nexus-core#116/#120 the gate is two jobs built from composite actions.

    The canonical pin is the 40-hex sha shared by every `uses: James3014/nexus-core/...@sha`
    line and every `nexus-certify-ref` input; trusted inputs (config, workflow) are read from
    the base ref by the tool itself, so no byte-compare "protect" step or PIN_ONLY policy
    step exists in the workflow any more.
    """
    import re

    text = (
        REPO_ROOT / ".github" / "workflows" / "nexus-core-issue-completion.yml"
    ).read_text(encoding="utf-8")

    uses = re.findall(
        r"uses:\s*James3014/nexus-core/\.github/actions/([A-Za-z0-9_-]+)@([0-9a-f]{40})", text
    )
    refs = re.findall(r'nexus-certify-ref:\s*"([0-9a-f]{40})"', text)
    assert {name for name, _ in uses} == {"issue-gate", "receipt-verify"}
    shas = {sha for _, sha in uses} | set(refs)
    assert len(shas) == 1 and len(refs) == 2, (uses, refs)
    assert "pull_request_target" in text
    assert "head.repo.fork == false" in text
    assert "id-token: write" in text
    assert "name: Nexus Core issue completion" in text
    assert "needs: run" in text
    for forbidden in ("uv sync", "uv build", "pip install", "NEXUS_CORE_TOOL_PIN"):
        assert forbidden not in text, forbidden


@pytest.mark.skip(
    reason="base-ref force binding moved into the James3014/nexus-core issue-gate composite "
    "action (nexus-core#116) and is covered by nexus-core's own tests"
)
def test_committed_workflow_force_binds_exact_pr_base_ref() -> None:  # pragma: no cover
    pass
