"""Workspace inventory cluster of ``SelfHostedTaskService``.

Big-file split S2 (Issue #2542). ``_InventoryMixin`` holds the durable-state and
workspace inventory methods moved out of ``nexus/orchestrator/self_hosted_task_service.py``:
``_workspace_task_states``, ``_submission_task_states`` (the fail-closed submission
inventory), ``find_tasks_by_repository_issue``, ``workspace_inventory``,
``state_root_inventory``, ``workspace_convergence_plan``, ``workspace_slot_status``,
``workspace_slot_prepare`` and ``apply_workspace_convergence``. Their source lines are
verbatim, except that every facade-module name they load that the facade defines or that
tests patch on the facade (``WorktreeManager``, ``_jsonable``) is resolved at call time
through ``_service_module()``.

``workspace_slot_prepare`` prepares a worktree slot through ``WorktreeManager`` and
``apply_workspace_convergence(apply=True)`` runs ``cleanup_tasks(dry_run=False)``; both
reach those effects through ``self`` / the facade exactly as before. ``state_dir``,
``_read_state_snapshot``, ``canonical_state_dir``, ``build_contract`` and
``cleanup_tasks`` stay in the facade class.
"""

from __future__ import annotations

import hashlib
import importlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Mapping, Optional

if TYPE_CHECKING:
    from nexus.orchestrator.task_contract import ArchitectTaskContract


def _service_module():
    # Late binding: the service imports this module at its top level, so its own
    # (and its patched) names are only resolved once a method runs.
    return importlib.import_module("nexus.orchestrator.self_hosted_task_service")


