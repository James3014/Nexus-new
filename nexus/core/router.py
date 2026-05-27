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
    def __init__(self, project_root: str, run_dir: str = None, mem_palace: Any = None):
        self.project_root = project_root
        self.run_dir = run_dir or project_root
        self.mem_palace = mem_palace
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
            import os
            is_light_route = os.environ.get("NEXUS_LIGHT_ROUTE", "0") == "1"
            # 讀取當前 belief 信心狀態
            confidence = 1.0
            if hasattr(self.p_loop, "confidence"):
                confidence = float(self.p_loop.confidence)
            elif isinstance(self.p_loop, dict) and "confidence" in self.p_loop:
                confidence = float(self.p_loop["confidence"])
            elif hasattr(self.p_loop, "current_belief") and hasattr(self.p_loop.current_belief, "confidence"):
                confidence = float(self.p_loop.current_belief.confidence)

            if is_light_route and confidence >= 0.85:
                # 🚀 高信心狀態 + 輕量路由：自律跳過 LanceDB 全文檢索
                palace_result = {"status": "SUCCESS", "hit_rate": 0.0, "results": [], "tenant": tenant_id}
            else:
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
            if self.mem_palace and hasattr(self.mem_palace, "retrieve_from_shards"):
                rows = self.mem_palace.retrieve_from_shards(tenant_id, query, limit=3)
                results = self._filter_tenant_rows(rows, tenant_id)
                return {"status": "SUCCESS", "hit_rate": 1.0 if results else 0.0, "results": results, "tenant": tenant_id}
            from nexus.services.memory_repository import MemoryRepository
            from pathlib import Path
            repo = MemoryRepository(Path(self.project_root) / ".nexus" / "memory" / "memory_index.lancedb")
            tables = repo.list_tables()
            if not tables:
                return {"status": "SUCCESS", "hit_rate": 0.0, "results": [], "tenant": tenant_id}
            df = repo.search_fts_across_tables(query, list(tables)[:5], limit=3)
            results = self._filter_tenant_rows(df.to_dict(orient="records") if not df.empty else [], tenant_id)
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
            filtered = [c for c in raw_candidates if self._candidate_tenant_id(c) == str(tenant_id)]
            results = [{"id": c.id, "score": c.score} for c in filtered]
            return {"status": "SUCCESS", "results": results, "tenant": tenant_id}
        except Exception as e:
            logger.debug(f"_semantic_search error: {e}")
            return {"status": "SUCCESS", "results": [], "tenant": tenant_id}

    @staticmethod
    def _row_tenant_id(row: Dict[str, Any]) -> str:
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        return str(row.get("tenant_id") or row.get("tenant") or metadata.get("tenant_id") or metadata.get("tenant") or "")

    @classmethod
    def _filter_tenant_rows(cls, rows: List[Dict[str, Any]], tenant_id: str) -> List[Dict[str, Any]]:
        tenant = str(tenant_id or "")
        return [row for row in rows if isinstance(row, dict) and cls._row_tenant_id(row) == tenant]

    @staticmethod
    def _candidate_tenant_id(candidate: Any) -> str:
        metadata = getattr(candidate, "metadata", None)
        metadata = metadata if isinstance(metadata, dict) else {}
        return str(
            getattr(candidate, "tenant_id", "")
            or getattr(candidate, "tenant", "")
            or metadata.get("tenant_id")
            or metadata.get("tenant")
            or ""
        )

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
        """🛡️ Autonomic Selector Facade for SPXDRAC ecosystem (P29 merged)."""
        phase_key = str(phase or "R").lower()
        decision_id = f"dec_{phase_key}_{int(datetime.now(timezone.utc).timestamp() * 1000)}"
        
        # 1. 統一訊號採集 (P3)
        from nexus.core.capability_signal_set import CapabilitySignalSet
        signal_set = CapabilitySignalSet.from_context(context, self.project_root, belief_engine=self.p_loop)

        # 2. 安全約束評估 (P4)
        from nexus.core.capability_constraints import CapabilityConstraints
        constraints = CapabilityConstraints(self.project_root, mem_palace=self.mem_palace, firewall=self.firewall)

        # 3. 智慧能力動態選擇 (P5 & P7)
        from nexus.core.capability_selector import CapabilitySelector
        selector = CapabilitySelector()
        plan = selector.select_capabilities(signal_set, constraints)

        # 4. 驅動執行與收據累積 (P9 - P11)
        from nexus.core.executor_controls import ExecutorControls
        controller = ExecutorControls(self.project_root)
        
        # 處理 possible block
        if isinstance(plan, dict) and plan.get("status") == "BLOCKED":
            logger.warning("🛡️ [SkillsRouter] Capability Selector BLOCKED execution.")
            return []

        receipts = controller.execute_plan(plan)

        # 5. [P26] OutcomeMemory 學習寫回
        try:
            learning_log = Path(self.project_root) / ".nexus" / "reports" / "learn" / "learning_closure.jsonl"
            learning_log.parent.mkdir(parents=True, exist_ok=True)
            with open(learning_log, "a", encoding="utf-8") as handle:
                for cap_receipt in receipts:
                    row = {
                        "plan_id": plan.plan_id,
                        "task_id": plan.task_id,
                        "capability_name": cap_receipt.capability_name,
                        "gate_passed": cap_receipt.gate_passed,
                        "outcome": cap_receipt.outcome,
                        "timestamp": cap_receipt.timestamp,
                    }
                    handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.debug("[OutcomeMemory] learning_closure writeback failed: %s", e)

        # 6. 包裝成果並回傳給舊接口 (向下相容)
        candidates = []
        for cap_receipt in receipts:
            for skill_receipt in cap_receipt.skill_receipts:
                if skill_receipt.used:
                    candidates.append({
                        "skill_id": skill_receipt.skill_id,
                        "score": 1.0,
                        "source": "autonomic_selector",
                        "artifact_found": True,
                        "decision_id": decision_id,
                    })

        # Fallback to legacy triggers if no candidate found
        if not candidates:
            candidates = self._inventory_candidates(phase, context)
            for c in candidates:
                c["decision_id"] = decision_id

        # 記錄 decision log
        run_dir = __import__("pathlib").Path(self.run_dir)
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "router_decisions.jsonl"
        row = {
            "decision_id": decision_id,
            "phase": phase,
            "task_id": context.get("task_id", ""),
            "candidate_count": len(candidates),
            "fallback_used": len(candidates) == 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        with open(log_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")

        return candidates

    def _inventory_candidates(self, phase: str, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        inventory_path = Path(self.project_root) / "scripts" / "skills_inventory.json"
        if not inventory_path.exists():
            return []
        try:
            inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        phase_value = str(phase or "").upper()
        query = " ".join(
            str(context.get(key, ""))
            for key in ("task_desc", "task_id", "query")
            if context.get(key)
        ).lower()
        candidates: List[Dict[str, Any]] = []
        for skill_id, meta in (inventory.get("skills", {}) or {}).items():
            builtin_skill = Path(self.project_root) / "scripts" / "skills_builtin" / skill_id / "SKILL.md"
            external_skill = Path(self.project_root) / "scripts" / skill_id / "SKILL.md"
            if not builtin_skill.exists() and not external_skill.exists():
                continue
            phases = [str(p).upper() for p in (meta.get("phases") or [])]
            if phases and phase_value and phase_value not in phases:
                continue
            triggers = [str(t).lower() for t in (meta.get("triggers") or [])]
            trigger_hit = any(t and t in query for t in triggers)
            candidates.append(
                {
                    "skill_id": skill_id,
                    "score": 1.0 if trigger_hit else 0.5,
                    "source": "inventory",
                    "artifact_found": True,
                }
            )
        return sorted(candidates, key=lambda c: c["score"], reverse=True)

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
