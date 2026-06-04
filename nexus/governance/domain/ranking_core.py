class RankingCore:
    @staticmethod
    def score(evidence_quality: float) -> float:
        return evidence_quality * 100.0
