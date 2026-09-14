from __future__ import annotations

import pytest

from scripts.ops import trusted_deletion_anchor as anchor


def _install_transition_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter(anchor.TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION[1])
    monkeypatch.setattr(anchor, "_sha", lambda _value: next(values))


def test_pr960_transition_is_exact_one_use_and_chained_from_pr910(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert anchor.TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION[0] == 960
    assert (
        anchor.TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION[1][:2]
        == anchor.TRUSTED_PR910_DEPENDENCY_SNAPSHOT_TRANSITION[1][2:]
    )
    _install_transition_hashes(monkeypatch)
    anchor._validate_trusted_dependency_contract(
        b"trusted-pyproject",
        b"head-pyproject",
        b"trusted-lock",
        b"head-lock",
        pull_request_number=960,
        head_product_init_is_regular=True,
    )


def test_pr960_transition_rejects_reuse_under_another_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_transition_hashes(monkeypatch)
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        anchor._validate_trusted_dependency_contract(
            b"trusted-pyproject",
            b"head-pyproject",
            b"trusted-lock",
            b"head-lock",
            pull_request_number=961,
            head_product_init_is_regular=True,
        )


def test_trusted_runtime_identity_is_wave2_merge() -> None:
    runtime = next(
        record
        for record in anchor.TRUSTED_EXTERNAL_RUNTIME_PACKAGES
        if record[0] == "nexus-runtime"
    )
    assert runtime[3] == "b48fbd7abe96041bffcea31fa31fa90e78582f02"
