import json
import logging
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

@dataclass(frozen=True)
class MismatchEntry:
    """語義漂移記錄項"""
    module_name: str
    input_hash: str
    py_output: Any
    rs_output: Any
    match: bool
    diff_reason: Optional[str] = None
    diff_details: Dict[str, List[str]] = field(default_factory=dict) # 新增：詳細差異項目
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class MismatchLedger:
    """治理資料：記錄並分類 Python 與 Rust 執行結果的差異"""
    
    def __init__(self, ledger_path: Path):
        self.ledger_path = ledger_path
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)

    def record_mismatch(self, entry: MismatchEntry):
        logger.warning(f"❌ [DualRun] Mismatch detected in {entry.module_name}: {entry.diff_reason}")
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict()) + "\n")

class DualRunComparator:
    """雙跑比對框架：對比 Python 與 Rust 執行結果"""

    def __init__(self, ledger: Optional[MismatchLedger] = None):
        self.ledger = ledger

    def compare(self, module_name: str, py_result: Any, rs_result: Any, input_data: Any) -> bool:
        """比對執行結果並記錄差異"""
        # 簡單的相等比對
        match = (py_result == rs_result)
        
        if not match and self.ledger:
            # 建立 input_hash 供追蹤 (簡化版)
            input_hash = str(hash(str(input_data)))
            
            diff_reason = "OUTPUT_VALUE_MISMATCH"
            if type(py_result) != type(rs_result):
                diff_reason = "TYPE_MISMATCH"
                
            entry = MismatchEntry(
                module_name=module_name,
                input_hash=input_hash,
                py_output=py_result,
                rs_output=rs_result,
                match=False,
                diff_reason=diff_reason
            )
            self.ledger.record_mismatch(entry)
            
        return match
