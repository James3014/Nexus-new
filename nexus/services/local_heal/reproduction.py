import subprocess
import os
import re
from pathlib import Path
from typing import Tuple

class ReproductionRunner:
    """🧪 ReproductionRunner: 負責建立物理失敗證據"""
    def __init__(self, repo_dir: Path):
        self.repo_dir = repo_dir

    @staticmethod
    def clean_repro_script(script: str) -> str:
        lines = script.splitlines()
        cleaned = []
        in_fence = False
        for line in lines:
            if line.strip().startswith("```"):
                in_fence = not in_fence
                continue
            if in_fence or line.strip():
                cleaned.append(line)
        return "\n".join(cleaned).strip()

    def generate_repro_script(self, problem: str) -> str:
        # 當前版本暫由外部注入或作為 stub
        return ""

    def run_repro(self, script_code: str) -> Tuple[bool, str]:
        if not script_code: return False, "No repro script."
        script_code = self.clean_repro_script(script_code)
        repro_path = self.repo_dir / "reproduce_bug.py"
        try:
            repro_path.write_text(script_code, encoding="utf-8")
            env = os.environ.copy()
            env["PYTHONPATH"] = f"{str(self.repo_dir)}:{env.get('PYTHONPATH', '')}"
            res = subprocess.run(["python3", "reproduce_bug.py"], cwd=str(self.repo_dir), capture_output=True, text=True, timeout=30, env=env)
            if res.returncode != 0:
                return True, res.stderr if res.stderr else res.stdout
            return False, "Exited with code 0."
        except Exception as e:
            return False, str(e)
        finally:
            if repro_path.exists():
                try: os.remove(repro_path)
                except: pass
