import json
import yaml
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional
from nexus.core.capability_gate import CapabilityGate

class PromptBuilder:
    """
    🪄 Nexus PromptBuilder Service
    負責隔離「模型咒語」與「程式邏輯」，實現 Prompt 的集中化、模板化與動態注入。
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.config_path = self.project_root / "nexus" / "config" / "models.yaml"
        self.lesson_path = self.project_root / "obsidian/crystal_lessons.jsonl"
        
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

    def _get_lessons(self, task: str) -> List[str]:
        """提取相關的經驗結晶 (Lessons)。"""
        if not self.lesson_path.exists():
            return []
        
        relevant = []
        try:
            with open(self.lesson_path, "r", encoding="utf-8") as f:
                for line in f:
                    l = json.loads(line)
                    if l.get("signature") in task or l.get("cause") in task:
                        relevant.append(f"- [{l['signature']}]: {l['lesson']}")
        except Exception:
            pass
        return relevant[:3]

    def build_system_prompt(self, phase: str, model_hint: str = "flash") -> str:
        """建立系統層級的指導 Prompt，並注入能力閘門工具清單。"""
        primer_section = "\n".join([f"  - {r}" for r in self.NEXUS_PRIMER["constitutional_rules"]])
        guard_section = "\n".join([f"  - {g}" for g in self.NEXUS_PRIMER["logic_guard"]])
        
        # 🛡️ P5.1: 注入動態能力閘門
        gate = CapabilityGate()
        tools_info = gate.build_tools_json(phase)
        tools_section = f"Available Tools (Current Phase: {phase}):\n" + \
                        "\n".join([f"  - {t}" for t in tools_info["available_tools"]])
        
        return f"""### [Nexus v22 Constitution]
Phase: {phase}
Rules:
{primer_section}

### [Safety Guards]
{guard_section}

### [Capability Gate]
{tools_section}
"""

    def build_task_prompt(self, task: str, context_brief: str, model_hint: str = "flash") -> str:
        """組裝具體的任務指令。"""
        config = self._load_config()
        hint_key = "gemini_flash" if model_hint == "flash" else "claude_sonnet"
        model_cfg = config.get("models", {}).get(hint_key, {})
        
        template = model_cfg.get("template", "[Nexus Task]\nTask: [Nexus Task]")
        
        # 1. 注入 Lessons
        lessons = self._get_lessons(task)
        lesson_str = "\n".join(lessons) if lessons else "None"
        
        # 2. 組合最終 Prompt
        prompt = template.replace("[Nexus Task]", f"{task}\n\n### [Crystal Lessons]\n{lesson_str}\n\n### [Context Brief]\n{context_brief}")
        return prompt

    def build_full_payload(self, phase: str, task: str, diff: str, model_hint: str = "flash") -> str:
        """生成最終發送給 LLM 的完整字串 (含 Byte Cache 標記)。"""
        system = self.build_system_prompt(phase, model_hint)
        task_p = self.build_task_prompt(task, "N/A", model_hint)
        
        # 🧼 P3: 注入 Solid Prefix 標記以觸發 Provider Cache
        header = f"CACHE_KEY: {self.prefix_hash}\n"
        return f"{header}{system}\n\n{task_p}\n\n### [Code Diff / State]\n{diff}"

