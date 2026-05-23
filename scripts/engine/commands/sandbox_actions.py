from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from scripts.engine.commands.exception_translation import NexusCliActionError


class SandboxRunnerLike(Protocol):
    def run_task(self, task: str) -> Mapping[str, Any]:
        ...


SandboxRunnerFactory = Callable[[Path], SandboxRunnerLike]


@dataclass(frozen=True)
class SandboxRunResult:
    task: str
    success: bool
    raw_result: dict[str, Any]


def _default_runner_factory(repo_root: Path) -> SandboxRunnerLike:
    from nexus.engine.sandbox_runner import SandboxRunner

    return SandboxRunner(repo_root)


def run_sandbox_task(
    repo_root: str | Path,
    task: str,
    *,
    runner_factory: SandboxRunnerFactory | None = None,
) -> SandboxRunResult:
    root = Path(repo_root)
    runner = (runner_factory or _default_runner_factory)(root)
    run_task = getattr(runner, "run_task", None)
    if not callable(run_task):
        raise NexusCliActionError("Sandbox runner does not expose run_task.", exit_code=1)

    raw_result = dict(run_task(task))
    return SandboxRunResult(
        task=task,
        success=bool(raw_result.get("success")),
        raw_result=raw_result,
    )


def render_sandbox_run_result(result: SandboxRunResult) -> list[str]:
    return [f"🏗️ [Sandbox] Execution finished. Success: {result.success}"]
