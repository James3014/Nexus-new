"""CLI Pre-Gate：在 A 階段之前，用 exit code 做一次機械性驗證"""
import subprocess
import logging
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)

def run_cli_pregate(
    project_root: Path,
    commands: List[str],
    timeout_per_cmd: int = 60,
) -> Tuple[bool, List[dict]]:
    """
    執行驗證指令列表，回傳 (all_passed, results)
    
    results = [
        {"cmd": "pytest tests/", "exit_code": 0, "passed": True},
        {"cmd": "cargo test", "exit_code": 1, "passed": False, "stderr": "..."},
    ]
    """
    if not commands:
        return True, []
    
    results = []
    all_passed = True
    
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=timeout_per_cmd,
            )
            passed = proc.returncode == 0
            results.append({
                "cmd": cmd,
                "exit_code": proc.returncode,
                "passed": passed,
                "stdout_tail": proc.stdout[-500:] if proc.stdout else "",
                "stderr_tail": proc.stderr[-500:] if proc.stderr else "",
            })
            if not passed:
                all_passed = False
                logger.warning("❌ CLI Pre-Gate FAIL: %s (rc=%d)", cmd, proc.returncode)
            else:
                logger.info("✅ CLI Pre-Gate PASS: %s", cmd)
        except subprocess.TimeoutExpired:
            results.append({
                "cmd": cmd,
                "exit_code": 124,
                "passed": False,
                "stderr_tail": f"timeout after {timeout_per_cmd}s",
            })
            all_passed = False
            logger.warning("❌ CLI Pre-Gate TIMEOUT: %s", cmd)
    
    return all_passed, results

def _auto_detect_verify_commands(project_root: Path) -> List[str]:
    """根據專案語言自動推斷驗證指令"""
    cmds = []
    
    # Python
    if (project_root / "pytest.ini").exists() or (project_root / "pyproject.toml").exists():
        cmds.append("python3 -m pytest --tb=short -q")
    
    # Rust
    if (project_root / "Cargo.toml").exists():
        cmds.append("cargo test --lib 2>&1")
    
    # Go
    if (project_root / "go.mod").exists():
        cmds.append("go test ./... 2>&1")
    
    # Node
    if (project_root / "package.json").exists():
        import json
        try:
            pkg = json.loads((project_root / "package.json").read_text())
            if "test" in pkg.get("scripts", {}):
                cmds.append("npm test 2>&1")
        except Exception:
            pass
    
    return cmds
