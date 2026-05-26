from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CapabilitySignalSet:
    """Rigorous snapshot representing all input signals evaluated by the Selector."""

    task_id: str
    task_desc: str
    risk_level: str  # 'LOW', 'NORMAL', 'HIGH', 'CRITICAL'
    impact_complexity: float  # Scale 0.0 to 5.0 derived from JIT impact or codebase size
    belief_confidence: float  # Scale 0.0 to 1.0 retrieved from BeliefEngine
    skills_triggered: List[str]  # Raw skill IDs matching baseline keywords
    tenant_id: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_context(
        cls,
        context: Dict[str, Any],
        project_root: str,
        belief_engine: Optional[Any] = None,
    ) -> CapabilitySignalSet:
        """Deterministically extract and assemble the SignalSet snapshot from runtime context."""
        task_id = str(context.get("task_id", context.get("task_desc", "default_task")))
        task_desc = str(context.get("task_desc", context.get("query", "")))
        tenant_id = str(context.get("tenant_id", "default"))
        risk_level = str(context.get("risk_level", "NORMAL")).upper()
        if risk_level not in ("LOW", "NORMAL", "HIGH", "CRITICAL"):
            risk_level = "NORMAL"

        # 1. 取得 Belief 信心度
        belief_confidence = 0.7
        if belief_engine and hasattr(belief_engine, "get_confidence"):
            try:
                belief_confidence = float(belief_engine.get_confidence(task_id, assumption=task_desc))
            except Exception:
                belief_confidence = 0.7

        # 1.1 [P12] 路由接 LanceDB & Memory 實體檢索 (FTS & 語意)
        # 如果檢索到歷史失敗案例，則進行信心度扣減
        memory_index_path = Path(project_root) / ".nexus" / "memory" / "memory_index.lancedb"
        if memory_index_path.exists():
            try:
                from nexus.services.memory_repository import MemoryRepository

                repo = MemoryRepository(memory_index_path)
                tables = repo.list_tables()
                if tables:
                    df = repo.search_fts_across_tables(task_desc, list(tables)[:3], limit=2)
                    if not df.empty:
                        records = df.to_dict(orient="records")
                        for rec in records:
                            content_str = str(rec.get("content", "")).lower()
                            if "fail" in content_str or "error" in content_str or "nameerror" in content_str:
                                belief_confidence = round(max(0.1, belief_confidence - 0.2), 4)
                                break
            except Exception:
                pass

        # 2. 自動分析 triggers 候選技能
        skills_triggered = []
        inventory_path = Path(project_root) / "scripts" / "skills_inventory.json"
        if inventory_path.exists():
            try:
                inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
                skills = inventory.get("skills", {}) or {}
                query_lower = task_desc.lower()
                for skill_id, meta in skills.items():
                    triggers = [str(t).lower() for t in (meta.get("triggers") or [])]
                    if any(t and t in query_lower for t in triggers):
                        skills_triggered.append(skill_id)
            except Exception:
                pass

        # 3. 取得 CodeIntel / JIT impact 複雜度
        impact_complexity = 1.0
        try:
            complexity_raw = context.get("impact_complexity") or context.get("complexity")
            if complexity_raw is not None:
                impact_complexity = max(0.0, min(5.0, float(complexity_raw)))
        except (ValueError, TypeError):
            impact_complexity = 1.0

        # 4. 解析 NEXUS_CAPABILITY_SKILL_MAP.md 以補齊 HEEP 活躍 Skills 訊號
        map_path = Path(project_root) / "docs" / "info" / "NEXUS_CAPABILITY_SKILL_MAP.md"
        if map_path.exists():
            try:
                content = map_path.read_text(encoding="utf-8")
                import re

                # 簡單提取所有 markdown 中包圍在 `` 內部的 primary skill 名稱
                primary_skills = re.findall(r"\|\s*`[^`\s]+`\s*\|\s*`([^`\s]+)`\s*\|", content)
                for skill in primary_skills:
                    if skill and skill not in skills_triggered:
                        skills_triggered.append(skill)
            except Exception:
                pass

        return cls(
            task_id=task_id,
            task_desc=task_desc,
            risk_level=risk_level,
            impact_complexity=impact_complexity,
            belief_confidence=belief_confidence,
            skills_triggered=skills_triggered,
            tenant_id=tenant_id,
            metadata=dict(context),
        )

