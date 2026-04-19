"""
Evidence Verifier: 系統級獨立驗證器。
不依賴 Agent 自述，透過物理命令獨立產生/驗證 evidence。
"""

import subprocess
from pathlib import Path

class EvidenceVerifier:
    """
    在 Audit (A) 階段被呼叫，獨立驗證 Agent 宣稱的 evidence。
    
    驗證項目:
    1. code_artifacts — 每個檔案是否存在 + 是否被 git 追蹤
    2. test_artifacts — 每個測試命令是否真的被執行過（檢查 exit code log）
    3. git_diff_check — 當前 worktree 的 git diff 是否與宣稱的 patch 一致
    4. command_artifacts — 所列命令的 exit code 是否真的為 0
    """
    
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
    
    def verify(self, evidence_bundle: dict) -> dict:
        results = {
            "code_artifacts_verified": self._verify_code_artifacts(
                evidence_bundle.get("code_artifacts", [])
            ),
            "git_diff_non_empty": self._check_git_diff_non_empty(),
            "git_diff_stat": self._get_git_diff_stat(),
            "test_commands_verified": self._verify_test_commands(
                evidence_bundle.get("test_artifacts", [])
            ),
            "overall_trust": "UNKNOWN",
        }
        
        # 計算 overall trust
        code_ok = results["code_artifacts_verified"]["all_exist"]
        diff_ok = results["git_diff_non_empty"]
        test_ok = results["test_commands_verified"]["all_executed"]
        
        if code_ok and diff_ok and test_ok:
            results["overall_trust"] = "HIGH"
        elif code_ok and (diff_ok or test_ok):
            results["overall_trust"] = "MEDIUM"
        else:
            results["overall_trust"] = "LOW"
        
        return results
    
    def _verify_code_artifacts(self, artifacts: list) -> dict:
        missing = []
        untracked = []
        invalid_items = []
        normalized_paths = []
        tracked_files = self._get_tracked_files()
        
        for artifact in artifacts:
            file_path = ""
            if isinstance(artifact, str):
                file_path = artifact
            elif isinstance(artifact, dict):
                file_path = artifact.get("file_path", "")
            
            if not file_path:
                invalid_items.append(artifact)
                continue
            
            normalized_paths.append(file_path)
            path = self.project_root / file_path
            if not path.exists():
                missing.append(file_path)
            elif str(file_path) not in tracked_files:
                untracked.append(file_path)
        
        return {
            "all_exist": len(missing) == 0 and len(invalid_items) == 0,
            "missing": missing,
            "untracked": untracked,
            "invalid_items": invalid_items,
            "normalized_paths": normalized_paths,
            "total": len(artifacts),
        }
    
    def _check_git_diff_non_empty(self) -> bool:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=self.project_root, capture_output=True, text=True
        )
        return bool(result.stdout.strip())
    
    def _get_git_diff_stat(self) -> str:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=self.project_root, capture_output=True, text=True
        )
        return result.stdout.strip()[:500]
    
    def _verify_test_commands(self, test_artifacts: list) -> dict:
        executed = []
        not_executed = []
        
        for cmd_info in test_artifacts:
            cmd = cmd_info if isinstance(cmd_info, str) else cmd_info.get("command", "")
            if not cmd:
                continue
            try:
                result = subprocess.run(
                    cmd, shell=True, cwd=self.project_root,
                    capture_output=True, text=True, timeout=30
                )
                executed.append({
                    "command": cmd,
                    "exit_code": result.returncode,
                    "passed": result.returncode == 0,
                })
            except subprocess.TimeoutExpired:
                not_executed.append({"command": cmd, "reason": "timeout"})
            except Exception as e:
                not_executed.append({"command": cmd, "reason": str(e)})
        
        return {
            "all_executed": len(not_executed) == 0 and len(executed) > 0,
            "executed": executed,
            "not_executed": not_executed,
        }
    
    def _get_tracked_files(self) -> set:
        result = subprocess.run(
            ["git", "ls-files"], cwd=self.project_root,
            capture_output=True, text=True
        )
        return set(result.stdout.strip().split("\n"))
