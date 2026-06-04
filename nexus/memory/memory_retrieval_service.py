from typing import List, Optional
from nexus.memory.memory_models import MemoryHit, FailureSignatureHit, MemoryContextPack

class MemoryRetrievalService:
    """
    🧠 Task: Causal Memory Retrieval Service
    職責: 執行 Failure Signature > Family Level > Archive 三段式檢索與排序。
    """
    
    @staticmethod
    def rank_and_pack(hits: List[MemoryHit], 
                      current_state_version: int,
                      relevance_threshold: float = 0.7) -> MemoryContextPack:
        """
        將原始命中進行因果權重排序、過濾與分層封裝。
        """
        # 1. 物理過濾 Stale Memory 與 低相關性
        valid_hits = [
            h for hit in hits 
            if (h := hit) and h.relevance >= relevance_threshold 
            and h.state_version <= current_state_version
        ]

        actionable = []
        family = []
        archive = []

        # 2. 分層 (利用 isinstance 或 metadata)
        for hit in valid_hits:
            if isinstance(hit, FailureSignatureHit):
                actionable.append(hit)
            elif hit.metadata.get("type") == "family":
                family.append(hit)
            else:
                archive.append(hit)

        # 3. 排序 (內部權重排序)
        actionable.sort(key=lambda x: x.relevance, reverse=True)
        family.sort(key=lambda x: x.relevance, reverse=True)
        archive.sort(key=lambda x: x.relevance, reverse=True)

        return MemoryContextPack(
            actionable_hits=actionable,
            family_context=family,
            background_archive=archive
        )
