import os
import json
import subprocess
import concurrent.futures
import time
from pathlib import Path
from nexus.core.handoff_builder import HandoffBuilder

class SubAgentTimeoutError(Exception):
    pass

class SubAgentSpawner:
    """
    🚀 Nexus 平行分身生產器 (AOS-P5.3)
    負責在獨立 Worktree 中啟動具備治理盔甲的子代理。
    """
    
    def __init__(self, task_id: str = "swarm-task"):
        self.task_id = task_id
        self.handoff_builder = HandoffBuilder()

    def spawn(self, task: str, target_files: list, worktree: str, phase: str = "P") -> dict:
        """🎯 啟動單個穿甲分身並等待 JSON Outcome"""
        
        # 1. 準備穿甲環境變數
        armor_env = {
            "NEXUS_ENFORCED":   "true",
            "NEXUS_WORKTREE":   str(worktree),
            "NEXUS_PHASE_GATE": phase,
            "NEXUS_SCOPE":      json.dumps(target_files),
            "NEXUS_PARENT_ID":  self.task_id,
        }

        # 2. 建立 HandoffJSON 規約
        handoff = self.handoff_builder.build(
            task=task,
            scope=target_files,
            phase=phase,
            parent_id=self.task_id
        )

        try:
            # 3. 物理執行：使用 nexus:runner 啟動
            # 指令對齊: nexus_cli.py nexus:runner --handoff ...
            result = subprocess.run(
                ["uv", "run", "nexus_cli.py", "nexus:runner",
                 "--handoff", json.dumps(handoff),
                 "--enforce-governance",
                 "--worktree", str(worktree)],
                env={**os.environ, **armor_env},
                capture_output=True, 
                text=True, 
                timeout=300
            )

            if result.returncode != 0:
                # 🚨 啟動失敗或崩潰：物理回滾
                self._rollback(worktree)
                return {
                    "taskid": self.task_id,
                    "success": False,
                    "error": f"Sub-agent {self.task_id} 崩潰/退出碼 {result.returncode}.\nStderr: {result.stderr}"
                }

            # 4. 解析 OutcomePayload (分身只准回傳 JSON 到 stdout)
            # 注意：runner 目前只是 Mock，假設 stdout 包含補丁 JSON
            try:
                # 這裡假設分身最後一行輸出是 JSON 或整體是 JSON
                outcome = json.loads(result.stdout.strip().split("\n")[-1])
                return outcome
            except:
                return {
                    "taskid": self.task_id,
                    "success": False,
                    "error": "分身回傳格式錯誤：未檢出 OutcomePayload JSON。"
                }

        except subprocess.TimeoutExpired:
            # 🚨 超時：物理回滾防止污染
            self._rollback(worktree)
            raise SubAgentTimeoutError(f"分身 {self.task_id} 執行超時 (300s)，已執行強制回滾。")
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _rollback(self, worktree: str):
        """物理回滾 Worktree 狀態"""
        try:
            subprocess.run(["git", "reset", "--hard", "HEAD"], cwd=worktree, check=True)
            print(f"🔄 [Armor:Rollback] Worktree {worktree} rolled back due to failure.")
        except:
            pass

def run_parallel_agents(tasks, session_prefix="parallel_spawn"):
    if not tasks: return []
    print(f"🚀 [Spawning Engine] 正在啟動 {len(tasks)} 個平行分身 (穿甲監管模式)...")
    
    results = []
    spawner = SubAgentSpawner(task_id=session_prefix)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(tasks)) as executor:
        futures = [
            executor.submit(spawner.spawn, t["prompt"], t.get("scope", []), t.get("worktree", "./worktree"), t.get("phase", "P"))
            for t in tasks
        ]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
            
    return results

if __name__ == "__main__":
    # 測試注入
    test_tasks = [{"prompt": "fix typo", "scope": ["test.py"], "worktree": "/tmp/nexus_sub_1"}]
    print(run_parallel_agents(test_tasks))
