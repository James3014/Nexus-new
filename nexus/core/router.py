from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
from datetime import datetime, timezone
import hashlib
import logging

logger = logging.getLogger(__name__)


class SkillsRouter:
    """
    🔀 Nexus v7 Skills Router (Hardened)
    整合 Superpowers 權重體系與決策樹注入，提升 95%+ 路由準確度。
    """

    def __init__(self, project_root: str, skills_root: str = "skills", run_dir: Optional[str] = None):
        self.project_root = Path(project_root)
        self.run_dir = Path(run_dir) if (run_dir and str(run_dir) != "None") else None
        # 核心職能來源改為從 inventory 動態讀取
        self.skills_root = Path(skills_root)
        self.builtin_skills_root = self.project_root / "scripts" / "skills_builtin"
        self.external_skills_root = self.project_root / "scripts"
        
        # 載入技能庫清單 (Skills Inventory)
        self.inventory_path = self.project_root / "scripts" / "skills_inventory.json"
        self.inventory = {}
        if self.inventory_path.exists():
            try:
                self.inventory = json.loads(self.inventory_path.read_text())
            except Exception as e:
                logger.debug("router inventory parse error: %s", e)

        # 載入自學習權重 (Autonomic Weights)
        self.weights_path = self.project_root / "scripts" / "core" / "autonomic_weights.json"
        self.weights_config = self._load_weights()
        self._decision_seq = 0

    def _new_decision_id(self, phase: str, skill_id: str, context: Dict[str, Any]) -> str:
        self._decision_seq += 1
        task_id = str(context.get("task_id", "") or "")
        seed = f"{phase}|{skill_id}|{task_id}|{datetime.now(timezone.utc).isoformat()}|{self._decision_seq}"
        digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]
        return f"dec_{phase.lower()}_{digest}"

    def _resolve_skill_artifact(self, skill_id: str) -> Dict[str, Any]:
        """
        Resolve skill artifact path with deterministic priority:
        1) scripts/skills_builtin/<skill_id>/SKILL.md
        2) scripts/<skill_id>/SKILL.md
        """
        builtin_path = self.builtin_skills_root / skill_id / "SKILL.md"
        if builtin_path.exists():
            return {
                "skill_path": str(builtin_path),
                "skill_source": "builtin",
                "artifact_found": True,
            }

        external_path = self.external_skills_root / skill_id / "SKILL.md"
        if external_path.exists():
            return {
                "skill_path": str(external_path),
                "skill_source": "external",
                "artifact_found": True,
            }

        return {
            "skill_path": str(builtin_path),
            "skill_source": "missing",
            "artifact_found": False,
        }

    def _load_weights(self) -> Dict[str, Any]:
        """從 JSON 載入權重，若失敗則回傳預設值。"""
        defaults = {
            "base_weights": {
                "tdd_weight": 2.5,
                "subagent_bias": 1.8,
                "refactor_weight": 3.0,
                "investigate_weight": 4.5
            },
            "skill_adjustments": {}
        }
        if self.weights_path.exists():
            try:
                return json.loads(self.weights_path.read_text())
            except Exception:
                return defaults
        return defaults

    def _calculate_weights(self, phase: str, context: Dict[str, Any]) -> float:
        """執行動態權重體系計算。"""
        weights = self.weights_config.get("base_weights", {})
        adjustments = self.weights_config.get("skill_adjustments", {})
        
        score = 0.0
        
        # 1. TDD 權重
        is_repair = phase == "R"
        has_tests = any("test" in f.lower() for f in context.get("files", []))
        if is_repair or has_tests:
            score += float(weights.get("tdd_weight", 2.5))
            
        # 2. Subagent 偏置
        files_count = len(context.get("files", []))
        is_large_task = files_count > 5 or len(context.get("steps_history", [])) > 3
        if is_large_task:
            score += float(weights.get("subagent_bias", 1.8))
            
        # 3. 任務類別權重
        task_id_lower = context.get("task_id", "").lower()
        is_refactoring = any(kw in task_id_lower for kw in ["refactor", "migration"])
        is_investigating = any(kw in task_id_lower for kw in ["investigate", "leak", "scan", "audit"])
        
        if is_refactoring:
            score += float(weights.get("refactor_weight", 3.0))
        if is_investigating:
            score += float(weights.get("investigate_weight", 4.5))

        # 4. 技能特徵加權 (自學習補強)
        # 如果 context 中有暗示特定術語，命中調整表
        for skill_key, bonus in adjustments.items():
            if skill_key.lower() in task_id_lower:
                score += float(bonus)
            
        return score

    def route(self, phase: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """傳統單一路由介面 (回傳 Top-1)。"""
        candidates = self.route_candidates(phase, context)
        return candidates[0] if candidates else {}

    def generate_scorecard(self, skill_id: str, phase: str, context: Dict[str, Any], info: Dict[str, Any]) -> Dict[str, Any]:
        """
        🚀 Nexus v9: Scorecard Generation
        產出透明的技能評分表。
        """
        task_id_lower = context.get("task_id", "").lower()
        
        # 基礎分與情境分
        base_score = 1.0
        trigger_score = 0.0
        for trigger in info.get("triggers", []):
            if trigger.lower() in task_id_lower:
                trigger_score += 2.0
                
        env_score = float(self._calculate_weights(phase, context))
        final_score = round(float(base_score + trigger_score + env_score), 2)
        
        return {
            "skill_id": skill_id,
            "final_score": final_score,
            "breakdown": {
                "base": base_score,
                "triggers": trigger_score,
                "environment": env_score
            },
            "status": "SELECTED" if final_score >= 4.0 else "REJECTED",
            "reason": "Meets threshold" if final_score >= 4.0 else "Below quality threshold (4.0)"
        }

    def save_decision_log(self, phase: str, selected: Dict[str, Any], rejected: List[Dict[str, Any]]):
        """💾 v9: 持久化紀錄路由決策與評分表。"""
        # Phase C: 產物收斂，優先使用 run_dir
        if self.run_dir:
            log_file = self.run_dir / "router_decisions.jsonl"
        else:
            log_file = self.project_root / "scripts/core/router_decisions.jsonl"
            
        log_file.parent.mkdir(parents=True, exist_ok=True)
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "phase": phase,
            "decision_id": selected.get("decision_id"),
            "selected_skill": selected.get("skill_id"),
            "score": selected.get("score"),
            "scorecard": selected.get("scorecard"),
            "rejections_count": len(rejected),
            "rejected_samples": (rejected or [])[:3]
        }
        with open(log_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def route_candidates(self, phase: str, context: Any = None, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        🚀 Nexus v9 Fallback Route (Hardened)
        回傳符合階段的所有候選技能，並附帶 Scorecard 與 Rejected 清單。
        """
        context_dict = {"task_id": context} if isinstance(context, str) else (context or {})
        
        candidates, rejected = self._collect_candidates(phase, context_dict)
        top_candidates = self._rank_and_augment_candidates(phase, context_dict, candidates, rejected, top_k)
        
        # 💾 v9: 自動持久化存檔決策 (即便沒選中也要紀錄)
        self.save_decision_log(phase, top_candidates[0] if top_candidates else {"skill_id": "NONE"}, rejected)
        return top_candidates

    def _collect_candidates(self, phase: str, context_dict: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        skills_data = self.inventory.get("skills", {})
        candidates = []
        rejected = []
        
        for skill_id, info in skills_data.items():
            if phase not in info.get("phases", []):
                continue
                
            scorecard = self.generate_scorecard(skill_id, phase, context_dict, info)
            artifact = self._resolve_skill_artifact(skill_id)
            
            candidate = {
                "skill_id": skill_id,
                "score": scorecard["final_score"],
                "scorecard": scorecard,
                "decision_id": self._new_decision_id(phase, skill_id, context_dict),
                "description": info.get("description", ""),
                "skill_path": artifact["skill_path"],
                "skill_source": artifact["skill_source"],
                "artifact_found": artifact["artifact_found"],
            }
            
            if scorecard["status"] == "SELECTED" and artifact["artifact_found"]:
                candidates.append(candidate)
            else:
                rejected.append({
                    "skill_id": skill_id,
                    "reason": "Skill artifact missing" if not artifact["artifact_found"] else scorecard["reason"],
                    "score": scorecard["final_score"]
                })
        return candidates, rejected

    def _rank_and_augment_candidates(self, phase: str, context_dict: Dict[str, Any], candidates: List[Dict[str, Any]], rejected: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = candidates[:top_k]
        
        for c in top_candidates:
            c["phase"] = phase
            c["rejected_candidates"] = (rejected or [])[:5]
            c["decision_tree"] = {
                "selected": c.get("skill_id", "NONE"),
                "rejections_count": len(rejected or []),
                "scorecard_summary": c["scorecard"].get("breakdown", {}) if c.get("scorecard") else {}
            }
        return top_candidates
