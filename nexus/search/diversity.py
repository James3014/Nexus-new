import difflib
from typing import List

class DiversityMeter:
    """
    📏 Task T9: Diversity Meter
    職責: 量測候選補丁之間的差異性。
    """
    def compute_diversity(self, patches: List[str]) -> float:
        if len(patches) < 2:
            return 1.0
        
        # 改用字詞集合 (Word-set) 基礎的多樣性量測 (Jaccard Distance)
        import re
        def get_words(text):
            return set(re.findall(r'\w+', text))

        diversities = []
        for i in range(len(patches)):
            for j in range(i + 1, len(patches)):
                set_a = get_words(patches[i])
                set_b = get_words(patches[j])
                intersection = len(set_a.intersection(set_b))
                union = len(set_a.union(set_b))
                # Jaccard Similarity = intersection / union
                # Jaccard Distance (Diversity) = 1 - similarity
                diversities.append(1.0 - (intersection / union if union > 0 else 0))
        
        return sum(diversities) / len(diversities)
