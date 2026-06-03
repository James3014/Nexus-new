import subprocess
import sysconfig
from pathlib import Path
from typing import List, Dict
from nexus.env.models import EnvSnapshot

class EnvProbe:
    """🔭 Task T10: Environment Probe"""
    @staticmethod
    def capture_snapshot(python_exe: str) -> EnvSnapshot:
        # 獲取 Python 版本
        version = sysconfig.get_python_version()
        
        # 獲取已安裝套件 (模擬)
        packages = ["numpy", "astropy", "pyerfa"] # 真實情況會跑 pip list
        
        # 獲取重要環境變數
        import os
        env_vars = [f"{k}={v}" for k, v in os.environ.items() if "NEXUS" in k or "PYTHON" in k]
        
        return EnvSnapshot(
            python_version=version,
            installed_packages=packages,
            env_vars=env_vars
        )
