from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Any, Protocol

from scripts.engine.commands.exception_translation import NexusCliActionError


class SandboxRunnerLike(Protocol):
    def run_task(
        self,
        task: str,
        *,
        command: list[str] | None,
        cwd: str | Path,
        timeout_sec: int,
        output_file: str | Path | None,
        cleanup: bool,
    ) -> Mapping[str, Any]:
        ...


SandboxRunnerFactory = Callable[[Path], SandboxRunnerLike]


@dataclass(frozen=True)
class SandboxRunResult:
    task: str
    success: bool
    raw_result: dict[str, Any]


def parse_sandbox_command(command: str | list[str] | tuple[str, ...] | None) -> list[str] | None:
    if command is None:
        return None
    if isinstance(command, str):
        return shlex.split(command)
    return [str(part) for part in command]


def _default_runner_factory(repo_root: Path) -> SandboxRunnerLike:
    from nexus.engine.sandbox_runner import SandboxRunner

    return SandboxRunner(repo_root)


def run_sandbox_task(
    repo_root: str | Path,
    task: str,
    *,
    command: str | list[str] | tuple[str, ...] | None = None,
    cwd: str | Path = ".",
    timeout_sec: int = 60,
    output_file: str | Path | None = None,
    cleanup: bool = True,
    runner_factory: SandboxRunnerFactory | None = None,
) -> SandboxRunResult:
    root = Path(repo_root)
    parsed_command = parse_sandbox_command(command)
    if not parsed_command:
        raise NexusCliActionError("Sandbox physical runner requires an explicit command.", exit_code=2)

    runner = (runner_factory or _default_runner_factory)(root)
    run_task = getattr(runner, "run_task", None)
    if not callable(run_task):
        raise NexusCliActionError("Sandbox runner does not expose run_task.", exit_code=1)

    raw_result = dict(
        run_task(
            task,
            command=parsed_command,
            cwd=cwd,
            timeout_sec=timeout_sec,
            output_file=output_file,
            cleanup=cleanup,
        )
    )
    return SandboxRunResult(
        task=task,
        success=bool(raw_result.get("success")),
        raw_result=raw_result,
    )


def render_sandbox_run_result(result: SandboxRunResult) -> list[str]:
    return [f"🏗️ [Sandbox] Execution finished. Success: {result.success}"]
