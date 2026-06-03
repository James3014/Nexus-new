from typing import List, Dict
from nexus.verifiers.models import VerifierVerdict

class ScoreAggregator:
    """
    📊 Task T2: Score Aggregator
    職責: 彙總不同驗證器的分數，但不做最終決策。
    """
    @staticmethod
    def aggregate(verdicts: List[VerifierVerdict]) -> Dict[str, float]:
        scores = {}
        for v in verdicts:
            cid = v.candidate_id
            if cid not in scores:
                scores[cid] = 0.0
            
            # 權重分配：顯性漏洞訊號權重極大化
            weight = 1.0
            if v.verifier_name == "contract": weight = 2.0
            if v.verifier_name == "test": weight = 5.0
            if v.verifier_name in ["name_sanity", "inheritance"]: weight = 10.0 # 領域加固
            
            val = v.score * weight if v.passed else -20.0 * weight # 懲罰翻倍
            scores[cid] += val
        return scores
