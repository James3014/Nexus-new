from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Awaitable, Callable


class WorkflowError(RuntimeError):
    pass


TaskFn = Callable[[], Awaitable[None]]


@dataclass
class _Task:
    run: TaskFn
    undo: TaskFn | None = None
    dependencies: list[str] = field(default_factory=list)


class AsyncDAGWorkflow:
    def __init__(self) -> None:
        self._tasks: dict[str, _Task] = {}

    def add_task(
        self,
        name: str,
        task: TaskFn,
        undo: TaskFn | None = None,
        dependencies: list[str] | None = None,
    ) -> None:
        self._tasks[name] = _Task(run=task, undo=undo, dependencies=list(dependencies or []))

    async def execute(self) -> None:
        self._validate_graph()
        completed: list[str] = []
        pending = set(self._tasks)

        try:
            while pending:
                ready = [
                    name
                    for name in pending
                    if all(dep in completed for dep in self._tasks[name].dependencies)
                ]
                if not ready:
                    raise WorkflowError("Circular dependency detected")
                await asyncio.gather(*(self._run_one(name, completed) for name in ready))
                pending.difference_update(ready)
        except Exception as exc:
            await self._rollback(completed)
            if isinstance(exc, WorkflowError):
                raise
            raise WorkflowError(str(exc)) from exc

    async def _run_one(self, name: str, completed: list[str]) -> None:
        await self._tasks[name].run()
        completed.append(name)

    async def _rollback(self, completed: list[str]) -> None:
        for name in reversed(completed):
            undo = self._tasks[name].undo
            if undo is not None:
                await undo()

    def _validate_graph(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise WorkflowError("Circular dependency detected")
            if name in visited:
                return
            if name not in self._tasks:
                raise WorkflowError(f"Unknown dependency: {name}")
            visiting.add(name)
            for dependency in self._tasks[name].dependencies:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)

        for task_name in self._tasks:
            visit(task_name)
