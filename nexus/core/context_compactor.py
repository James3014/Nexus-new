import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime

class ContextCompactor:
    def __init__(self, project_root: Path):
        self.compacted_file = project_root / ".nexus" / "state" / "context_summary.json"

    def compact(self, state: Dict[str, Any], confidence: float = 0.5):
        prev = self._load()
        tasks = state.get("tasks", {})
        done = [t.get("note", "") for t in tasks.values() if t.get("status") == "done" and t.get("note")]
        
        signal = int(confidence * 100)
        existing = {f["outcome"] if isinstance(f, dict) else f for f in prev.get("verified_facts", [])}
        
        merged = prev.get("verified_facts", [])
        for item in done:
            if item not in existing:
                merged.append({
                    "context": f"crystal://session/{datetime.now().strftime('%Y%m%d')}",
                    "goal": "Context Continuity Recovery",
                    "action": "Task Crystallization",
                    "outcome": item,
                    "signal": signal,
                    "pivot": "",
                    "memory": "crystal_sync_pending"
                })

        summary = {
            "verified_facts": merged,
            "applied_changes": list(set(prev.get("applied_changes", []) + [t["id"] for t in tasks.values() if t.get("status") == "done"])),
            "unresolved_risks": [],
            "next_hypotheses": []
        }
        self.compacted_file.parent.mkdir(parents=True, exist_ok=True)
        self.compacted_file.write_text(json.dumps(summary, indent=2))
        return summary

    def _load(self):
        if self.compacted_file.exists():
            try:
                data = json.loads(self.compacted_file.read_text())
                if isinstance(data, dict): return data
            except: pass
        return {"verified_facts": []}

class BoundaryAligner:
    def align_boundaries(self, seq): return seq
