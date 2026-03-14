import json
import subprocess
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from core.state_contracts import NexusDiagnosis, NexusResearch
from core.state_io import StateIO


class ContextHub:
    """
    🧠 Nexus Context Hub
    負責收集、組裝與壓縮上下文，為 Agent 提供乾淨的 P-D-X-R-A-C 視圖。
    """

    # 🏆 Nexus Primer: v7 新域大師核心規制
    NEXUS_PRIMER = {
        "constitutional_rules": [
            "P: Plan MUST be atomic and measurable.",
            "D: Diagnosis MUST focus on failure signatures, not just stack traces.",
            "R: Repair MUST be minimal; no unrelated refactor.",
            "A: Audit MUST prove the fix with unit/e2e tests.",
        ],
        "top_patterns": {
            "FASTAPI_500": "Check dependency overrides and startup event order.",
            "PYTHON_IMPORT_ERR": "Scan for circular dependencies or missing PYTHONPATH.",
            "RACE_CONDITION": "Identify shared states and apply locks or atomic ops.",
        },
    }

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.state_io = StateIO(project_root)

    def _inject_memory_reminders(self, phase: str) -> Dict[str, Any]:
        """🔌 Hook: 呼叫 LogMemory Agent 取得 per-round 記憶。"""
        try:
            # 呼叫 scripts/logmemory.py (使用 uv run 以符合全域安全規則)
            uv_path = "/Users/jameschen/.local/bin/uv"
            cmd = [
                uv_path, "run", 
                "--with", "redis", 
                "--with", "lancedb", 
                str(self.project_root / "scripts/logmemory.py"), 
                "--phase", phase,
                "--cache"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=self.project_root)
            
            if result.returncode == 0:
                # 讀取產出的 reminders.json
                reminder_file = self.project_root / "reminders.json"
                if reminder_file.exists():
                    data = json.loads(reminder_file.read_text())
                    print(f"🧠 [MemoryHook] Injected {len(data.get('reminders', []))} reminders for phase {phase}")
                    return data
        except Exception as e:
            print(f"⚠️ [MemoryHook] Injection failed: {e}")
        return {"reminders": [], "total_sources": 0}

    def assemble_diag_pack(
        self, violations: List[Dict], summary: str
    ) -> Dict[str, Any]:
        """組裝診斷階段所需的 Context Pack。"""
        state = self.state_io.load_global_state()
        pack = {
            "task_id": state.task_id,
            "failure_summary": summary,
            "violations": violations[:10],  # 截斷以保持 token 效率
            "hotspots": list(set([v.get("file") for v in violations if v.get("file")])),
            "history_summary": [steps.summary for steps in state.steps_history[-3:]],
            "contract_version": "1.5.2",
            "memory_reminders": self._inject_memory_reminders("D")
        }
        return pack

    def assemble_research_pack(self, query: str, results: List[Dict]) -> Dict[str, Any]:
        """組裝研究階段所需的 Context Pack。"""
        return {
            "query": query,
            "results": results,
            "fact_count": len(results),
            "relevance_gate": True,
        }

    def assemble_repair_pack(
        self,
        diagnosis: NexusDiagnosis,
        reflections: List[Dict],
        research: Optional[NexusResearch] = None,
    ) -> Dict[str, Any]:
        """組裝修復階段所需的 Context Pack (對齊 v5+)。"""
        return {
            "root_cause": diagnosis.summary,
            "repair_strategy": diagnosis.pseudo_flows,
            "target_files": diagnosis.hotspots,
            "recent_reflections": reflections,
            "external_research": research.key_findings if research else [],
            "logic_guard": {
                "chain_of_thought": "Analyze logs → Plan minimal diff → Apply patch → Verify via Linter",
                "negative_constraints": [
                    "DO NOT modify files outside the provided hotspots",
                    "DO NOT introduce unrelated refactoring",
                    "STRICTLY follow the defined state contracts",
                ],
            },
            "memory_reminders": self._inject_memory_reminders("R")
        }

    def record_crystal_lesson(
        self, failure_signature: str, root_cause: str, lesson: str
    ):
        """💾 Phase 5: 記錄失敗案例用於 Active Learning。"""
        lesson_file = self.project_root / "obsidian/crystal_lessons.jsonl"
        lesson_file.parent.mkdir(parents=True, exist_ok=True)

        entry = {
            "timestamp": datetime.now().isoformat(),
            "signature": failure_signature,
            "cause": root_cause,
            "lesson": lesson,
            "recall_accuracy": 0.0,  # 初始準確度佔位
        }
        with open(lesson_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
        print(f"🧠 [ActiveLearning] Crystal Lesson recorded: {failure_signature}")
