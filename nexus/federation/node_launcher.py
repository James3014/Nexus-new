from typing import Any, Dict, List, Optional, Tuple
import subprocess
import os
import sys

class NodeLauncher:
    def __init__(self, repo_path: str, wasm_mode: bool = True) -> None:
        self.repo_path: str = os.path.abspath(repo_path)
        self.wasm_mode: bool = wasm_mode

    def launch(self, script_path: str, args: Optional[List[str]] = None) -> Optional[Any]:
        if args is None:
            args = []
            
        print(f"🚀 Launching Nexus Node (Mode: {'WASM' if self.wasm_mode else 'NATIVE'})...")
        
        if self.wasm_mode:
            # Use Wasmer with volume mapping for the repository jail
            # Map host repo_path to /workspace inside the sandbox
            cmd = [
                "wasmer", "run", 
                "--volume", f"{self.repo_path}:/workspace",
                "wasmer/python", "--", 
                f"/workspace/{script_path}"
            ] + args
        else:
            # Native fallback
            cmd = [sys.executable, f"{self.repo_path}/{script_path}"] + args
            
        try:
            process = subprocess.Popen(cmd)
            print(f"✅ Node started with PID: {process.pid}")
            return process
        except Exception as e:
            print(f"❌ Failed to launch node: {e}")
            return None

if __name__ == "__main__":
    # Demo use case
    launcher = NodeLauncher(repo_path=".")
    launcher.launch("scripts/engine/nexus_cli.py", ["--help"])
