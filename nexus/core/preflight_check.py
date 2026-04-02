from typing import Any, Dict, List, Optional, Tuple
import subprocess
import os
import logging

logger = logging.getLogger(__name__)

class PreflightCheck:
    """
    🔮 Nexus 預檢先知 (Phase G.0)
    強制執行環境物理核驗，防止 Agent 在版本不符或資源衝突時敷衍執行。
    """
    
    @staticmethod
    def check_version(tool: str, required_min: str) -> bool:
        """🎯 核驗二進位工具版本真值 (支援動態最小版本)"""
        try:
            cmd = [tool, "--version"]
            res = subprocess.run(cmd, capture_output=True, text=True)
            version_out = res.stdout + res.stderr
            logger.info(f"🔍 [Preflight:Version] {tool} -> {version_out.strip()}")
            
            # 動態版本比對：提取數字部分並比較
            import re
            match = re.search(r"(\d+\.\d+(\.\d+)?)", version_out)
            if match:
                current = match.group(1).split('.')
                required = required_min.split('.')
                # 補齊長度
                while len(current) < 3: current.append("0")
                while len(required) < 3: required.append("0")
                return tuple(map(int, current)) >= tuple(map(int, required))
            return False
        except Exception:
            return False

    @staticmethod
    def check_port(port: int) -> Optional[int]:
        """🎯 核驗埠口佔用狀態，返回 PID"""
        try:
            # macOS lsof 語法
            process = subprocess.run(
                ["lsof", "-i", f":{port}", "-t"],
                capture_output=True, text=True
            )
            if process.stdout.strip():
                pid = int(process.stdout.strip().split('\n')[0])
                logger.warning(f"⚠️ [Preflight:Port] Port {port} is occupied by PID {pid}")
                return pid
        except Exception:
            pass
        return None

    @staticmethod
    def validate_environment(specs: Dict[str, str]) -> Dict[str, Any]:
        """🎯 全量執行預檢指標矩陣"""
        report = {"status": "HEALTHY", "issues": []}
        
        for tool, version in specs.items():
            if not PreflightCheck.check_version(tool, version):
                report["status"] = "BLOCKED"
                report["issues"].append(f"Mismatched {tool} version. Expected {version}")
                
        return report

if __name__ == "__main__":
    # 測試執行
    p = PreflightCheck()
    print(f"Rust 1.90 Check: {p.check_version('rustc', '1.90')}")
    print(f"Port 8000 Check: {p.check_port(8000)}")
