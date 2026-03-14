from pathlib import Path
from core.state_io import StateIO
from core.skills_router import SkillsRouter
from core.context_hub import ContextHub


class Commander:
    """
    🕹️ Nexus Commander
    負責 Phase 導航 (State Transition) 與 Orchestration。
    """

    def __init__(self, run_dir: str):
        self.run_dir = Path(run_dir)
        self.project_root = self.run_dir.parents[1] if ".runs" in str(self.run_dir) else self.run_dir
        self.state_io = StateIO(run_dir)
        self.router = SkillsRouter(project_root=str(self.project_root))
        self.hub = ContextHub(self.project_root)

    def next_step(self) -> str:
        """核心狀態機：根據當前狀態與計畫，決定下一步動作。"""
        state = self.state_io.load_global_state()
        print(
            f"🧭 [Commander] Current state: {state.current_phase}:{state.current_step_id or 'none'}"
        )

        # 🛡️ External Needed Hook (Lesson from 09_STATE_CONTRACT_DRAFT)
        if state.external_needed:
            print("🌐 [Commander] External knowledge requested (X-stage).")
            return "RUN_SKILL:external-research"

        # 🛡️ 狀態轉移矩陣 (符合 02_TARGET_ARCHITECTURE)
        if state.current_phase == "P":
            return self._orchestrate_p(state)
        elif state.current_phase == "D":
            return self._orchestrate_d(state)
        elif state.current_phase == "R":
            return self._orchestrate_r(state)

        return "STALL"

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
        print(
            f"🔗 [Commander] CLI Command '{args.get('command')}' has been mapped to NexusState."
        )
        return self.next_step()
