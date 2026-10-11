"""Phase 5b-1: nexus-runtime owns the self-hosted task status vocabulary."""

from __future__ import annotations

import ast
from pathlib import Path

import nexus_runtime.task_lifecycle as runtime_lifecycle

import nexus.orchestrator.self_hosted_task_service as service

SERVICE_SOURCE = (
    Path(__file__).resolve().parents[2] / "nexus" / "orchestrator" / "self_hosted_task_service.py"
)


def test_service_status_sets_are_the_runtime_objects() -> None:
    for name in runtime_lifecycle.__all__:
        assert getattr(service, name) is getattr(runtime_lifecycle, name), name


def test_service_does_not_redefine_status_sets() -> None:
    tree = ast.parse(SERVICE_SOURCE.read_text(encoding="utf-8"))
    assigned = {
        target.id
        for node in tree.body
        if isinstance(node, (ast.Assign, ast.AnnAssign))
        for target in (node.targets if isinstance(node, ast.Assign) else [node.target])
        if isinstance(target, ast.Name)
    }
    assert assigned.isdisjoint(runtime_lifecycle.__all__)
