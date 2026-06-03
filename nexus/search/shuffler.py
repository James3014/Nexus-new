from typing import List, Dict, Any
import random

class VariantShuffler:
    """
    🔀 Task T1.2: Variant Shuffler
    職責: 透過攪拌 (Shuffling) 策略打破候選者的同質化。
    """
    def apply_shuffling(self, base_candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not base_candidates:
            return []
            
        shuffled = []
        for c in base_candidates:
            # 模擬攪拌：修改 Prompt Variant 或 Temperature
            new_c = c.copy()
            new_c["prompt_variant"] = random.choice(["aider-strict", "thinking-step", "code-minimal"])
            shuffled.append(new_c)
        return shuffled
