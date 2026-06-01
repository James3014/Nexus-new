import json
import logging
import hashlib
from typing import List, Dict, Any, Optional
from pathlib import Path

from nexus.research.findings_memory import FindingsMemoryStore, FindingsCard
from nexus.learning.skill_registry import SkillRegistry
from nexus.learning.skill_schema import SkillFrontmatter, SkillSuccessMetric
from nexus.research.wisdom.wisdom_vault import WisdomVault

logger = logging.getLogger(__name__)

class FindingsDistiller:
    """
    🔬 FindingsDistiller (v24.5)
    將 FindingsCard (含 BattleSwarm 結果) 自動轉化為 SkillRegistry 技能
    """

    def __init__(self, findings_store: FindingsMemoryStore, skill_registry: SkillRegistry, wisdom_vault: Optional[WisdomVault] = None, score_threshold: float = 7.0):
        self.findings_store = findings_store
        self.skill_registry = skill_registry
        self.wisdom_vault = wisdom_vault
        self.score_threshold = score_threshold

    def distill_batch(self, scope: str = "task", limit: int = 50) -> List[str]:
        """批次蒸餾流程"""
        try:
            cards = self.findings_store.list_recent(scope=scope, kind="episodes", limit=limit)
        except Exception as e:
            logger.error(f"⚠️ [Distiller] Search failed: {e}")
            cards = []
            
        distilled_ids = []
        for card in cards:
            score = float(card.extra.get("audit_score", 0.0)) if card.extra else 0.0
            
            if score < self.score_threshold:
                continue
                
            # 計算去重用的 fingerprint
            fingerprint = self._generate_fingerprint(card)
            skill_id = f"battle-{fingerprint}"
            
            if self.skill_registry.get_by_task_id(skill_id):
                continue # 已蒸餾過
                
            hypothesis = self._build_hypothesis(card)
            if not hypothesis:
                continue

            languages, file_patterns = self._extract_skill_frontmatter(card)
            
            win_rate = score / 10.0
            
            metric = SkillSuccessMetric(repair_success=True, retry_count=0, success_rate=win_rate)
            frontmatter = SkillFrontmatter(
                name=f"Auto-distilled from {card.title}",
                description=hypothesis[:200],
                task_id=skill_id,
                success_metric=metric,
                winning_hypothesis=hypothesis,
                languages=languages,
                file_patterns=file_patterns,
                win_rate=win_rate
            )
            
            try:
                self.skill_registry.upsert(frontmatter)
                success = True
            except Exception as e:
                logger.error(f"Upsert failed: {e}")
                success = False
            
            if success:
                distilled_ids.append(skill_id)
                card.tags.append("distilled:true")
                self.findings_store.write(card) # Update tag

                # 同步寫入 WisdomVault
                if self.wisdom_vault:
                    try:
                        self._ingest_to_wisdom(card, score)
                    except Exception as e:
                        logger.warning(f"⚠️ [Distiller] WisdomVault ingest failed: {e}")

        logger.info(f"🧪 [Distiller] Successfully distilled {len(distilled_ids)} new skills.")
        return distilled_ids

    def distill_battle_results(self, battle_result: dict, task_id: str) -> Optional[str]:
        """即時蒸餾 BattleSwarm 結果"""
        if battle_result.get("status") != "winner_found":
            return None
            
        winner = battle_result.get("winner", {})
        strategy = winner.get("strategy", "unknown")
        score = winner.get("score", 0.0)
        params = winner.get("params", {})
        
        fingerprint_source = f"{task_id}-{strategy}"
        fingerprint = hashlib.md5(fingerprint_source.encode()).hexdigest()[:8]
        skill_id = f"battle-{strategy}-{fingerprint}"
        
        prompt_modifier = params.get("prompt_modifier", "") if params else ""
        temperature = params.get("temperature") if params else "auto"
        top_p = params.get("top_p") if params else "auto"

        hypothesis = f"# Winning Strategy: {strategy}\\n"
        if prompt_modifier:
            hypothesis += f"## Strategy Modifiers\\n{prompt_modifier}\\n"
        hypothesis += f"## Parameters\\n- Temperature: {temperature}\\n- Top p: {top_p}\\n"

        languages = [winner.get("language", "unknown")]
        file_patterns = winner.get("file_patterns", [])

        win_rate = score / 10.0
        metric = SkillSuccessMetric(repair_success=True, retry_count=0, success_rate=win_rate)
        frontmatter = SkillFrontmatter(
            name=f"Immediate battle winner for {task_id}",
            description=hypothesis[:200],
            task_id=skill_id,
            success_metric=metric,
            winning_hypothesis=hypothesis,
            languages=languages,
            file_patterns=file_patterns,
            win_rate=win_rate
        )

        try:
            self.skill_registry.upsert(frontmatter)
            return skill_id
        except Exception:
            return None

    def _extract_skill_frontmatter(self, card: FindingsCard) -> tuple[List[str], List[str]]:
        """從 FindingsCard.tags 推斷語言和檔案模式"""
        languages = [t.split(":")[1] for t in card.tags if t.startswith("lang:")]
        file_patterns = [t.split(":")[1] for t in card.tags if t.startswith("file:")]
        return languages, file_patterns

    def _build_hypothesis(self, card: FindingsCard) -> str:
        """從高分 FindingsCard 提取可複用的解法假說"""
        extra = card.extra or {}
        params = extra.get("suggested_params", {})
        if params:
            return f"# Optimized via Bayesian\n```json\n{json.dumps(params, indent=2)}\n```\n{card.body}"
        return str(card.body)[:500] if card.body else ""

    def _generate_fingerprint(self, card: FindingsCard) -> str:
        """用 task_id 和 strategy 產生 unique id"""
        strategy = "unknown"
        for t in card.tags:
            if t.startswith("strategy:"):
                strategy = t.split(":")[1]
                break

        fingerprint_source = f"{card.task_id}-{strategy}"
        return hashlib.md5(fingerprint_source.encode()).hexdigest()[:8]
        
    def _ingest_to_wisdom(self, card: FindingsCard, score: float):
        """同步寫入 LanceDB 以供後續語義查詢"""
        task_content = f"[Swarm Episode] {card.title}"
        resolution_content = f"Result: {card.body}\nAudit Score: {score}\nTask ID: {card.task_id}"
        
        batch_data = [{
            "task": task_content,
            "resolution": resolution_content,
            "vector": self.wisdom_vault.model.encode(task_content).tolist()
        }]
        
        try:
            table = self.wisdom_vault.db.open_table(self.wisdom_vault.table_name)
            table.add(batch_data)
        except Exception:
            self.wisdom_vault.db.create_table(self.wisdom_vault.table_name, data=batch_data)
        logger.info(f"✅ [Distiller] Ingested {card.id} into WisdomVault.")
