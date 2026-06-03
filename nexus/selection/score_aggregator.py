from typing import List, Dict
from nexus.verifiers.contracts import VerifierVerdict

class ScoreAggregator:
    """
    📊 Task T2: Score Aggregator (Selection Lane)
    職責: 獨立彙總不同驗證器的分數，不包含排序或 Winner 決策邏輯。
    """
    @staticmethod
    def aggregate(verdicts: List[VerifierVerdict]) -> Dict[str, float]:
        scores = {}
        # 紀錄發生衝突的驗證器
        conflicts = set()
        
        for v in verdicts:
            cid = v.candidate_id
            if cid not in scores:
                scores[cid] = 0.0
            
            # 動態權重分配 (可由外部設定，此為預設)
            weight = 1.0
            if v.verifier_name == "contract": weight = 2.0
            if v.verifier_name == "test": weight = 5.0
            if v.verifier_name in ["name_sanity", "inheritance"]: weight = 10.0
            
            val = v.score * weight if v.passed else -20.0 * weight
            scores[cid] += val
            
            # 若有驗證器明確標示致命缺陷且被其他驗證器通過，則視為信號衝突 (預留擴充)
            if not v.passed and v.score < -5.0:
                conflicts.add(cid)
                
        return {"scores": scores, "conflicts": list(conflicts)}
