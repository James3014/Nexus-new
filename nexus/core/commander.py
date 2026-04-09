from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from nexus.core.state_contracts import NexusState
from nexus.core.state_io import StateIO
from nexus.core.router import SkillsRouter
from nexus.core.context_hub import ContextHub
from nexus.health.service import SelfHealService


class Commander:
    """
    🕹️ Nexus Commander
    負責 Phase 導航 (State Transition) 與 Orchestration。
    """

    def __init__(self, run_dir: str, state_io=None, router=None, context_hub=None):
        self.run_dir = Path(run_dir).resolve()
        
        # 🛡️ 健全的專案根路徑偵測：跳過 .nexus 進入真正的專案根部
        curr = self.run_dir
        self.project_root = curr
        while curr.parent != curr:
            if (curr / ".git").exists():
                self.project_root = curr
                break
            if (curr / ".nexus").exists() and curr.name != ".nexus":
                self.project_root = curr
                break
            curr = curr.parent
            
        self.state_io = state_io
        self.router = router
        self.hub = context_hub
        self.self_heal_service = SelfHealService(self.project_root)

    def next_step(
        self,
        status: str = "running",
        metadata: Optional[Dict] = None,
        summary: Optional[str] = None,
        state: Optional[NexusState] = None,
    ):
        """🧬 狀態自動機切換門檻"""
        state = state or self.state_io.load_global_state()
        from nexus.core.crystal_analyzer import TraumaEngine

        print(
            f"🧭 [Commander] Current state: {state.current_phase}:{state.current_step_id or 'none'}"
        )

        # 🎯 P 階段: Policy 檢索與注入 (Week 2 M2)
        if state.current_phase == "P":
            from nexus.core.policy_manager import PolicyManager
            pm = PolicyManager(self.project_root)
            # 這裡需要傳入任務描述，假設從 state 或 manifest 取得
            descr = state.metadata.get("task_description", "")
            pm.apply_policy_to_state(state, descr)
            self.state_io.save_global_state(state)

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

        # 🛡️ Phase Health Autonomy (PHA-001): delegate health/self-heal to dedicated service.
        # Benchmarks must remain deterministic and must not trigger nested auto-repair task runners.
        if not state.metadata.get("benchmark_run"):
            self.self_heal_service.run_cycle(state)
            self.state_io.save_global_state(state)

        # 🛡️ 狀態轉移矩陣 (符合 02_TARGET_ARCHITECTURE)
        if state.current_phase == "P":
            return self._orchestrate_p(state)
        elif state.current_phase == "D":
            return self._orchestrate_d(state)
        elif state.current_phase == "R":
            return self._orchestrate_r(state)
        elif state.current_phase == "A":
            return self._orchestrate_a(state)

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
        
        # ⚓ [Phase 10] Universal ToolHook 管線
        from nexus.core.harness import default_director
        
        # 準備上下文
        harness_context = {
            "phase": "R",
            "budget_remaining": state.metadata.get("budget_token", 5000) - state.total_token_usage,
            "project_root": self.project_root,
        }
        
        tool_name = "repair" # 這裡是邏輯工具名
        args = state.metadata.get("next_params", {"target_file": state.metadata.get("target_file")})
        
        status, messages = default_director.run_pre_execute(tool_name, args, harness_context)
        
        if status == "BLOCKED":
            print(f"🛑 [Commander:HARNESS] Blocked! Reason: {'; '.join(messages)}")
            return "HARNESS_BLOCKED"
            
        if status == "WARN":
            print(f"⚠️ [Commander:HARNESS] Warning: {'; '.join(messages)}")
            
        return "RUN_SKILL:repair"

    def _orchestrate_a(self, state):
        """A 階段：審計 (對接 v22 Parity Audit)"""
        print("🔬 [Commander] Triggering A-stage: Phase Parity Audit...")
        from nexus.engine.phases.audit import AuditPhaseHandler
        handler = AuditPhaseHandler(self.project_root, self.project_root / ".nexus")
        res = handler.run(state)
        
        if res["status"] == "COMPLETED":
            state.current_phase = "C" # 轉導至結晶化 (C)
            self.state_io.save_global_state(state)
            return "SUCCESS"
        return "STALL"

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

    def handle_ink_input(self, ink_content: str):
        """🎨 P5.10: 處理 Ink 緊湊格式輸入"""
        from nexus.core.ink_parser import InkParser
        parser = InkParser()
        commands = parser.parse(ink_content)
        
        results = []
        for cmd in commands:
            formal = parser.to_formal(cmd)
            # 將正式指令轉發至處理器 (Mock)
            results.append(f"Executed {formal['tool']} for {formal['args'].get('path')}")
            
        return results
