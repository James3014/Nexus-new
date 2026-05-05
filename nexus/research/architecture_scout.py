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
        return {
            "schema": "nexus_distant_scout_plan_v1",
            "status": "READY",
            "reason": str(plateau.get("reason") or "plateau_detected"),
            "forbidden_families": forbidden,
            "recommended_family": recommended_family,
            "architecture_actions": [
                "identify_component_boundary",
                "introduce_testable_seam",
                "move_retry_or_timeout_policy_behind_interface",
                "verify_with_regression_test_before_patch_acceptance",
            ],
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
