import json
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

class RustKernelAdapter:
    """Python 適配器，負責與 Rust Kernel 進行 JSON IPC 通訊"""

    def __init__(self, binary_path: str | Path):
        self.binary_path = Path(binary_path)

    def _call_kernel(self, request_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.binary_path.exists():
            return {"success": False, "error_message": f"Binary not found: {self.binary_path}"}

        request = {
            "type": request_type,
            "payload": payload
        }
        
        try:
            process = subprocess.Popen(
                [str(self.binary_path)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(input=json.dumps(request))
            
            if process.returncode != 0:
                return {"success": False, "error_message": f"Kernel exited with {process.returncode}: {stderr}"}
                
            return json.loads(stdout)
        except Exception as e:
            return {"success": False, "error_message": str(e)}

    def smoke_test(self, message: str) -> Dict[str, Any]:
        return self._call_kernel("SmokeTest", {"message": message})

    def get_flow_decision(self, current_state: str, event: str) -> Dict[str, Any]:
        return self._call_kernel("FlowDecision", {"current_state": current_state, "event": event})
