from __future__ import annotations

import pytest

import scripts.ops.trusted_deletion_anchor as trusted_anchor


def test_pr960_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION == (
        960,
        (
            "f4f3c2c390804e048d42aa30c447a64af1d079bf2881a93252a38a6674cfcf9f",
            "26e853cd712aaf96b188f4dc9f1e2e8feea3a0d8989fc321a84b28e8b6776b45",
            "2c2c1a9d9e2f12736fb3a33efbace9a7b264ca737c00e27ed37696dc5f560c34",
            "ec48fa0ea3dc4403c84d26dcf73a0f18b88292270c4dc519986b06a92835ce35",
        ),
    )


def _pr960_snapshot_fixture(monkeypatch: pytest.MonkeyPatch) -> list[bytes]:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )
    return values


def test_pr960_dependency_snapshot_transition_allows_exact_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _pr960_snapshot_fixture(monkeypatch)
    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=960,
        head_product_init_is_regular=True,
    )


@pytest.mark.parametrize("tampered_index", range(4))
def test_pr960_dependency_snapshot_transition_rejects_each_hash_tamper(
    monkeypatch: pytest.MonkeyPatch,
    tampered_index: int,
) -> None:
    values = _pr960_snapshot_fixture(monkeypatch)
    values[tampered_index] += b"tampered"
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=960,
            head_product_init_is_regular=True,
        )


@pytest.mark.parametrize("pull_request_number", [910, 959, 961])
def test_pr960_dependency_snapshot_transition_rejects_other_prs(
    monkeypatch: pytest.MonkeyPatch,
    pull_request_number: int,
) -> None:
    values = _pr960_snapshot_fixture(monkeypatch)
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=pull_request_number,
            head_product_init_is_regular=True,
        )


def test_pr960_dependency_snapshot_transition_preserves_product_file_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    values = _pr960_snapshot_fixture(monkeypatch)
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=960,
            head_product_init_is_regular=False,
        )
