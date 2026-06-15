import json
import datetime
from pathlib import Path
from nexus.engine.surgical_retriever import SurgicalRetriever
from nexus.engine.surgical_slicer import SurgicalSlicer
from nexus.engine.surgical_packer import SurgicalPacker

class SurgicalIntelligence:
    def __init__(self, root, evidence_log_path: str | Path = None):
        self.root = Path(root)
        self.retriever = SurgicalRetriever(self.root)
        if evidence_log_path is None:
            self.evidence_log_path = self.root / ".nexus" / "metrics" / "surgical_evidence_log.jsonl"
        else:
            self.evidence_log_path = Path(evidence_log_path)
            
    def provide_context(self, sym, budget=4000):
        files = self.retriever.find_definition(sym)
        if not files: return ""
        file_path = files[0]
        s = SurgicalSlicer(file_path)
        res = s.slice_function(sym)
        
        # Line-level evidence logging
        if res.start_line > 0:
            try:
                self.evidence_log_path.parent.mkdir(parents=True, exist_ok=True)
                relative_file_path = str(file_path.relative_to(self.root))
            except Exception:
                relative_file_path = str(file_path)
                
            evidence_row = {
                "symbol": sym,
                "file_path": relative_file_path,
                "start_line": res.start_line,
                "end_line": res.end_line,
                "budget_tokens": budget,
                "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            try:
                with self.evidence_log_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(evidence_row) + "\n")
            except Exception:
                pass

        try: return SurgicalPacker(res.code_content, budget).pack()
        except: return res.code_content[:budget*4]
