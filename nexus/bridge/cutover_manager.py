import os
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from nexus.bridge.rust_kernel import RustKernelAdapter
from nexus.bridge.dual_run import DualRunComparator, MismatchLedger

logger = logging.getLogger(__name__)

class RustCutoverManager:
    """Stage R6: 整合與切換管理器，控制 Rust Kernel 的灰度佈署與回退"""

    DEFAULT_BINARY_PATH = Path("/Users/jameschen/Workspace/nexus/nexus-core-rs/target/release/nexus-core-rs")
    DEFAULT_LEDGER_PATH = Path("/Users/jameschen/Workspace/nexus/.nexus/reports/rust_mismatch_ledger.jsonl")

    def __init__(self, binary_path: Optional[Path] = None, ledger_path: Optional[Path] = None):
        self.adapter = RustKernelAdapter(binary_path or self.DEFAULT_BINARY_PATH)
        self.ledger = MismatchLedger(ledger_path or self.DEFAULT_LEDGER_PATH)
        self.comparator = DualRunComparator(self.ledger)
        
        # Feature Flags
        self.use_rust_ast = os.environ.get("USE_RUST_AST_SCANNER", "0") == "1"
        self.use_rust_flow = os.environ.get("USE_RUST_FLOW_ENGINE", "0") == "1"
        self.use_rust_receipt = os.environ.get("USE_RUST_RECEIPT_VERIFIER", "0") == "1"
        self.use_rust_matcher = os.environ.get("USE_RUST_MATCHER", "0") == "1"
        
        self.dual_run_enabled = os.environ.get("RUST_DUAL_RUN", "0") == "1"
        self.primary_only = os.environ.get("RUST_PRIMARY_ONLY", "0") == "1"

    def validate_flow_transition(self, current: str, next_state: str, py_fsm: Optional[Any] = None) -> bool:
        """驗證流程轉移，支援 Dual-run 與 Primary Only 模式"""
        
        rs_result = None
        if self.use_rust_flow or self.dual_run_enabled:
            logger.info("🦀 [Rust] Calling Kernel for flow validation...")
            call_res = self.adapter._call_kernel("ValidateTransition", {"current": current, "next": next_state})
            if call_res.get("success"):
                rs_result = call_res["payload"]["is_valid"]
            else:
                logger.error("⚠️ [Rust] Kernel failed: %s", call_res.get("error_message"))

        # 如果是 Primary Only，直接回傳 Rust 結果 (含 Fallback)
        if self.primary_only and rs_result is not None:
            return rs_result

        # 執行 Python 舊路徑
        py_result = self._legacy_validate_flow(current, next_state, py_fsm)
        
        # 執行 Dual-run 比對
        if self.dual_run_enabled and rs_result is not None:
            match = self.comparator.compare("flow_machine", py_result, rs_result, {"current": current, "next": next_state})
            if not match:
                logger.warning("⚖️ [DualRun] Divergence in flow validation! Python=%s, Rust=%s", py_result, rs_result)

        # 根據模式決定回傳值
        if self.use_rust_flow and rs_result is not None:
            return rs_result
            
        return py_result

    def _legacy_validate_flow(self, current: str, next_state: str, py_fsm: Any) -> bool:
        if py_fsm and hasattr(py_fsm, "validate_transition"):
             from nexus.engine.capability_contracts import FlowState
             try:
                 return py_fsm.validate_transition(FlowState(current), FlowState(next_state))
             except Exception:
                 return True
        return True 

    def get_status(self) -> Dict[str, Any]:
        return {
            "rust_ast_active": self.use_rust_ast,
            "rust_flow_active": self.use_rust_flow,
            "rust_receipt_active": self.use_rust_receipt,
            "rust_matcher_active": self.use_rust_matcher,
            "dual_run_enabled": self.dual_run_enabled,
            "primary_only": self.primary_only
        }
