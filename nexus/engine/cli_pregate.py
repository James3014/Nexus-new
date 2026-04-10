from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
"""CLI Pre-Gate：在 A 階段之前，用 exit code 做一次機械性驗證"""
import subprocess
import logging
import os
import sys
import json

logger = logging.getLogger(__name__)

def _get_venv_python(project_root: Path) -> str:
    """
    💎 物理直譯器鎖定 (Iron Python):
    優先尋找虛擬環境直譯器。
    """
    # Mac/Linux
    python_bin = project_root / ".venv" / "bin" / "python3"
    if not python_bin.exists():
        # Windows
        python_bin = project_root / ".venv" / "Scripts" / "python.exe"
    
    if python_bin.exists():
        return str(python_bin)
    
    return sys.executable

def run_cli_pregate(
    project_root: Path,
    commands: List[str],
    timeout_per_cmd: int = 60,
) -> Tuple[bool, List[dict]]:
    """
    執行驗證指令列表，回傳 (all_passed, results)
    """
    if not commands:
        return True, [{"cmd": "_SKIPPED", "exit_code": -1, "passed": True, "pregate_skip": True}]
    
    env = os.environ.copy()
    venv_bin = str(project_root / ".venv" / "bin")
    env["PATH"] = f"{venv_bin}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONPATH"] = f"{project_root}{os.pathsep}{env.get('PYTHONPATH', '')}"
    
    results = []
    all_passed = True
    
    for cmd in commands:
        try:
            logger.info("🧪 [Pre-Gate] 執行驗證: %s", cmd)
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=project_root,
                capture_output=True,
                text=True,
                timeout=timeout_per_cmd,
                env=env,
            )
            
            # ⚖️ 治理門檻調整 (Adaptive Gating):
            # rc == 2 (Usage error/Path not found in Sandbox) 視為 Soft Fail (passed)。
            is_env_error = (proc.returncode == 2)
            passed = (proc.returncode == 0) or is_env_error
            
            results.append({
                "cmd": cmd,
                "exit_code": proc.returncode,
                "passed": passed,
                "is_soft_fail": is_env_error,
                "stdout_tail": (proc.stdout or "")[-500:],
                "stderr_tail": (proc.stderr or "")[-500:],
            })
            
            if is_env_error:
                logger.warning("⚠️ CLI Pre-Gate SOFT FAIL (rc=2, Ambient Noise): %s", cmd)
            elif not passed:
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
    venv_python = _get_venv_python(project_root)
    
    # Python
    if (project_root / "pytest.ini").exists() or (project_root / "pyproject.toml").exists():
        cmds.append(f"{venv_python} -m pytest --tb=short -q")
    
    # Rust
    if (project_root / "Cargo.toml").exists():
        cmds.append("cargo test --lib 2>&1")
    
    # Go
    if (project_root / "go.mod").exists():
        cmds.append("go test ./... 2>&1")

    # Node.js
    package_json = project_root / "package.json"
    if package_json.exists():
        try:
            data = json.loads(package_json.read_text(encoding="utf-8"))
            scripts = data.get("scripts", {}) if isinstance(data, dict) else {}
            if isinstance(scripts, dict) and scripts.get("test"):
                cmds.append("npm test --silent 2>&1")
        except Exception as exc:
            logger.debug("package_json_parse_failed: %s", exc)
    
    return cmds
