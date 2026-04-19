import subprocess
import hashlib
import time
import sys
import os
from pathlib import Path
from typing import Dict, List, Any

class ReplayRunner:
    """
    Stage 2: Physical Replay Runner.
    執行實體命令對質，不接受 Agent 的口頭自述。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        
    def run_replay(self, bundle: Dict[str, Any]) -> Dict[str, Any]:
        """
        重跑 evidence bundle 中所列的 test_artifacts。
        """
        replay_results = []
        overall_passed = True
        
        test_artifacts = bundle.get("test_artifacts", [])
        if not test_artifacts:
            return {
                "status": "SKIPPED",
                "reason": "no_test_artifacts_to_replay",
                "passed": True,
                "replay_count": 0
            }
            
        for spec in test_artifacts:
            cmd = spec.get("command")
            expected_rc = spec.get("exit_code", 0)
            expected_hash = spec.get("output_hash")
            
            start_time = time.time()
            try:
                result = subprocess.run(
                    cmd, shell=True, cwd=self.project_root,
                    capture_output=True, text=True, timeout=60
                )
                duration = int((time.time() - start_time) * 1000)
                
                # 計算輸出 hash (簡化版：只針對 stdout)
                actual_hash = hashlib.sha256(result.stdout.encode()).hexdigest()
                
                match_rc = (result.returncode == expected_rc)
                match_hash = (actual_hash == expected_hash) if expected_hash else True
                
                item_passed = match_rc and match_hash
                if not item_passed:
                    overall_passed = False
                    
                replay_results.append({
                    "command": cmd,
                    "actual_exit_code": result.returncode,
                    "expected_exit_code": expected_rc,
                    "actual_hash": actual_hash,
                    "expected_hash": expected_hash,
                    "match_rc": match_rc,
                    "match_hash": match_hash,
                    "duration_ms": duration,
                    "passed": item_passed
                })
            except Exception as e:
                overall_passed = False
                replay_results.append({
                    "command": cmd,
                    "error": str(e),
                    "passed": False
                })
                
        return {
            "status": "COMPLETED" if overall_passed else "FAILED",
            "passed": overall_passed,
            "replay_results": replay_results,
            "replay_count": len(replay_results),
            "env_info": {
                "python": sys.version,
                "platform": sys.platform,
                "cwd": os.getcwd()
            }
        }
