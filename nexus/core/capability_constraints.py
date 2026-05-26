from __future__ import annotations

import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

from nexus.core.domain_firewall import DomainFirewall
from nexus.core.mem_palace import MemoryPalace


class CapabilityConstraints:
    """🛡️ Hard constraints collector packaging MemPalace & DomainFirewall rules."""

    def __init__(
        self,
        project_root: str,
        mem_palace: Any | None = None,
        firewall: Any | None = None,
    ) -> None:
        self.project_root = project_root
        self.mem_palace = mem_palace or MemoryPalace(
            proto_path=__import__("pathlib").Path(project_root) / "MUSE_PROTO.md"
        )
        self.firewall = firewall or DomainFirewall()

    def evaluate_constraints(self, signal_set: Any) -> Dict[str, Any]:
        """Verify the given task snapshot against ethical firewall & blacklists."""
        # 1. 黑名單檢核 (Ethical Blacklist Check)
        if hasattr(self.mem_palace, "verify_context"):
            try:
                verdict = self.mem_palace.verify_context(signal_set.task_desc)
                if isinstance(verdict, dict) and verdict.get("status") == "BLOCKED":
                    logger.warning(
                        "🛡️ [MemPalace] Context blocked by ethical pattern: %s",
                        verdict.get("reason"),
                    )
                    return {"status": "BLOCKED", "reason": f"ETHICAL_BLOCK: {verdict.get('reason')}"}
            except Exception as e:
                logger.error("🛡️ [MemPalace] verify_context error: %s", e)

        # 2. 獲取 TTL / 信念約束條件 (forbid / require / prefer)
        constraints = {"require": [], "forbid": [], "prefer": []}
        if hasattr(self.mem_palace, "get_skill_constraints"):
            try:
                constraints = self.mem_palace.get_skill_constraints()
            except Exception as e:
                logger.debug("🛡️ [MemPalace] get_skill_constraints error: %s", e)

        return {
            "status": "ALLOWED",
            "forbidden_skills_rules": list(constraints.get("forbid") or []),
            "required_skills_rules": list(constraints.get("require") or []),
            "preferred_skills_rules": list(constraints.get("prefer") or []),
        }

    def authorize_skill_for_domain(self, skill_id: str, active_domain: str) -> bool:
        """Verify if the selected skill is authorized for the current domain."""
        try:
            return bool(self.firewall.authorize(skill_id, active_domain))
        except Exception as e:
            logger.error("🛡️ [DomainFirewall] authorization error: %s", e)
            return False
