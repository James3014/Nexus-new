#!/usr/bin/env python3
import json
import subprocess
import os
import time
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
        print(f"🌐 [Nexus:Phase-X] External Research for: {task}")
        
        # 1. Hybrid Cache check (Target: Reduce <3k token re-fetch)
        research_file = self.run_dir / "researchpack.json"
        if research_file.exists():
            print(f"♻️ [X-Stage] Cache Hit: Loading existing researchpack.")
            return json.loads(research_file.read_text())

        # 1. 🛡️ v1.8 Hybrid Cache Check
        research_file = self.run_dir / "researchpack.json"
        if research_file.exists():
            print("📎 [X-Stage] Loading local research cache...")
            return json.loads(research_file.read_text())

        # 🧬 LanceDB Vector Cache Check
        import lancedb
        DB_PATH = os.path.expanduser("~/.openclaw/memory/lancedb-research")
        db = lancedb.connect(DB_PATH)
        table_name = "research_cache"
        
        # Simple task-based exact match for now, could be vector search
        try:
            tbl = db.open_table(table_name)
            cached = tbl.to_pandas().query(f"task == '{task}'").to_dict(orient="records")
            if cached:
                print("🧠 [X-Stage] Found in LanceDB research cache!")
                res = json.loads(cached[0]["pack"])
                research_file.write_text(json.dumps(res, ensure_ascii=False))
                return res
        except Exception:
            pass

        # 2. Concise Query Execution
        research_pack = None
        tokens_used = 0
        try:
            # Add "concise summary only" to minimize tokens
            optimized_query = f"{task} (provide a concise summary only, limit to 300 words)"
            felo_cmd = ["npx", "-y", "@willh/felo-cli", "--json", optimized_query]
            result = subprocess.run(felo_cmd, capture_output=True, text=True, check=False)
            
            # Estimate tokens
            tokens_used = len(result.stdout) // 4 + 100
            findings = [result.stdout] if result.returncode == 0 else ["Felo search failed, falling back to internal."]
            
            research_pack = {
                "findings": findings,
                "source": "Felo-CLI",
                "status": "SUCCESS" if result.returncode == 0 else "FAIL",
                "tokens_used": tokens_used
            }
            
            # Save to LanceDB
            try:
                data = [{"task": task, "pack": json.dumps(research_pack), "timestamp": time.time()}]
                if table_name not in db.table_names():
                    db.create_table(table_name, data=data)
                else:
                    db.open_table(table_name).add(data)
            except Exception:
                pass

        except Exception as e:
            print(f"⚠️ [X-Stage] Research error: {e}")
            research_pack = {"findings": [f"Research error: {str(e)}"], "source": "ERROR", "status": "FAIL", "tokens_used": 0}
        
        # 🛡️ v9 Hardening: 寫入 Trace
        research_file.write_text(json.dumps(research_pack, ensure_ascii=False))
        return research_pack
