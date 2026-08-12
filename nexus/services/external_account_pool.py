"""Provider-neutral request-scoped account leases for external providers.

This module owns account binding semantics only. Provider adapters remain
responsible for credential storage, provider error classification, and route
selection. Public leases expose only a non-secret alias hash and immutable
execution binding data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Mapping, Optional, Sequence
import uuid


class AccountFailureKind(str, Enum):
    """Provider-neutral failure taxonomy for account failover decisions."""

    AUTH_OR_SESSION_INVALID = "AUTH_OR_SESSION_INVALID"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REFRESH_FAILED = "TOKEN_REFRESH_FAILED"
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED"
    RATE_LIMITED = "RATE_LIMITED"
    ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"
    ACCOUNT_DISABLED = "ACCOUNT_DISABLED"

    MODEL_OR_TASK_ERROR = "MODEL_OR_TASK_ERROR"
    SYNTAX_OR_IMPLEMENTATION_ERROR = "SYNTAX_OR_IMPLEMENTATION_ERROR"
    VERIFIER_FAILED = "VERIFIER_FAILED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    PERMISSION_OR_SCOPE_ERROR = "PERMISSION_OR_SCOPE_ERROR"
    UNKNOWN = "UNKNOWN"


_ROTATION_ELIGIBLE_FAILURES = frozenset(
    {
        AccountFailureKind.AUTH_OR_SESSION_INVALID,
        AccountFailureKind.TOKEN_EXPIRED,
        AccountFailureKind.TOKEN_REFRESH_FAILED,
        AccountFailureKind.QUOTA_EXHAUSTED,
        AccountFailureKind.RATE_LIMITED,
        AccountFailureKind.ACCOUNT_UNAVAILABLE,
        AccountFailureKind.ACCOUNT_DISABLED,
    }
)


def is_rotation_eligible(failure_kind: AccountFailureKind) -> bool:
    """Return whether a structured provider failure may rotate an account."""

    return failure_kind in _ROTATION_ELIGIBLE_FAILURES


class ExternalAccountPoolError(RuntimeError):
    """Base exception for provider-neutral account-pool operations."""


class ExternalAccountPoolExhaustedError(ExternalAccountPoolError):
    """Raised when no usable account remains in the provider pool."""


class InvalidAccountLeaseError(ExternalAccountPoolError):
    """Raised when a lease does not match an active pool binding."""


@dataclass(frozen=True)
class AccountLease:
    """Immutable request-scoped binding exposed to one consumer."""

    lease_id: str
    provider: str
    consumer_id: str
    account_alias_hash: str
    execution_env: Mapping[str, str] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "execution_env",
            MappingProxyType(dict(self.execution_env)),
        )


@dataclass
class InternalAccountRecord:
    """Opaque provider-local account state consumed by the neutral lease pool.

    ``internal_id`` is never exposed through :class:`AccountLease`. Provider
    adapters supply the alias hash and non-secret execution binding data.
    """

    internal_id: str
    alias_hash: str
    execution_env: Mapping[str, str]
    is_available: bool = True
    active_lease_ids: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.execution_env = MappingProxyType(dict(self.execution_env))

    @property
    def load(self) -> int:
        return len(self.active_lease_ids)


class ExternalAccountPool:
    """Request-scoped lease pool for exactly one already-selected provider."""

    def __init__(
        self,
        provider: str,
        accounts: Optional[Sequence[InternalAccountRecord]] = None,
    ) -> None:
        provider_key = str(provider).strip()
        if not provider_key:
            raise ValueError("provider must be non-empty")
        self.provider = provider_key
        self._accounts: dict[str, InternalAccountRecord] = {}
        self._lease_to_account_id: dict[str, str] = {}
        self._active_leases: dict[str, AccountLease] = {}

        for account in accounts or ():
            self.register_account(account)

    def register_account(self, account: InternalAccountRecord) -> None:
        """Register one provider-owned account record without exposing aliases."""

        if account.internal_id in self._accounts:
            raise ValueError(f"duplicate account internal_id: {account.internal_id}")
        self._accounts[account.internal_id] = account

    def acquire(self, consumer_id: str) -> AccountLease:
        """Acquire a lease from the least-loaded available account."""

        available = [account for account in self._accounts.values() if account.is_available]
        if not available:
            raise ExternalAccountPoolExhaustedError(
                f"EXTERNAL_ACCOUNT_POOL_EXHAUSTED:{self.provider}"
            )

        account = min(available, key=lambda candidate: candidate.load)
        lease_id = f"lease_{uuid.uuid4().hex}"
        lease = AccountLease(
            lease_id=lease_id,
            provider=self.provider,
            consumer_id=str(consumer_id),
            account_alias_hash=account.alias_hash,
            execution_env=account.execution_env,
        )
        account.active_lease_ids.add(lease_id)
        self._lease_to_account_id[lease_id] = account.internal_id
        self._active_leases[lease_id] = lease
        return lease

    def _require_active_lease(self, lease: AccountLease) -> str:
        active = self._active_leases.get(lease.lease_id)
        if active != lease:
            raise InvalidAccountLeaseError(
                f"INVALID_ACCOUNT_LEASE:{lease.lease_id}"
            )
        try:
            return self._lease_to_account_id[lease.lease_id]
        except KeyError as exc:
            raise InvalidAccountLeaseError(
                f"INVALID_ACCOUNT_LEASE:{lease.lease_id}"
            ) from exc

    def release(self, lease: AccountLease) -> None:
        """Release only the supplied lease; unrelated bindings remain intact."""

        account_id = self._require_active_lease(lease)
        self._active_leases.pop(lease.lease_id, None)
        self._lease_to_account_id.pop(lease.lease_id, None)
        account = self._accounts[account_id]
        account.active_lease_ids.discard(lease.lease_id)

    def report_failure(
        self,
        lease: AccountLease,
        failure_kind: AccountFailureKind,
    ) -> Optional[AccountLease]:
        """Rotate one failed binding when the structured failure permits it.

        Provider-specific adapters classify raw provider errors before calling
        this method. Non-eligible failures leave the active lease untouched and
        return ``None``. Eligible account failures mark the failed internal
        account unavailable, release only this lease, and reacquire a
        replacement for the same consumer. Exhaustion fails closed.
        """

        account_id = self._require_active_lease(lease)
        if not is_rotation_eligible(failure_kind):
            return None

        self._accounts[account_id].is_available = False
        consumer_id = lease.consumer_id
        self.release(lease)
        return self.acquire(consumer_id)
