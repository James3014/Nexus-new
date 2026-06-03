from typing import List, Any, Dict
import uuid

class ProposalGenerator:
    """
    🏗️ Task T1.1: Proposal Generator
    職責: 負責產生初始候選提案 (Proposals)。
    """
    def generate_candidates(self, task_id: str, k: int, model: str) -> List[Dict[str, Any]]:
        # 在實際系統中，這會呼叫 Ollama/API
        # 這裡回傳模擬的候選者清單
        return [
            {
                "candidate_id": f"{task_id}-{model}-{i}-{uuid.uuid4().hex[:4]}",
                "model": model,
                "attempt": i,
                "content": f"fix_logic_v{i}"
            } for i in range(k)
        ]