class _InventoryMixin:
    """Mixin base of ``SelfHostedTaskService``; never instantiated on its own."""

    if TYPE_CHECKING:  # provided by SelfHostedTaskService
        state_dir: Path

        @staticmethod
        def canonical_state_dir() -> Path: ...

        def _read_state_snapshot(self, task_id: str) -> Optional[dict[str, Any]]: ...

        def build_contract(self, request: Mapping[str, Any]) -> ArchitectTaskContract: ...

        def cleanup_tasks(
            self, *, task_id: Optional[str] = None, dry_run: bool = True
        ) -> dict[str, Any]: ...

    # fmt: off
    def _workspace_task_states(self) -> dict[str, dict[str, Any]]:
        """Load durable task snapshots without invoking reconciliation."""
        if not self.state_dir.exists():
            return {}
        states: dict[str, dict[str, Any]] = {}
        for path in sorted(self.state_dir.glob("*.json")):
            state = self._read_state_snapshot(path.stem)
            if state is not None:
                states[path.stem] = state
        return states

    def _submission_task_states(self) -> dict[str, dict[str, Any]]:
        """Fail closed when submission authority cannot trust durable state."""
        states = self._workspace_task_states()
        invalid = [
            state
            for state in states.values()
            if state.get("state_valid") is False
        ]
        if invalid:
            blockers = ",".join(
                f"{state.get('task_id') or 'unknown'}:"
                f"{(state.get('blocker') or {}).get('code') or 'STATE_INVALID'}"
                for state in invalid
            )
            raise RuntimeError(
                f"INVALID_DURABLE_STATE_BLOCKS_SUBMISSION:{blockers}"
            )
        return states

    def find_tasks_by_repository_issue(
        self, repository: str, issue_number: int
    ) -> list[dict[str, Any]]:
        """Read tasks whose persisted request binds exactly to repository and issue."""
        repository = str(repository).strip()
        issue = str(issue_number).strip()
        matches: list[dict[str, Any]] = []
        for state in self._workspace_task_states().values():
            request = state.get("request") if isinstance(state.get("request"), Mapping) else {}
            request_repository = str(request.get("repository") or "").strip()  # pyright: ignore[reportOptionalMemberAccess]
            request_issue = str(request.get("issue") or request.get("issue_number") or "").strip()  # pyright: ignore[reportOptionalMemberAccess]
            state_repository = str(state.get("repository") or "").strip()
            state_issue = str(state.get("issue") or "").strip()
            if ((request_repository == repository and request_issue == issue) or
                    (state_repository == repository and state_issue == issue)):
                matches.append(state)
        return matches

    def workspace_inventory(
        self,
        *,
        controller_root: Optional[str | Path] = None,
    ) -> dict[str, Any]:
        """Read-only inventory of registered worktrees and lifecycle ownership."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = _service_module().WorktreeManager(root_dir=str(root.parent / "nexus-runtime-targets"), create_root=False)
        inventory = manager.get_workspace_inventory(
            controller_root=root,
            task_states=states,
        )
        return _service_module()._jsonable(inventory)

    def state_root_inventory(self) -> dict[str, Any]:
        """Inventory canonical and nested lifecycle state without mutation."""
        canonical = self.canonical_state_dir()
        entries: list[dict[str, Any]] = []
        if canonical.exists():
            candidates = sorted(canonical.glob("**/*.json"))
        else:
            candidates = []
        for path in candidates:
            if path.name.startswith("manifest-"):
                continue
            try:
                raw = path.read_bytes()
                state = json.loads(raw)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(state, Mapping) or not state.get("task_id"):
                continue
            relative_parent = path.parent.relative_to(canonical)
            if str(relative_parent) == ".":
                authority = "CANONICAL_AUTHORITY"
            elif "nexus-state-archive" in path.parts:
                authority = "ARCHIVE_EVIDENCE"
            else:
                authority = "REHEARSAL_EVIDENCE"
            entries.append({
                "path": str(path),
                "authority": authority,
                "task_id": state.get("task_id"),
                "attempt_id": state.get("attempt_id"),
                "status": state.get("status"),
                "promotion_status": state.get("promotion_status"),
                "candidate_commit_sha": state.get("candidate_commit_sha"),
                "candidate_ref": state.get("candidate_ref"),
                "state_sha256": hashlib.sha256(raw).hexdigest(),
                "updated_at": state.get("updated_at"),
            })
        by_task: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            by_task.setdefault(str(entry["task_id"]), []).append(entry)
        canonical_authority_counts = {
            task_id: sum(1 for value in values if value["authority"] == "CANONICAL_AUTHORITY")
            for task_id, values in by_task.items()
        }
        conflicts = sorted(task_id for task_id, count in canonical_authority_counts.items() if count > 1)
        evidence_duplicates = sorted(task_id for task_id, values in by_task.items() if len(values) > 1 and task_id not in conflicts)
        return {
            "schema": "nexus.lifecycle_state_root_inventory.v1",
            "canonical_state_root": str(canonical),
            "entry_count": len(entries),
            "task_count": len(by_task),
            "conflict_task_ids": conflicts,
            "authority_conflict": bool(conflicts),
            "evidence_duplicate_task_ids": evidence_duplicates,
            "entries": entries,
            "inventory_sha256": hashlib.sha256(
                json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest(),
        }

    def workspace_convergence_plan(
        self,
        *,
        controller_root: Optional[str | Path] = None,
        expected_controller_revision: Optional[str] = None,
    ) -> dict[str, Any]:
        """Build a stable dry-run plan; no state or workspace mutation occurs."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = _service_module().WorktreeManager(root_dir=str(root.parent / "nexus-runtime-targets"), create_root=False)
        inventory = manager.get_workspace_inventory(
            controller_root=root,
            task_states=states,
        )
        expected = expected_controller_revision or inventory.controller_head
        plan = manager.plan_convergence(inventory, expected_controller_revision=expected)
        return _service_module()._jsonable(plan)

    def workspace_slot_status(
        self,
        *,
        campaign_id: str = "default",
        slot_index: int = 0,
        controller_root: Optional[str | Path] = None,
    ) -> dict[str, Any]:
        """Read-only reusable-slot readiness check."""
        states = self._workspace_task_states()
        root = Path(controller_root or Path.cwd()).resolve()
        manager = _service_module().WorktreeManager(root_dir=str(root.parent / "nexus-runtime-targets"), create_root=False)
        status = manager.get_reusable_slot_status(
            campaign_id=campaign_id,
            slot_index=slot_index,
            controller_root=root,
            task_states=states,
        )
        return _service_module()._jsonable(status)

    def workspace_slot_prepare(
        self,
        request: Mapping[str, Any],
        *,
        campaign_id: str = "default",
        slot_index: int = 0,
    ) -> dict[str, Any]:
        """Prepare one reusable slot through WorktreeManager authority."""
        contract = self.build_contract(request)
        states = self._workspace_task_states()
        manager = _service_module().WorktreeManager(root_dir=contract.target_worktree_root)
        prepared = manager.prepare_reusable_slot(
            contract,
            campaign_id=campaign_id,
            slot_index=slot_index,
            task_states=states,
        )
        return _service_module()._jsonable(prepared)

    def apply_workspace_convergence(
        self,
        *,
        controller_root: Optional[str | Path] = None,
        expected_controller_revision: str,
        expected_plan_hash: str,
        apply: bool = False,
    ) -> dict[str, Any]:
        """Apply only lifecycle-bound terminal cleanup through existing authority.

        The default is a dry-run.  Unbound redundant worktrees remain blocked
        because they have no task contract through which existing cleanup
        authority can safely operate.
        """
        root = Path(controller_root or Path.cwd()).resolve()
        states = self._workspace_task_states()
        manager = _service_module().WorktreeManager(
            root_dir=str(root.parent / "nexus-runtime-targets"),
            create_root=False,
        )
        inventory = manager.get_workspace_inventory(controller_root=root, task_states=states)
        if inventory.controller_head != expected_controller_revision:
            raise RuntimeError(
                f"CONTROLLER_REVISION_DRIFT: current controller {inventory.controller_head} "
                f"does not match expected {expected_controller_revision}"
            )
        plan = manager.plan_convergence(
            inventory,
            expected_controller_revision=expected_controller_revision,
        )
        if plan.plan_hash != expected_plan_hash:
            raise RuntimeError(
                f"PLAN_HASH_MISMATCH: current plan {plan.plan_hash} "
                f"does not match expected {expected_plan_hash}"
            )
        if not apply:
            return {
                **_service_module()._jsonable(plan),
                "applied": False,
                "next_gate": "EXPLICIT_APPLY",
            }

        decisions: list[dict[str, Any]] = []
        path_to_state = {
            str(Path((state.get("lease") or {}).get("target_worktree") or "").resolve()): state
            for state in states.values()
            if (state.get("lease") or {}).get("target_worktree")
        }
        for path in plan.releasable_paths:
            if Path(path).resolve() == Path("/Users/jameschen/Workspace/nexus").resolve():
                raise RuntimeError("LEGACY_ROOT_APPLY_FORBIDDEN: legacy root cannot be released")
            state = path_to_state.get(str(Path(path).resolve()))
            if state is None:
                decisions.append({
                    "path": path,
                    "cleanup_decision": "BLOCKED_UNBOUND_WORKSPACE",
                    "cleanup_blocker": "no lifecycle task contract owns this worktree",
                    "cleanup_performed": False,
                })
                continue
            task_id = str(state.get("task_id"))
            result = self.cleanup_tasks(task_id=task_id, dry_run=False)
            decisions.extend(result.get("decisions", []))

        return {
            **_service_module()._jsonable(plan),
            "applied": True,
            "decisions": decisions,
            "next_gate": "OWNER_REVIEW",
        }
    # fmt: on
