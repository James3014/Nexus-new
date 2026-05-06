from __future__ import annotations

from typing import Any


class DistantScoutPlanner:
    """Generate an architecture-level pivot when local repair reaches a plateau."""

    def plan(
        self,
        *,
        task_desc: str,
        plateau: dict[str, Any],
        asi_ledger: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not plateau.get("detected"):
            return {
                "schema": "nexus_distant_scout_plan_v1",
                "status": "SKIPPED",
                "reason": "plateau_not_detected",
                "architecture_actions": [],
            }

        family = str(plateau.get("family") or "").strip()
        forbidden = [family] if family else []
        reasons = [
            str(item.get("rollback_reason") or item.get("evidence") or "").strip()
            for item in (asi_ledger or [])
            if isinstance(item, dict)
        ]
        reasons = [item for item in reasons if item]
        recommended_family = self._recommended_family(family, task_desc)
        target_boundary = self._target_boundary(recommended_family, task_desc)
        affected_files = self._affected_files(target_boundary)
        rollback_plan = {
            "strategy": "preserve_target_then_apply_bounded_seam",
            "restore_points": affected_files,
            "abort_if": [
                "verification_command_fails",
                "blast_radius_expands_beyond_target_boundary",
                "recommended_family_matches_forbidden_family",
            ],
        }
        return {
            "schema": "nexus_distant_scout_plan_v1",
            "status": "READY",
            "reason": str(plateau.get("reason") or "plateau_detected"),
            "forbidden_families": forbidden,
            "recommended_family": recommended_family,
            "target_boundary": target_boundary,
            "affected_files": affected_files,
            "architecture_actions": [
                "identify_component_boundary",
                "introduce_testable_seam",
                "move_retry_or_timeout_policy_behind_interface",
                "verify_with_regression_test_before_patch_acceptance",
            ],
            "bounded_refactor": {
                "max_files": len(affected_files),
                "allowed_files": affected_files,
                "requires_new_test": True,
                "requires_rollback_plan": True,
            },
            "rollback_plan": rollback_plan,
            "gate_passed": bool(affected_files and rollback_plan["restore_points"] and recommended_family not in forbidden),
            "failure_signatures": list(dict.fromkeys(reasons))[:5],
            "verification_commands": [
                "uv run pytest -q",
                "uv run python scripts/ops/capability_route_smoke.py --print-only",
            ],
        }

    def _recommended_family(self, family: str, task_desc: str) -> str:
        text = f"{family} {task_desc}".lower()
        if "retry" in text or "timeout" in text or "race" in text:
            return "flow:architecture_timeout_policy_seam"
        if "storage" in text or "repository" in text:
            return "flow:architecture_storage_boundary"
        return "flow:architecture_boundary_refactor"

    def _target_boundary(self, recommended_family: str, task_desc: str) -> str:
        text = f"{recommended_family} {task_desc}".lower()
        if "timeout" in text or "retry" in text or "race" in text:
            return "repair_timeout_policy"
        if "storage" in text or "repository" in text:
            return "storage_search_boundary"
        return "component_boundary"

    def _affected_files(self, target_boundary: str) -> list[str]:
        if target_boundary == "repair_timeout_policy":
            return ["nexus/app/research_flow_service.py", "nexus/research/sprint_service.py"]
        if target_boundary == "storage_search_boundary":
            return ["nexus/infrastructure/storage_implementations.py", "nexus/services/semantic_searcher.py"]
        return ["nexus/app/research_flow_service.py"]


class ArchitectureRefactorExecutor:
    """Validate and materialize a bounded architecture refactor contract."""

    def prepare(self, *, plan: dict[str, Any], requested_files: list[str]) -> dict[str, Any]:
        if str(plan.get("status") or "") != "READY":
            return {
                "schema": "nexus_architecture_refactor_execution_v1",
                "status": "BLOCKED",
                "reason": "scout_plan_not_ready",
                "allowed_files": [],
                "target_files": [],
            }
        bounded = plan.get("bounded_refactor") if isinstance(plan.get("bounded_refactor"), dict) else {}
        allowed = [str(item) for item in bounded.get("allowed_files", []) or [] if str(item).strip()]
        requested = [str(item) for item in requested_files or [] if str(item).strip()]
        out_of_scope = [item for item in requested if item not in set(allowed)]
        requires_new_test = bool(bounded.get("requires_new_test", False))
        rollback = plan.get("rollback_plan") if isinstance(plan.get("rollback_plan"), dict) else {}
        rollback_ready = bool(rollback.get("restore_points"))
        status = "READY" if requested and not out_of_scope and requires_new_test and rollback_ready else "BLOCKED"
        failures: list[str] = []
        if not requested:
            failures.append("no_target_files")
        if out_of_scope:
            failures.append("target_outside_bounded_refactor")
        if not requires_new_test:
            failures.append("missing_new_test_requirement")
        if not rollback_ready:
            failures.append("rollback_plan_missing_restore_points")
        return {
            "schema": "nexus_architecture_refactor_execution_v1",
            "status": status,
            "target_boundary": plan.get("target_boundary", ""),
            "recommended_family": plan.get("recommended_family", ""),
            "allowed_files": allowed,
            "target_files": requested,
            "out_of_scope_files": out_of_scope,
            "requires_new_test": requires_new_test,
            "rollback_ready": rollback_ready,
            "verification_commands": list(plan.get("verification_commands", []) or []),
            "failures": failures,
        }
