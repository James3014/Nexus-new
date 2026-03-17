#!/usr/bin/env python3
import json
import subprocess
from typing import Any, Dict
from nexus.engine.phases.base import BasePhaseHandler
from nexus.core.state_contracts import NexusState

class ResearchPhaseHandler(BasePhaseHandler):
    """
    🌐 Phase X: Research
    封裝 Felo CLI 調用與研究追蹤紀錄。
    """
    def __init__(self, project_root: Any, run_dir: Any):
        super().__init__(project_root, run_dir)

    def run(self, state: NexusState, context: Dict[str, Any]) -> Dict[str, Any]:
        task = context.get("task")
        print(f"🌐 [Nexus:Phase-X] External Research via Felo CLI for: {task}")
        
        research_pack = None
        try:
            # 實例化 Felo 調用
            felo_cmd = ["npx", "-y", "@willh/felo-cli", "--json", task]
            result = subprocess.run(felo_cmd, capture_output=True, text=True, check=False)
            findings = [result.stdout] if result.returncode == 0 else ["Felo search failed, falling back to internal."]
            
            research_pack = {
                "findings": findings,
                "source": "Felo-CLI",
                "status": "SUCCESS" if result.returncode == 0 else "FAIL"
            }
        except Exception as e:
            print(f"⚠️ [X-Stage] Research error: {e}")
            research_pack = {"findings": [f"Research error: {str(e)}"], "source": "ERROR", "status": "FAIL"}
        
        # 🛡️ v9 Hardening: 寫入 Trace
        research_file = self.run_dir / "researchpack.json"
        research_file.write_text(json.dumps(research_pack, ensure_ascii=False))
        return research_pack
