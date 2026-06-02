import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexus.bridge.rust_kernel import RustKernelAdapter

logger = logging.getLogger(__name__)

class RustCutoverManager:
    """Stage R6: 整合與切換管理器，控制 Rust Kernel 的灰度佈署與回退"""

    DEFAULT_BINARY_PATH = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")

    def __init__(self, binary_path: Optional[Path] = None):
        self.adapter = RustKernelAdapter(binary_path or self.DEFAULT_BINARY_PATH)
        
        # Feature Flags
        self.use_rust_ast = os.environ.get("USE_RUST_AST_SCANNER", "0") == "1"
        self.use_rust_flow = os.environ.get("USE_RUST_FLOW_ENGINE", "0") == "1"
        self.use_rust_receipt = os.environ.get("USE_RUST_RECEIPT_VERIFIER", "0") == "1"
        self.use_rust_matcher = os.environ.get("USE_RUST_MATCHER", "0") == "1"

    def validate_flow_transition(self, current: str, next_state: str) -> bool:
        if self.use_rust_flow:
            logger.info("🦀 [Rust] Validating flow transition via Kernel...")
            result = self.adapter._call_kernel("ValidateTransition", {"current": current, "next": next_state})
            if result.get("success"):
                return result["payload"]["is_valid"]
            logger.error("⚠️ [Rust] Kernel failed, falling back to legacy flow validation: %s", result.get("error_message"))
            
        # Legacy Fallback
        return self._legacy_validate_flow(current, next_state)

    def _legacy_validate_flow(self, current: str, next_state: str) -> bool:
        # 這裡未來會接回 Python 的 FlowStateMachine
        return True 

    def get_status(self) -> Dict[str, bool]:
        return {
            "rust_ast_active": self.use_rust_ast,
            "rust_flow_active": self.use_rust_flow,
            "rust_receipt_active": self.use_rust_receipt,
            "rust_matcher_active": self.use_rust_matcher
        }
