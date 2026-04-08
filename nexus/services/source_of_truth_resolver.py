import json
from pathlib import Path
from typing import Dict, Any, List

class SourceOfTruthResolver:
    """
    ⚖️ Work Order B: Source-of-Truth Resolver
    標定系統真值來源，定義 Truth Rank，防止決策依據模糊。
    """
    
    TRUTH_RANK = [
        "audit_result.json",
        "acceptance_check.json",
        "manifest.json",
        "phase_metrics.json"
    ]

    def __init__(self, project_root: Path, task_id: str):
        self.project_root = project_root
        self.task_id = task_id
        self.run_dir = project_root / ".nexus" / "runs" / task_id

    def resolve(self) -> Dict[str, Any]:
        """
        解析真值映射表。
        """
        field_map = {
            "releaseReady": {
                "source": "acceptance_check.json",
                "type": "truth",
                "rank": 2
            },
            "auditPassed": {
                "source": "audit_result.json",
                "type": "truth",
                "rank": 1
            },
            "canPublish": {
                "source": "decision_formula",
                "type": "derived"
            },
            "taskStatus": {
                "source": "manifest.json",
                "type": "truth",
                "rank": 3
            }
        }

        # 掃描實體存在性
        available_sources = []
        for src in self.TRUTH_RANK:
            if (self.run_dir / src).exists():
                available_sources.append(src)

        return {
            "truth_rank": self.TRUTH_RANK,
            "available_sources": available_sources,
            "field_map": field_map,
            "resolver_version": "v1.0"
        }

if __name__ == "__main__":
    # 測試
    root = Path(str(__import__("pathlib").Path(__file__).resolve().parents[2]))
    tid = "test-task-001"
    resolver = SourceOfTruthResolver(root, tid)
    print(json.dumps(resolver.resolve(), indent=2))
