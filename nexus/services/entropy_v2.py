import math
import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)

class EntropyGuardV2:
    """🛡️ [Wave 3] Entropy Guard v2: Multi-Dimensional Audit"""
    
    def __init__(self, token_threshold: float = 3.5):
        self.token_threshold = token_threshold

    def audit_payload(self, text: str, tokens: List[int] = None) -> Dict[str, Any]:
        """執行全維度熵審計，防範密鑰洩露與 Token 濫用內容"""
        # 1. 文本熵 (Shannon)
        text_entropy = self._shannon(text)
        
        # 2. Token 分佈熵 (行動 22)
        token_entropy = self._shannon_tokens(tokens) if tokens else 0.0
        
        is_vetoed = text_entropy > 4.5 or token_entropy > self.token_threshold
        
        logger.info(f"🛡️ [Entropy-v2] Text: {text_entropy:.1f}, Tokens: {token_entropy:.1f} | Result: {'VETO' if is_vetoed else 'PASS'}")
        
        return {
            "text_entropy": text_entropy,
            "token_entropy": token_entropy,
            "status": "VETOED" if is_vetoed else "PASSED"
        }

    def _shannon(self, text: str) -> float:
        if not text: return 0.0
        prob = [float(text.count(c)) / len(text) for c in dict.fromkeys(list(text))]
        return - sum([p * math.log(p) / math.log(2.0) for p in prob])

    def _shannon_tokens(self, tokens: List[int]) -> float:
        if not tokens: return 0.0
        prob = [float(tokens.count(t)) / len(tokens) for t in dict.fromkeys(tokens)]
        return - sum([p * math.log(p) / math.log(2.0) for p in prob])

if __name__ == "__main__":
    guard = EntropyGuardV2()
    print(guard.audit_payload("Safe text", [1, 1, 1, 1])) # Pass
    print(guard.audit_payload("sk-abcdefgh12345678", [10, 20, 30, 40])) # Veto
