import json
from typing import Dict, Any

class DualGateProtocol:
    @staticmethod
    def render(task: str, data: Dict[str, Any], evidence: str, debt: str) -> str:
        return (
            f"[Task]\n{task}\n\n"
            f"[Data]\n{json.dumps(data, indent=2)}\n\n"
            f"[Evidence]\n{evidence}\n\n"
            f"[Residual Debt]\n{debt}"
        )
