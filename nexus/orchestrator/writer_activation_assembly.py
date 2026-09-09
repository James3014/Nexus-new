"""Source-owned startup descriptor for a complete writer activation vector.

This module only freezes already-loaded inputs.  It does not discover roots
from HTTP data, publish authority, or create writer admission.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from nexus.contracts.state_owner_transition import WriterTransitionRequest
from nexus.orchestrator.unified_mcp_gateway import LoadedWriterCollectorPlan


class WriterAssemblyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedWriterAssembly:
    """Immutable owner-installed three-root assembly input."""

    source_root: Path
    source_head: str
    source_tree: str
    plans: tuple[LoadedWriterCollectorPlan, ...]
    requests: tuple[WriterTransitionRequest, ...]

    def __post_init__(self) -> None:
        root = self.source_root.resolve()
        if root != self.source_root or not root.is_absolute():
            raise WriterAssemblyError("ASSEMBLY_SOURCE_ROOT_NOT_CANONICAL")
        if not self.plans or len(self.plans) != len(self.requests):
            raise WriterAssemblyError("ASSEMBLY_VECTOR_LENGTH_MISMATCH")
        if len({plan.root.resolve() for plan in self.plans}) != len(self.plans):
            raise WriterAssemblyError("ASSEMBLY_ROOTS_NOT_UNIQUE")
        if len({request.root_id for request in self.requests}) != len(self.requests):
            raise WriterAssemblyError("ASSEMBLY_ROOT_IDS_NOT_UNIQUE")
        for plan, request in zip(self.plans, self.requests):
            if not isinstance(plan, LoadedWriterCollectorPlan) or not isinstance(request, WriterTransitionRequest):
                raise WriterAssemblyError("ASSEMBLY_TYPED_INPUT_REQUIRED")
            if (
                plan.request_digest != request.request_digest
                or plan.root_id != request.root_id
                or plan.root.resolve() != plan.root
                or plan.source_head != self.source_head
                or plan.source_tree != self.source_tree
                or request.expected_source_head != self.source_head
                or request.expected_source_tree != self.source_tree
            ):
                raise WriterAssemblyError("ASSEMBLY_PLAN_REQUEST_MISMATCH")

    @property
    def by_request_digest(self) -> Mapping[str, LoadedWriterCollectorPlan]:
        return {request.request_digest: plan for plan, request in zip(self.plans, self.requests)}

    @property
    def ordered_roots(self) -> tuple[Path, ...]:
        return tuple(plan.root for plan in self.plans)

    def plan_for(self, request: WriterTransitionRequest) -> LoadedWriterCollectorPlan:
        if not isinstance(request, WriterTransitionRequest):
            raise WriterAssemblyError("ASSEMBLY_REQUEST_TYPED_REQUIRED")
        plan = self.by_request_digest.get(request.request_digest)
        if plan is None or plan.root_id != request.root_id:
            raise WriterAssemblyError("ASSEMBLY_REQUEST_NOT_LOADED")
        return plan


def load_writer_assembly(
    *,
    source_root: Path,
    source_head: str,
    source_tree: str,
    plans: tuple[LoadedWriterCollectorPlan, ...],
    requests: tuple[WriterTransitionRequest, ...],
) -> LoadedWriterAssembly:
    """Validate an owner-installed vector without selecting any input."""
    return LoadedWriterAssembly(source_root, source_head, source_tree, tuple(plans), tuple(requests))


__all__ = ["LoadedWriterAssembly", "WriterAssemblyError", "load_writer_assembly"]
