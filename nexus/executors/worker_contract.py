"""Provider-neutral contract for governed self-hosted workers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Protocol, Any


SUPPORTED_WORKER_PROVIDERS = ("codex", "gemini", "agy", "opencode", "mimo", "ollama")


class WorkerOutcome(str, Enum):
    PROVEN = "PROVEN"
    INCOMPLETE = "INCOMPLETE"
    FAILED = "FAILED"


@dataclass(frozen=True)
class WorkerPreflight:
    provider: str
    executable: Optional[str]
    executable_available: bool
    authorized: bool
    implementation_status: str
    ready: bool
    reason: str


@dataclass(frozen=True)
class WorkerExecutionReceipt:
    provider: str
    task_id: str
    target_worktree: str
    worker_status: str
    outcome: str
    exit_code: Optional[int]
    executable_identity: str
    argv: tuple[str, ...]
    stdout_sha256: str
    stderr_sha256: str
    wall_time_ms: int
    process_group_id: Optional[int]
    process_group_killed: bool
    timed_out: bool
    provider_calls: int
    evidence_complete: bool
    commit_created: bool
    merge_performed: bool
    push_performed: bool
    failure_reason: Optional[str] = None


class WorkerProviderUnavailable(RuntimeError):
    """Raised when a provider is known but cannot be invoked safely."""


class WorkerAdapter(Protocol):
    provider: str

    def preflight(self) -> WorkerPreflight:
        ...

    def invoke(
        self,
        contract: Any,
        lease: Any,
        *,
        prompt: str,
        **options: Any,
    ) -> WorkerExecutionReceipt:
        ...
