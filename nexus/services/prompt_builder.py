from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import json
import yaml
import hashlib
from nexus.core.capability_gate import CapabilityGate

class PromptBuilder:
    """
    🪄 Nexus PromptBuilder Service
    負責隔離「模型咒語」與「程式邏輯」，實現 Prompt 的集中化、模板化與動態注入。
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.config_path = self.project_root / "nexus" / "config" / "models.yaml"
        # P1-D: Updated lesson source to structured JSONL
        self.lesson_path = self.project_root / ".nexus" / "knowledge" / "lesson_events.jsonl"
        
        # 內建核心規制 (原本在 ContextHub)
        self.NEXUS_PRIMER = {
            "constitutional_rules": [
                "P: Plan MUST be atomic and measurable.",
                "D: Diagnosis MUST focus on failure signatures, not just stack traces.",
                "R: Repair MUST be minimal; no unrelated refactor.",
                "A: Audit MUST prove the fix with unit/e2e tests.",
            ],
            "logic_guard": [
                "DO NOT modify files outside the provided hotspots",
                "STRICTLY follow the defined TDD cycle (RED-GREEN-REFACTOR)",
            ]
        }
        # 🟢 P3: SolidPrefixProtocol (Byte Cache)
        self.prefix_hash = hashlib.sha256(json.dumps(self.NEXUS_PRIMER).encode()).hexdigest()[:16]

    def _load_config(self) -> Dict[str, Any]:
        """載入 models.yaml 配置。"""
        if not self.config_path.exists():
            return {"models": {}}
        with open(self.config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _get_lessons_v22(self, task: str) -> Dict[str, Any]:
        """使用 P1-D 檢索服務提取教訓。"""
        from nexus.services.lesson_retrieval import (
            retrieve_relevant_lessons,
            inject_lesson_context,
        )

        retrieved = retrieve_relevant_lessons(self.lesson_path, task)
        # 模擬一個空的 state 以使用 inject_lesson_context
        dummy_state = {"metadata": {}}
        dummy_state, _ = inject_lesson_context(dummy_state, retrieved)
        return dummy_state["metadata"].get("retrieved_lessons", {})

    def _get_consensus_feedback(self, task_id: str) -> str:
        """從 .nexus/consensus/feedback.json 提取回饋 (v23 Eternal)"""
        feedback_path = self.project_root / ".nexus" / "consensus" / "feedback.json"
        if not feedback_path.exists():
            return ""
            
        try:
            feedbacks = json.loads(feedback_path.read_text())
            # 過濾當前任務的最近 3 筆回饋
            relevant = [f for f in feedbacks if f.get("task_id") == task_id]
            if not relevant:
                return ""
                
            feedback_str = "⚠️ [Physical Veto Detected] Your previous attempts were REJECTED by the Physical Auditor.\n"
            for i, f in enumerate(relevant[-3:]):
                feedback_str += f"\n- Round {i+1} Reason: {f['reason']}\n  Suggestion: {f['suggestion']}\n"
            
            return feedback_str
        except Exception:
            return ""

    def build_system_prompt(self, phase: str, model_hint: str = "flash") -> str:
        """建立系統層級的指導 Prompt (含教育模式)"""
        primer_section = "\n".join([f"  - {r}" for r in self.NEXUS_PRIMER["constitutional_rules"]])
        guard_section = "\n".join([f"  - {g}" for g in self.NEXUS_PRIMER["logic_guard"]])
        
        gate = CapabilityGate()
        tools_info = gate.build_tools_json(phase)
        tools_section = f"Available Tools (Current Phase: {phase}):\n" + \
                        "\n".join([f"  - {t}" for t in tools_info["available_tools"]])
        
        return f"""### [Nexus v23 Constitution]
Phase: {phase}
Rules:
{primer_section}

### [Safety Guards]
{guard_section}

### [Capability Gate]
{tools_section}
"""

    def build_task_prompt(self, task: str, context_brief: str, task_id: str = "unknown", model_hint: str = "flash") -> str:
        """組裝任務指令並注入橋接回饋。"""
        config = self._load_config()
        hint_key = "gemini_flash" if model_hint == "flash" else "claude_sonnet"
        model_cfg = config.get("models", {}).get(hint_key, {})
        
        template = model_cfg.get("template", "[Nexus Task]\nTask: [Nexus Task]")
        
        # 1. 注入 Lessons (成功經驗 - P1-D 升級版)
        retrieved_data = self._get_lessons_v22(task)
        lesson_str = retrieved_data.get("prompt_context", "None")
        
        # 2. 注入 Physical Feedback (失敗教訓)
        feedback_str = self._get_consensus_feedback(task_id)
        
        # 3. 組合最終 Prompt
        physical_section = f"\n### [Physical Feedback: VETOED]\n{feedback_str}" if feedback_str else ""
        
        prompt = template.replace("[Nexus Task]", 
                                 f"{task}{physical_section}\n\n### [Crystal Lessons]\n{lesson_str}\n\n### [Context Brief]\n{context_brief}")
        return prompt

    def build_full_payload(self, phase: str, task: str, diff: str, task_id: str = "unknown", model_hint: str = "flash") -> str:
        """生成完整字串。"""
        system = self.build_system_prompt(phase, model_hint)
        task_p = self.build_task_prompt(task, "N/A", task_id, model_hint)
        
        header = f"CACHE_KEY: {self.prefix_hash}\n"
        return f"{header}{system}\n\n{task_p}\n\n### [Code Diff / State]\n{diff}"

