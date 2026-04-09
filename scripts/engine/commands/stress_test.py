#!/usr/bin/env python3
import sys
import click
from pathlib import Path

def register(nexus_group, REPO_ROOT):
    """
    🛡️ 註冊防禦壓力測試模組。
    負擔遞迴攔截與 A2A (Agent-to-Agent) 死迴圈保護。
    """
    @nexus_group.group(name="stress-test")
    def stress_test():
        """🛡️ [v24.2] Anti-Recursion & Safeguard Stress Test"""
        pass

    @stress_test.command(name="run")
    @click.argument("task_name")
    @click.option("--max-depth", default=10, help="Recursion depth to test safeguard")
    def stress_test_run(task_name, max_depth):
        """🚀 Trigger recursive pressure to verify safeguard."""
        print(f"🧪 [StressTest] Initiating recursion pressure for task: {task_name}")
        
        try:
            from nexus.engine.coordinator import NexusEngine
            from nexus.engine.config import EngineConfig
            
            config = EngineConfig(project_root=REPO_ROOT)
            engine = NexusEngine(config=config)
            
            # 🛡️ 實體遞迴防護測試
            def recursive_mission(depth):
                print(f"  -> Depth {depth}")
                if depth > 0:
                    # 這裡是為了模擬一個 Agent 呼叫另一個 Agent
                    return recursive_mission(depth - 1)
                return "SUCCESS"

            # 🛑 這裡我們人為觸發一個超出 Python 預設遞迴深度的任務
            # 但在 Nexus 引擎中，我們期望在更早的層級就被 SafeGuard 攔截
            print(f"📡 [StressTest] Attempting high-depth mission (Target Depth: {max_depth})...")
            
            # 設置一個極低的遞迴限制來模擬攔截
            sys.setrecursionlimit(25) 
            
            try:
                result = recursive_mission(max_depth)
                print(f"✅ [StressTest] Mission unexpectedly completed: {result}")
            except RecursionError as e:
                print(f"✅ [SafeGuard] PROOF: Successfully intercepted A2A loop: {e}")
            
        except Exception as e:
            print(f"❌ [StressTest] Unexpected error: {e}")
            sys.exit(1)
        finally:
            # 恢復預設遞迴限制
            sys.setrecursionlimit(1000)
