import ctypes
import os
from pathlib import Path
from enum import Enum

# [NEXUS v26] Rust Governance Bridge
# Interfaces Python with the compiled nexus_core shared library.

class GovernanceBridge:
    def __init__(self):
        # 定位編譯好的 dylib
        lib_path = Path("target/release/libnexus_core.dylib")
        if not lib_path.exists():
            # 回退到 debug 路徑
            lib_path = Path("target/debug/libnexus_core.dylib")
        
        if not lib_path.exists():
            raise FileNotFoundError(f"Nexus Core library not found at {lib_path}")
            
        self.lib = ctypes.CDLL(str(lib_path))
        
    def can_transition(self, from_state: str, to_state: str) -> bool:
        """
        呼叫 Rust 物理層進行狀態轉移驗證。
        """
        # 注意：實際 PyO3 調用通常透過 import nexus_core
        # 這裡為了展示 TDD 隔離，我們先用 import 模式嘗試
        try:
            import sys
            sys.path.append("target/release")
            import nexus_core
            return nexus_core.can_transition(from_state, to_state)
        except ImportError:
            # 如果 import 失敗，回報 INFRA_INVALID
            print("⚠️ [Bridge] nexus_core extension module not found in path.")
            return False

    def normalize_intent(self, raw_output: str):
        """
        將模型輸出的原始字串交由 Rust 進行正規化，回傳 (Route, Decision, Phase, Confidence)。
        若解析失敗或為自然語言，則回傳 None 觸發 ESCALATE。
        """
        try:
            import sys
            sys.path.append("target/release")
            import nexus_core
            return nexus_core.normalize_intent(raw_output)
        except ImportError:
            print("⚠️ [Bridge] nexus_core extension module not found in path.")
            return None

if __name__ == "__main__":
    bridge = GovernanceBridge()
    print(f"PLAN -> EXECUTE: {bridge.can_transition('PLAN', 'EXECUTE')}")
    print(f"PLAN -> VERIFY: {bridge.can_transition('PLAN', 'VERIFY')}")
    print(f"Normalize Valid: {bridge.normalize_intent('r:0,d:0,p:1,c:0')}")
    print(f"Normalize Invalid: {bridge.normalize_intent('I think we should plan')}")
