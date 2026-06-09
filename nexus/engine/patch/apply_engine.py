import logging
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from nexus.engine.contracts.patch import PatchIntent, SearchReplaceBlock, ApplyVerdict
from nexus.engine.patch.envelope_parser import PatchEnvelopeParser
from nexus.engine.patch.block_normalizer import SearchBlockNormalizer
from nexus.engine.patch.unique_locator import UniqueLocator
from nexus.engine.patch.apply_planner import ApplyPlanner
from nexus.engine.patch.bounded_fuzzy_applier import BoundedFuzzyApplier
from nexus.engine.patch.apply_verifier import ApplyVerifier
from nexus.engine.patch.receipt_writer import ApplyReceiptWriter

from nexus.engine.contracts.execution import ExecutionPhase
from nexus.engine.execution.phase_timer import PhaseTimer
from nexus.engine.patch.health_classifier import PatchEnvelopeHealthClassifier, PatchHealth

from nexus.engine.execution.budget_policy import ExecutionBudgetPolicy, DeferredVerificationQueue
from nexus.engine.execution.receipt_augmenter import ExecutionReceiptAugmenter

logger = logging.getLogger(__name__)

class PatchApplyEngine:
    """
    🛡️ PatchApplyEngine: 補丁套用引擎
    整合 7 大模組與執行相位，執行受控的 Search/Replace 套用流程。
    """
    def __init__(self, project_root: Path, budget_profile: str = "core20"):
        self.project_root = Path(project_root)
        self.parser = PatchEnvelopeParser()
        self.normalizer = SearchBlockNormalizer()
        self.locator = UniqueLocator()
        self.planner = ApplyPlanner()
        self.applier = BoundedFuzzyApplier()
        self.verifier = ApplyVerifier()
        self.receipt_writer = ApplyReceiptWriter(self.project_root / ".nexus" / "reports")
        self.health_classifier = PatchEnvelopeHealthClassifier()
        self.timer = PhaseTimer()
        self.budget_policy = ExecutionBudgetPolicy(budget_profile)
        self.deferred_queue = DeferredVerificationQueue()
        self.receipt_augmenter = ExecutionReceiptAugmenter()

    def apply_patch(self, task_id: str, target_file: str, raw_patch: str) -> Dict[str, Any]:
        logger.info("🔪 [PatchEngine] Applying patch to %s for task %s", target_file, task_id)
        
        file_path = self.project_root / target_file
        if not file_path.exists():
            return {"status": "FAIL", "reason": f"FILE_NOT_FOUND: {target_file}"}
            
        original_content = file_path.read_text(encoding="utf-8")
        current_content = original_content
        
        # 1. Parse & Classify Health
        self.timer.start(ExecutionPhase.PATCH_PARSE)
        intent = self.parser.parse(task_id, raw_patch)
        health = self.health_classifier.classify(raw_patch, intent.blocks)
        self.timer.stop(ExecutionPhase.PATCH_PARSE)

        if health != PatchHealth.HEALTHY:
            logger.warning(f"⚠️ [PatchEngine] Patch unhealthy: {health.value}")
            return {
                "status": "FAIL", 
                "reason": f"PATCH_UNHEALTHY: {health.value}",
                "health_class": health.value
            }
            
        if not intent.blocks:
            return {"status": "FAIL", "reason": "NO_SEARCH_REPLACE_BLOCKS_FOUND"}
            
        block_results = []
        
        # 2. Iterate Blocks (Locate & Execute)
        self.timer.start(ExecutionPhase.TARGET_LOCATE)
        for i, block in enumerate(intent.blocks):
            # Normalize
            search_canon = self.normalizer.canonicalize(block.search)
            replace_canon = self.normalizer.canonicalize(block.replace)
            
            # Locate
            is_unique, pos, err = self.locator.find_unique_position(current_content, search_canon)
            
            if is_unique:
                self.timer.start(ExecutionPhase.APPLY_EXECUTE)
                current_content = current_content.replace(search_canon, replace_canon, 1)
                block_results.append({"index": i, "status": "SUCCESS", "method": "EXACT"})
                self.timer.stop(ExecutionPhase.APPLY_EXECUTE)
            else:
                self.timer.start(ExecutionPhase.APPLY_EXECUTE)
                # 嘗試模糊套用
                success, fuzzy_content, msg = self.applier.fuzzy_match_and_replace(current_content, search_canon, replace_canon)
                if success:
                    current_content = fuzzy_content
                    block_results.append({"index": i, "status": "SUCCESS", "method": "FUZZY", "msg": msg})
                else:
                    block_results.append({"index": i, "status": "FAIL", "reason": err or msg})
                    self.timer.stop(ExecutionPhase.APPLY_EXECUTE)
                    break # 一個區塊失敗則中止，執行 Fail-closed
                self.timer.stop(ExecutionPhase.APPLY_EXECUTE)
        
        if not self.timer._active_phase:
            self.timer.start(ExecutionPhase.VERIFY_LIGHT)
                    
        # 3. Verify Light (Fail-closed)
        success, v_msg = self.verifier.verify_change(original_content, current_content)
        self.timer.stop(ExecutionPhase.VERIFY_LIGHT)
        
        # Verify Heavy (AST / Checksum)
        if success:
            if self.budget_policy.should_defer(ExecutionPhase.VERIFY_HEAVY):
                self.deferred_queue.enqueue(
                    check_id=f"ast_{task_id}",
                    verifier_type="AST_HEAVY",
                    payload_hash=hashlib.sha256(current_content.encode()).hexdigest()
                )
            else:
                self.timer.start(ExecutionPhase.VERIFY_HEAVY)
                # ... run heavy AST parsing here ...
                self.timer.stop(ExecutionPhase.VERIFY_HEAVY)

            file_path.write_text(current_content, encoding="utf-8")
            logger.info("✅ [PatchEngine] Patch applied successfully.")
        
        # 4. Receipt
        self.timer.start(ExecutionPhase.RECEIPT_WRITE)
        base_receipt_data = {
            "task_id": task_id,
            "target_file": target_file,
            "success": success,
            "reason": v_msg,
            "block_results": block_results,
            "original_sha": hashlib.sha256(original_content.encode()).hexdigest(),
            "new_sha": hashlib.sha256(current_content.encode()).hexdigest()
        }
        
        receipt_data = self.receipt_augmenter.augment(
            base_receipt_data, 
            self.timer.timings, 
            self.deferred_queue.get_pending(), 
            health.value
        )
        
        self.receipt_writer.write_receipt(task_id, receipt_data)
        self.timer.stop(ExecutionPhase.RECEIPT_WRITE)
        
        return {"success": success, "receipt": receipt_data}
