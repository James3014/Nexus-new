from pathlib import Path
from nexus.core.state_io import StateIO
from nexus.core.router import SkillsRouter
from nexus.core.context_hub import ContextHub


class Commander:
    """
    🕹️ Nexus Commander
    負責 Phase 導航 (State Transition) 與 Orchestration。
    """

    def __init__(self, run_dir: str, state_io=None, router=None, context_hub=None):
        self.run_dir = Path(run_dir)
        self.project_root = self.run_dir.parents[1] if ".runs" in str(self.run_dir) else self.run_dir
        self.state_io = state_io
        self.router = router
        self.hub = context_hub

    def next_step(self) -> str:
        """核心狀態機：根據當前狀態與計畫，決定下一步動作。"""
    def next_step(self, status: str, metadata: Optional[Dict] = None, summary: Optional[str] = None):
        """🧬 狀態自動機切換門檻"""
        state = self.state_io.load_global_state()
        from nexus.core.crystal_analyzer import TraumaEngine

        print(
            f"🧭 [Commander] Current state: {state.current_phase}:{state.current_step_id or 'none'}"
        )

        # 🧪 C 階段: 創傷捕捉 + 記憶與學習 v2 (Episode 紀錄)
        if state.current_phase == "C" or status == "completed":
            from nexus.core.policy_manager import PolicyManager
            pm = PolicyManager(self.project_root)
            
            TraumaEngine.process_failures(state)
            pm.record_episode(state) # 🔄 M1: record_episode
            
            # 每 10 回合壓縮一次記憶 (PHA-041)
            if len(state.steps_history) % 10 == 0:
                 import subprocess
                 subprocess.run(["uv", "run", "scripts/ops/flash_ingest.py"], capture_output=True)

        # 🛡️ External Needed Hook (Lesson from 09_STATE_CONTRACT_DRAFT)
        if state.external_needed:
            print("🌐 [Commander] External knowledge requested (X-stage).")
            return "RUN_SKILL:external-research"

        # 🛡️ Phase Health Autonomy (PHA-001): 執行前先更新與保存健康度
        from nexus.core.phase_health import PhaseHealthCalculator
        from nexus.core.auto_repair import AutoRepairEngine
        PhaseHealthCalculator.update_state(state)
        AutoRepairEngine.execute_repairs(state)
        self.state_io.save_global_state(state)

        # 🛡️ 狀態轉移矩陣 (符合 02_TARGET_ARCHITECTURE)
        if state.current_phase == "P":
            return self._orchestrate_p(state)
        elif state.current_phase == "D":
            return self._orchestrate_d(state)
        elif state.current_phase == "R":
            return self._orchestrate_r(state)

        return "STALL"

    def get_crystal_lessons(self, relevance: float = 0.8) -> list[str]:
        """從 CrystalAnalyzer 獲取相關性高於閾值的經驗結晶。"""
        # 實戰中會對接 LancedB 或 Tracelog 語義檢索
        return ["Avoid circular imports in nexus.core", "Use pydantic model_dump for state serialization"]

    def _orchestrate_p(self, state):
        """P 階段：計畫生成 (對焦 v5 writing-plans)"""
        print("🚀 [Commander] Triggering P-stage: Skills Routing...")
        return "RUN_SKILL:writing-plans"

    def _orchestrate_d(self, state):
        """D 階段：診斷 (對焦 systematic-debugging)"""
        print("🚀 [Commander] Triggering D-stage: Analysis...")
        return "RUN_SKILL:systematic-debugging"

    def _orchestrate_r(self, state):
        """R 階段：修復 (對接 v5 repair)"""
        print("🛠️ [Commander] Triggering R-stage: Execution...")
        return "RUN_SKILL:repair"

    def handle_nexus_command(self, args: dict):
        """🧬 Nexus v7: 映射 CLI 命令至 NexusState"""
        state = self.state_io.load_global_state()
        state.current_phase = "P"
        state.task_id = args.get("task", "")
        # 加入 v7 特有元數據
        state.metadata["v7_triggered"] = True
        state.metadata["command"] = args.get("command")

        self.state_io.save_global_state(state)
        return self.next_step()

    def crystallize(self, state):
        """🧬 Phase C: 結晶化 (符合 2026-03-18_Nexus_記憶與學習v2)"""
        print(f"💎 [Commander] Crystallizing lessons for task: {state.task_id}")
        # 保存至 crystal_lessons.jsonl
        try:
            lesson = {
                "task_id": state.task_id,
                "status": "success",
                "phases": [h.phase for h in state.steps_history],
                "health": state.health_score
            }
            lessons_path = self.project_root / "crystal_lessons.jsonl"
            import json
            with open(lessons_path, "a") as f:
                f.write(json.dumps(lesson) + "\n")
        except Exception as e:
            print(f"⚠️ [Crystallize] Failed to save lesson: {e}")
