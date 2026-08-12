"""Tests for provider-neutral request-scoped external account leases."""

from __future__ import annotations

from dataclasses import fields

import pytest

from nexus.services.external_account_pool import (
    AccountFailureKind,
    AccountLease,
    ExternalAccountPool,
    ExternalAccountPoolExhaustedError,
    InternalAccountRecord,
    InvalidAccountLeaseError,
    is_rotation_eligible,
)


def _account(internal_id: str, alias_hash: str) -> InternalAccountRecord:
    return InternalAccountRecord(
        internal_id=internal_id,
        alias_hash=alias_hash,
        execution_env={"HOME": f"/tmp/{internal_id}"},
    )


def _pool() -> ExternalAccountPool:
    return ExternalAccountPool(
        provider="test_provider",
        accounts=(
            _account("account-a", "hash-a"),
            _account("account-b", "hash-b"),
            _account("account-c", "hash-c"),
        ),
    )


def test_public_lease_exposes_no_raw_account_identity() -> None:
    lease = _pool().acquire("consumer-a")

    assert {item.name for item in fields(AccountLease)} == {
        "lease_id",
        "provider",
        "consumer_id",
        "account_alias_hash",
        "execution_env",
    }
    assert not hasattr(lease, "alias")
    assert not hasattr(lease, "raw_alias")
    assert not hasattr(lease, "internal_id")
    assert lease.account_alias_hash == "hash-a"


def test_execution_env_is_defensively_copied_and_read_only() -> None:
    source_env = {"HOME": "/tmp/account-a"}
    account = InternalAccountRecord(
        internal_id="account-a",
        alias_hash="hash-a",
        execution_env=source_env,
    )
    pool = ExternalAccountPool("test_provider", [account])
    lease = pool.acquire("consumer-a")

    source_env["HOME"] = "/tmp/mutated"
    assert lease.execution_env["HOME"] == "/tmp/account-a"
    with pytest.raises(TypeError):
        lease.execution_env["HOME"] = "/tmp/direct-mutation"  # type: ignore[index]


def test_two_consumers_hold_independent_leases() -> None:
    pool = _pool()
    first = pool.acquire("consumer-a")
    second = pool.acquire("consumer-b")

    assert first.lease_id != second.lease_id
    assert first.consumer_id == "consumer-a"
    assert second.consumer_id == "consumer-b"
    assert first.account_alias_hash == "hash-a"
    assert second.account_alias_hash == "hash-b"


def test_release_does_not_mutate_other_binding() -> None:
    pool = _pool()
    first = pool.acquire("consumer-a")
    second = pool.acquire("consumer-b")

    pool.release(first)

    assert second.account_alias_hash == "hash-b"
    assert pool.report_failure(second, AccountFailureKind.UNKNOWN) is None
    pool.release(second)
    with pytest.raises(InvalidAccountLeaseError):
        pool.release(first)


@pytest.mark.parametrize(
    "failure_kind",
    [
        AccountFailureKind.AUTH_OR_SESSION_INVALID,
        AccountFailureKind.TOKEN_EXPIRED,
        AccountFailureKind.TOKEN_REFRESH_FAILED,
        AccountFailureKind.QUOTA_EXHAUSTED,
        AccountFailureKind.RATE_LIMITED,
        AccountFailureKind.ACCOUNT_UNAVAILABLE,
        AccountFailureKind.ACCOUNT_DISABLED,
    ],
)
def test_rotation_eligible_failure_kinds(failure_kind: AccountFailureKind) -> None:
    assert is_rotation_eligible(failure_kind) is True


@pytest.mark.parametrize(
    "failure_kind",
    [
        AccountFailureKind.MODEL_OR_TASK_ERROR,
        AccountFailureKind.SYNTAX_OR_IMPLEMENTATION_ERROR,
        AccountFailureKind.VERIFIER_FAILED,
        AccountFailureKind.CANCELLED,
        AccountFailureKind.TIMEOUT,
        AccountFailureKind.PERMISSION_OR_SCOPE_ERROR,
        AccountFailureKind.UNKNOWN,
    ],
)
def test_non_rotation_failure_kinds(failure_kind: AccountFailureKind) -> None:
    assert is_rotation_eligible(failure_kind) is False


def test_eligible_failure_rotates_only_failed_binding() -> None:
    pool = _pool()
    failed = pool.acquire("consumer-a")
    unaffected = pool.acquire("consumer-b")

    replacement = pool.report_failure(failed, AccountFailureKind.QUOTA_EXHAUSTED)

    assert replacement is not None
    assert replacement.consumer_id == "consumer-a"
    assert replacement.account_alias_hash == "hash-c"
    assert replacement.lease_id != failed.lease_id
    assert unaffected.account_alias_hash == "hash-b"
    assert pool.report_failure(unaffected, AccountFailureKind.UNKNOWN) is None
    pool.release(unaffected)


def test_noneligible_failure_keeps_original_lease_active() -> None:
    pool = _pool()
    lease = pool.acquire("consumer-a")

    assert (
        pool.report_failure(
            lease,
            AccountFailureKind.SYNTAX_OR_IMPLEMENTATION_ERROR,
        )
        is None
    )
    pool.release(lease)


def test_exhaustion_fails_closed_after_eligible_failure() -> None:
    pool = ExternalAccountPool(
        "test_provider",
        [_account("account-a", "hash-a")],
    )
    lease = pool.acquire("consumer-a")

    with pytest.raises(
        ExternalAccountPoolExhaustedError,
        match="EXTERNAL_ACCOUNT_POOL_EXHAUSTED:test_provider",
    ):
        pool.report_failure(lease, AccountFailureKind.AUTH_OR_SESSION_INVALID)

    with pytest.raises(ExternalAccountPoolExhaustedError):
        pool.acquire("consumer-b")


def test_empty_or_unknown_pool_fails_closed() -> None:
    pool = ExternalAccountPool("test_provider")

    with pytest.raises(ExternalAccountPoolExhaustedError):
        pool.acquire("consumer-a")
