import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

# The module was archived in #2373 (repo root -> docs/archive/root-2026-10). Load it by path
# so the archive directory never lands on sys.path (it holds many stale modules).
_PATH = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "archive"
    / "root-2026-10"
    / "nexus_dag_workflow.py"
)
_SPEC = importlib.util.spec_from_file_location("archived_nexus_dag_workflow", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _MODULE  # dataclasses resolve their module by name
_SPEC.loader.exec_module(_MODULE)
AsyncDAGWorkflow = _MODULE.AsyncDAGWorkflow
WorkflowError = _MODULE.WorkflowError


@pytest.mark.asyncio
async def test_circular_dependency():
    wf = AsyncDAGWorkflow()

    async def dummy():
        pass

    wf.add_task("A", dummy, dependencies=["B"])
    wf.add_task("B", dummy, dependencies=["A"])

    with pytest.raises(WorkflowError, match="Circular dependency"):
        await wf.execute()


@pytest.mark.asyncio
async def test_concurrent_execution():
    wf = AsyncDAGWorkflow()
    executed = []

    async def task_a():
        await asyncio.sleep(0.2)
        executed.append("A")

    async def task_b():
        await asyncio.sleep(0.1)
        executed.append("B")

    async def task_c():
        executed.append("C")

    # A depends on B and C. B and C should run concurrently.
    wf.add_task("A", task_a, dependencies=["B", "C"])
    wf.add_task("B", task_b)
    wf.add_task("C", task_c)

    await wf.execute()

    # B and C must finish before A.
    # Since B has a sleep and C doesn't, C should finish before B.
    assert executed == ["C", "B", "A"]


@pytest.mark.asyncio
async def test_rollback_on_failure():
    wf = AsyncDAGWorkflow()
    history = []
    undone = []

    async def t1():
        history.append("T1")

    async def u1():
        undone.append("U1")

    async def t2():
        history.append("T2")
        raise ValueError("Fail T2")

    async def u2():
        undone.append("U2")

    wf.add_task("T1", t1, u1)
    wf.add_task("T2", t2, u2, dependencies=["T1"])

    with pytest.raises(WorkflowError):
        await wf.execute()

    # T1 finished, T2 failed. Rollback should undo T1.
    assert history == ["T1", "T2"]
    assert undone == ["U1"]


@pytest.mark.asyncio
async def test_reverse_topological_rollback():
    wf = AsyncDAGWorkflow()
    results = []
    undone = []

    async def make_task(name):
        async def t():
            results.append(name)

        async def u():
            undone.append(name)

        return t, u

    tA, uA = await make_task("A")
    tB, uB = await make_task("B")
    tC, uC = await make_task("C")

    async def t_fail():
        raise RuntimeError("Crash")

    wf.add_task("A", tA, uA)
    wf.add_task("B", tB, uB, dependencies=["A"])
    wf.add_task("C", tC, uC, dependencies=["B"])
    wf.add_task("FAIL", t_fail, dependencies=["C"])

    with pytest.raises(WorkflowError):
        await wf.execute()

    # Execution was A -> B -> C -> FAIL
    # Rollback must be C -> B -> A
    assert results == ["A", "B", "C"]
    assert undone == ["C", "B", "A"]
