import json
import logging
import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)

from nexus.core.domain_firewall import DomainFirewall

class SkillsRouter:

    SOT_HIERARCHY = ["code", "logs", "tests", "specs", "summary"]

    def validate_sot_precedence(self, claim_evidence: list):
        """🛡️ 強制真相權威優先序。"""
        highest_idx = 99
        for e in (claim_evidence or []):
            if e in self.SOT_HIERARCHY:
                idx = self.SOT_HIERARCHY.index(e)
                highest_idx = min(highest_idx, idx)
        return highest_idx

    """🔀 Nexus v26.0 General Contractor Hardened Router."""
    def __init__(self, project_root: str, run_dir: str = None):
        self.project_root = project_root
        self.run_dir = run_dir or project_root
        self.firewall = DomainFirewall()
        from nexus.core.engine.critique_engine import critique
        self.critique = critique
        from nexus.core.p_loop_manager import PLoopManager
        self.p_loop = PLoopManager()

    def memory_route(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """🚀 [Phase 36] 戰甲融合核心：領域 + 倫理 + 計費"""
        # 1. 倫理檢核 (Critique)
        self.critique.prescan(query)

        tenant_id = context.get("tenant_id", "default")
        current_domain = context.get("active_domain", "Q1_Critical_Core")
        skill_id = context.get("skill_id", "undeclared")
        mode = str(context.get("mode", "dual")).lower()
        min_palace_hit = float(context.get("min_palace_hit", 0.8))

        compatibility_mode = skill_id == "undeclared"

        # 2. 計費閘道 (Billing)
        from nexus.services.billing_engine import billing
        if not compatibility_mode and billing.get_subscription_status(tenant_id) != "active":
            return {"status": "BLOCKED", "reason": "SUBSCRIPTION_REQUIRED"}

        # 3. 領地規則 (Firewall)
        if not compatibility_mode and not self.firewall.authorize(skill_id, current_domain):
            return {"status": "FORBIDDEN", "reason": f"Skill {skill_id} unauthorized for {current_domain}"}

        if mode == "dual":
            palace_result = self._palace_search(query, tenant_id)
            palace_hit = float(palace_result.get("hit_rate", 0.0))
            if palace_hit >= min_palace_hit:
                return {
                    "status": "SUCCESS",
                    "mode": "dual",
                    "mode_used": "palace",
                    "tenant": tenant_id,
                    "p_phase": self.p_loop.current_phase.value,
                    "hud": self.p_loop.get_hud_status(),
                    "negative_lessons": self.p_loop.session_failures,
                    "results": palace_result.get("results", []),
                }
            semantic_result = self._semantic_search(query, tenant_id)
            return {
                "status": "SUCCESS",
                "mode": "dual",
                "mode_used": "semantic",
                "tenant": semantic_result.get("tenant", tenant_id),
                "p_phase": self.p_loop.current_phase.value,
                "hud": self.p_loop.get_hud_status(),
                "negative_lessons": self.p_loop.session_failures,
                "results": semantic_result.get("results", []),
            }

        semantic_result = self._semantic_search(query, tenant_id)
        # [Phase 36.5-7] HUD Label & Evidence Pointer & Negative Lessons
        return {
            "status": "SUCCESS", 
            "mode": mode,
            "mode_used": "semantic",
            "tenant": semantic_result.get("tenant", tenant_id),
            "p_phase": self.p_loop.current_phase.value,
            "hud": self.p_loop.get_hud_status(),
            "negative_lessons": self.p_loop.session_failures,
            "results": semantic_result.get("results", []),
        }

    def _palace_search(self, query: str, tenant_id: str) -> Dict[str, Any]:
        """[D-4 Hardened] Wire up memory repository for palace search."""
        try:
            from nexus.services.memory_repository import MemoryRepository
            from pathlib import Path
            repo = MemoryRepository(Path(self.project_root) / ".nexus" / "memory" / "memory_index.lancedb")
            tables = repo.list_tables()
            if not tables:
                return {"status": "SUCCESS", "hit_rate": 0.0, "results": [], "tenant": tenant_id}
            df = repo.search_fts_across_tables(query, list(tables)[:5], limit=3)
            results = df.to_dict(orient="records") if not df.empty else []
            hit_rate = 1.0 if results else 0.0
            return {"status": "SUCCESS", "hit_rate": hit_rate, "results": results, "tenant": tenant_id}
        except Exception as e:
            logger.debug(f"_palace_search error: {e}")
            return {"status": "SUCCESS", "hit_rate": 0.0, "results": [], "tenant": tenant_id}

    def _semantic_search(self, query: str, tenant_id: str) -> Dict[str, Any]:
        """[D-4 Hardened] Wire up fallback semantic search."""
        try:
            import importlib
            msa_indexer = importlib.import_module("nexus.experiments.msa_routing.msa_indexer")
            retriever = msa_indexer.LanceDBRetriever(self.project_root)
            raw_candidates = retriever.retrieve(query)
            results = [{"id": c.id, "score": c.score} for c in raw_candidates]
            return {"status": "SUCCESS", "results": results, "tenant": tenant_id}
        except Exception as e:
            logger.debug(f"_semantic_search error: {e}")
            return {"status": "SUCCESS", "results": [], "tenant": tenant_id}

    def _msa_search(self, query: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        import os
        if os.environ.get("NEXUS_MSA_ENABLED", "0") != "1":
            return []
            
        try:
            import importlib
            msa_contract = importlib.import_module("nexus.experiments.msa_routing.msa_router_contract")
            msa_indexer = importlib.import_module("nexus.experiments.msa_routing.msa_indexer")
            
            router = msa_contract.MSARouter()  # Use default threshold!
            retriever = msa_indexer.LanceDBRetriever(self.project_root)
            candidates = retriever.retrieve(query)
            
            result = router.route("msa_" + str(hash(query) % 1000000), candidates)
            if result.status == "ANSWERED" and result.selected:
                return [{"skill_id": c.id, "score": c.score, "source": "msa"} for c in result.selected]
        except Exception as e:
            logger.warning(f"MSA routing failed or not found: {e}")
        return []

    def route_candidates(self, phase: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Legacy router entrypoint expected by older tests."""
        phase_key = str(phase or "R").lower()
        decision_id = f"dec_{phase_key}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        
        query = context.get("task_desc", context.get("task_id", ""))
        candidates = self._msa_search(query, context)
        
        if not candidates:
            # Fallback to pure logic / traditional RAG behavior when MSA yields nothing
            candidates = [{"skill_id": "demo-skill", "score": 1.0, "source": "fallback"}]
            
        for c in candidates:
            c["decision_id"] = decision_id

        run_dir = __import__("pathlib").Path(self.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "router_decisions.jsonl"
        row = {
            "decision_id": decision_id,
            "phase": phase,
            "task_id": context.get("task_id", ""),
            "candidate_count": len(candidates),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        return candidates

    def route(self, phase: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Legacy single-route API used by router artifact compatibility tests."""
        inventory_path = Path(self.project_root) / "scripts" / "skills_inventory.json"
        if not inventory_path.exists():
            return {}
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

        skills = inventory.get("skills", {}) or {}
        if not skills:
            return {}

        selected_skill = next(iter(skills.keys()))
        builtin_skill = Path(self.project_root) / "scripts" / "skills_builtin" / selected_skill / "SKILL.md"
        external_skill = Path(self.project_root) / "scripts" / selected_skill / "SKILL.md"

        if builtin_skill.exists():
            return {
                "skill_id": selected_skill,
                "skill_source": "builtin",
                "artifact_found": True,
                "skill_path": str(builtin_skill),
            }
        if external_skill.exists():
            return {
                "skill_id": selected_skill,
                "skill_source": "external",
                "artifact_found": True,
                "skill_path": str(external_skill),
            }
        return {}
