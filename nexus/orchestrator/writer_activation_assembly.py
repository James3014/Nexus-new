"""Source-owned startup descriptor for a complete writer activation vector.

This module only freezes already-loaded inputs.  It does not discover roots
from HTTP data, publish authority, or create writer admission.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from nexus.contracts.state_owner_transition import Operation, WriterTransitionRequest
from nexus.orchestrator.unified_mcp_gateway import LoadedWriterCollectorPlan


class WriterAssemblyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LoadedWriterAssembly:
    """Immutable post-drain request/plan vector; production binding is explicit."""

    source_root: Path
    source_head: str
    source_tree: str
    plans: tuple[LoadedWriterCollectorPlan, ...]
    requests: tuple[WriterTransitionRequest, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.source_root, Path):
            raise WriterAssemblyError("ASSEMBLY_SOURCE_ROOT_NOT_CANONICAL")
        if not isinstance(self.plans, (tuple, list)) or not isinstance(
            self.requests, (tuple, list)
        ):
            raise WriterAssemblyError("ASSEMBLY_TYPED_INPUT_REQUIRED")
        object.__setattr__(self, "plans", tuple(self.plans))
        object.__setattr__(self, "requests", tuple(self.requests))
        if any(not isinstance(p, LoadedWriterCollectorPlan) for p in self.plans) or any(
            not isinstance(r, WriterTransitionRequest) for r in self.requests
        ):
            raise WriterAssemblyError("ASSEMBLY_TYPED_INPUT_REQUIRED")
        root = self.source_root.resolve()
        if root != self.source_root or not root.is_absolute():
            raise WriterAssemblyError("ASSEMBLY_SOURCE_ROOT_NOT_CANONICAL")
        if not self.plans or len(self.plans) != len(self.requests):
            raise WriterAssemblyError("ASSEMBLY_VECTOR_LENGTH_MISMATCH")
        roots = tuple(plan.root.resolve() for plan in self.plans)
        if len(set(roots)) != len(roots):
            raise WriterAssemblyError("ASSEMBLY_ROOTS_NOT_UNIQUE")
        if any(
            left in right.parents or right in left.parents
            for i, left in enumerate(roots)
            for right in roots[i + 1 :]
        ):
            raise WriterAssemblyError("ASSEMBLY_ROOTS_OVERLAP")
        if len({request.root_id for request in self.requests}) != len(self.requests):
            raise WriterAssemblyError("ASSEMBLY_ROOT_IDS_NOT_UNIQUE")
        if len({request.request_digest for request in self.requests}) != len(self.requests):
            raise WriterAssemblyError("ASSEMBLY_REQUEST_DIGESTS_NOT_UNIQUE")
        if len({plan.cohort_id for plan in self.plans}) != 1:
            raise WriterAssemblyError("ASSEMBLY_COHORTS_NOT_SHARED")
        for plan, request in zip(self.plans, self.requests):
            if (
                request.operation is not Operation.APPLY
                or plan.request_digest != request.request_digest
                or plan.root_id != request.root_id
                or plan.root.resolve() != plan.root
                or plan.source_head != self.source_head
                or plan.source_tree != self.source_tree
                or request.expected_source_head != self.source_head
                or request.expected_source_tree != self.source_tree
                or plan.cohort_id != request.transaction_id
                or plan.cohort_id != request.drain_receipt_id
                or hashlib.sha256(str(plan.root).encode()).hexdigest()
                != request.expected_root_identity
                or plan.generation != (request.expected_generation or 0)
                or plan.writer_id != request.expected_writer_id
                or set(plan.artifacts) != {item.relative_path for item in request.selections}
            ):
                raise WriterAssemblyError("ASSEMBLY_PLAN_REQUEST_MISMATCH")

    def bind_production_transitions(self, gateway):
        """Bind the finalized production vector to real direct A services.

        Owners/registry must already be loaded and drained. This method is the
        post-drain construction seam, not a cold-start discovery or issuer API.
        """
        from nexus.orchestrator.state_owner_transition_authority import LoadedSourceIdentity
        from nexus.orchestrator.state_owner_transition_service import StateOwnerTransitionService
        from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

        expected = {
            frozenset({"task_state"}),
            frozenset({"event_log"}),
            frozenset({"runtime_receipt", "effect_journal"}),
        }
        if (
            len(self.plans) != 3
            or {frozenset(item.role for item in req.selections) for req in self.requests}
            != expected
        ):
            raise WriterAssemblyError("ASSEMBLY_PRODUCTION_VECTOR_REQUIRED")
        if not isinstance(gateway, UnifiedMCPGateway):
            raise WriterAssemblyError("ASSEMBLY_LOADED_GATEWAY_REQUIRED")
        source = getattr(gateway.service, "loaded_source_identity", None)
        loaded_roots = getattr(gateway.service, "writer_roots", None)
        roots = {plan.root_id: plan.root for plan in self.plans}
        if (
            not isinstance(source, LoadedSourceIdentity)
            or source.repository != "James3014/Nexus-new"
            or source.source_head != self.source_head
            or source.source_tree != self.source_tree
            or not isinstance(loaded_roots, Mapping)
            or dict(loaded_roots) != roots
            or any(
                source.card_path != req.card_path or source.card_sha256 != req.card_sha256
                for req in self.requests
            )
        ):
            raise WriterAssemblyError("ASSEMBLY_LOADED_SOURCE_MISMATCH")
        registry = gateway._writer_quiescence_registry
        if (
            registry is None
            or registry.source_identity
            != f"{source.repository}@{self.source_head}:{self.source_tree}"
        ):
            raise WriterAssemblyError("ASSEMBLY_LOADED_HOLD_REQUIRED")
        drain = registry.load_finalized(self.plans[0].cohort_id)
        if (
            drain.ordered_roots != tuple(str(p.root) for p in self.plans)
            or len(drain.observations) != 4
            or any(
                req.drain_receipt_hash != hashlib.sha256(drain.to_bytes()).hexdigest()
                for req in self.requests
            )
        ):
            raise WriterAssemblyError("ASSEMBLY_LOADED_VECTOR_MISMATCH")
        for plan, request in zip(self.plans, self.requests):
            identities = [
                o.identity for o in drain.observations if o.identity.root == str(plan.root)
            ]
            if (
                len(identities) != len({s.role for s in request.selections})
                or {i.role for i in identities} != {s.role for s in request.selections}
                or any(
                    i.generation != plan.generation or i.writer_id != plan.writer_id
                    for i in identities
                )
            ):
                raise WriterAssemblyError("ASSEMBLY_LOADED_VECTOR_MISMATCH")
        prior = getattr(gateway.service, "loaded_writer_collector_plans", None)
        if prior is not None and tuple(prior) != self.plans:
            raise WriterAssemblyError("ASSEMBLY_COLLECTOR_ALREADY_BOUND")
        gateway.service.loaded_writer_collector_plans = self.plans
        gateway._bind_loaded_writer_collector_plan()
        service = StateOwnerTransitionService(
            roots=roots, source=source, source_root=self.source_root, service=gateway.service
        )
        service.bind_collector_port(gateway._writer_transition_collector)
        return tuple(service.loaded_root_transition(request) for request in self.requests)

    def validate_cohort_inputs(self, registry, hold, roots: Sequence) -> None:
        """Require the production three-root/four-role vector before F admission.

        The descriptor itself supports smaller generic vectors. This method
        binds the complete production vector to actual typed A/owner handles
        and the already-finalized original B hold, never constructs authority.
        """
        from nexus.orchestrator.writer_activation_cohort import ActivationRoot
        from nexus.orchestrator.writer_quiescence import WriterHold, WriterRegistry

        if not isinstance(registry, WriterRegistry) or not isinstance(hold, WriterHold):
            raise WriterAssemblyError("ASSEMBLY_LOADED_HOLD_REQUIRED")
        if (
            len(roots) != 3
            or len(hold.selected) != 4
            or any(not isinstance(item, ActivationRoot) for item in roots)
        ):
            raise WriterAssemblyError("ASSEMBLY_PRODUCTION_VECTOR_REQUIRED")
        expected = {
            frozenset({"task_state"}),
            frozenset({"event_log"}),
            frozenset({"runtime_receipt", "effect_journal"}),
        }
        if {frozenset(item.role for item in req.selections) for req in self.requests} != expected:
            raise WriterAssemblyError("ASSEMBLY_PRODUCTION_VECTOR_REQUIRED")
        if (
            tuple(item.root for item in roots) != tuple(str(p) for p in self.ordered_roots)
            or hold.registry is not registry
            or hold.roots != tuple(item.root for item in roots)
            or registry.source_identity
            != f"James3014/Nexus-new@{self.source_head}:{self.source_tree}"
        ):
            raise WriterAssemblyError("ASSEMBLY_LOADED_VECTOR_MISMATCH")
        finalized = registry.load_finalized(hold.cohort_id)
        for root, request in zip(roots, self.requests):
            if (
                root.transition.request != request
                or root.transition.service._source_root != self.source_root
                or {i.identity.role for i in hold.selected if i.identity.root == root.root}
                != {item.role for item in request.selections}
                or request.drain_receipt_hash != hashlib.sha256(finalized.to_bytes()).hexdigest()
            ):
                raise WriterAssemblyError("ASSEMBLY_LOADED_VECTOR_MISMATCH")

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
    return LoadedWriterAssembly(
        source_root, source_head, source_tree, tuple(plans), tuple(requests)
    )


__all__ = ["LoadedWriterAssembly", "WriterAssemblyError", "load_writer_assembly"]
