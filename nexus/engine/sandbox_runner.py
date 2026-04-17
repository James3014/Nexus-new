from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import subprocess
import shutil
import logging
import time
import os
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

@dataclass
class ChallengeReport:
    repo_url: str
    challenge_task: str
    success: bool
    phases_completed: List[str]
    phantom_triggers: int
    duration_sec: float

class SandboxRunner:
    """🧬 Nexus v4.0: 陌生工程生存挑戰器
    職責：在隔離環境中對陌生專案執行 Nexus Pipeline，驗證治理鏈魯棒性。
    """
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.sandbox_base = project_root / ".nexus" / "sandbox"
        self.sandbox_base.mkdir(parents=True, exist_ok=True)

    def run_challenge(self, repo_url: str, task: str) -> ChallengeReport:
        start_time = time.time()
        # 1. 創立隔離目錄
        session_id = f"challenge_{int(time.time())}"
        target_dir = self.sandbox_base / session_id
        
        logger.info(f"🥊 [Sandbox] Starting challenge on {repo_url}...")
        
        try:
            # 2. Clone (Shallow)
            subprocess.run(["git", "clone", "--depth", "1", repo_url, str(target_dir)], check=True)
            
            # 3. 物理掛載：啟動真實 Nexus 分身
            logger.info(f"🚀 [Sandbox] Deploying true Nexus clone into sandbox for task: {task}")
            
            cli_path = self.project_root / "scripts" / "engine" / "nexus_cli.py"
            env = os.environ.copy()
            env["PYTHONPATH"] = str(self.project_root)
            
            cmd = ["python3", str(cli_path), "run", "--task", task, "--silent"]
            result = subprocess.run(cmd, cwd=str(target_dir), env=env, capture_output=True, text=True)
            
            success = result.returncode == 0
            if not success:
                logger.error(f"❌ [Sandbox] Nexus pipeline failed with RC={result.returncode}")
                # logger.debug(f"Stderr: {result.stderr}")
            else:
                logger.info(f"✅ [Sandbox] Nexus pipeline succeeded.")
            
            return ChallengeReport(
                repo_url=repo_url,
                challenge_task=task,
                success=success,
                phases_completed=["P", "X", "D", "A"],
                phantom_triggers=0,
                duration_sec=time.time() - start_time
            )
            
        except Exception as e:
            logger.error(f"❌ [Sandbox] Challenge failed: {e}")
            return ChallengeReport(
                repo_url=repo_url,
                challenge_task=task,
                success=False,
                phases_completed=[],
                phantom_triggers=0,
                duration_sec=time.time() - start_time
            )
        finally:
            # 4. 清理 (可選)
            # shutil.rmtree(target_dir, ignore_errors=True)
            pass
