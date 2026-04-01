import re
import logging
import json
from typing import Dict, List, Any, Optional
from nexus.services.reach.ucc_router import UCCRouter
from nexus.core.skill_outcomes import build_outcome_event, append_skill_outcome_event, OutcomePayload
from pathlib import Path

logger = logging.getLogger(__name__)

class DiagnosisVetoError(Exception):
    """🩺 診斷否決異常：當官方文檔與預測衝突時拋出"""
    pass

class SpecGuardV2:
    """🛡️ [Phase 2.1] Spec-Guard v2: Constitutional & Anti-Hallucination Gate"""
    
    FORBIDDEN_PATTERNS = [
        r"sdd\.os",             # Legacy repo references
        r"os\.system\(",        # Unsafe syscalls
        r"subprocess\.check_output\(shell=True\)",
        r"/Users/jameschen/sdd\.os",
    ]

    def __init__(self, spec_path: str = "MUSE_ENGINE_SPEC.md"):
        self.spec_path = spec_path
        self.router = UCCRouter()

    def audit_diff(self, diff_text: str) -> Dict[str, Any]:
        """[Legacy Hook] 審計變更內容是否違憲"""
        violations = []
        for pattern in self.FORBIDDEN_PATTERNS:
            if re.search(pattern, diff_text, re.IGNORECASE):
                violations.append(f"VIOLATION: Detect prohibited pattern '{pattern}'")
        
        is_vetoed = len(violations) > 0
        return {
            "status": "VETOED" if is_vetoed else "PASSED",
            "violations": violations,
            "audit_mode": "v23-Hardened"
        }

    def validate_diagnosis(self, diagnosis: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
        """
        🧬 [Phase 2.1] 動態抗幻校核 (Doc Grounding)
        職責: 偵測診斷中的 API 連結，抓取實體文檔並校核性能性能分析內容內容內容。
        """
        rootcase = diagnosis.get("rootcause", "")
        prediction = diagnosis.get("prediction", "")
        
        # 1. 提取官方 API/Doc 連結
        api_mentions = self._extract_api_mentions(rootcase + " " + prediction)
        if not api_mentions:
            return {"status": "PASS", "veto_count": 0}

        veto_events = []
        context.setdefault("ground_truth_docs", [])
        
        logger.info("🛡️ [Spec-Guard] Found %d API Mentions. Reaching for Ground Truth...", len(api_mentions))
        
        for api_url in api_mentions[:2]: # Phase 1 限流策略內容內容
            try:
                # 2. UCC 智慧觸達
                reach_result = self.router.reach(url=api_url, tier=1)
                
                # 將 ReachResult 轉為 dict 以相容既有邏輯內容性能性能
                reach_result_dict = reach_result.model_dump() if hasattr(reach_result, "model_dump") else (reach_result if isinstance(reach_result, dict) else vars(reach_result))
                
                # 3. 執行 Doc Conflict 檢定 (重合度判定內容性能)
                if self._doc_conflict(diagnosis, reach_result_dict):
                    veto_event = {
                        "decision_id": reach_result_dict.get("decision_id"),
                        "url": api_url,
                        "veto_type": "doc_conflict",
                        "expected_logic": rootcase[:100],
                        "actual_doc_fragment": reach_result_dict.get("markdown", "")[:300],
                        "confidence": reach_result_dict.get("confidence", 0.0)
                    }
                    veto_events.append(veto_event)
                    
                    # 4. 注入證據 (Phase 2.2 Learning 預備)
                    context["ground_truth_docs"].append(reach_result_dict)
                    
                    # 5. [Evidence 4] Telemetry Logging (D-Phase) 內容內容內容
                    self._log_veto_outcome(reach_result_dict)
                    
            except Exception as e:
                logger.warning("   ↳ [Spec-Guard] Reach failed for %s: %s", api_url, e)

        if veto_events:
            logger.error("🚫 [Spec-Guard] HARD_VETO! Doc conflict detected across %d items.", len(veto_events))
            return {
                "status": "HARD_VETO",
                "veto_count": len(veto_events),
                "injected_docs": len(context.get("ground_truth_docs", [])),
                "events": veto_events
            }
        
        return {"status": "PASS", "veto_count": 0}

    def _extract_api_mentions(self, text: str) -> List[str]:
        """提取官方文檔 URL"""
        pattern = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+[/\w\.-]*(?:com|io|dev|org|net)/docs/[/\w\.-]*'
        urls = re.findall(pattern, text, re.IGNORECASE)
        # 去重內容及性能內容性能性能
        return list(dict.fromkeys(urls))

    def _doc_conflict(self, diagnosis: Dict[str, Any], reach_result: Dict[str, Any]) -> bool:
        """
        🧠 衝突檢定：
        利用關鍵字重合度 (Keyword Overlap)。若診斷提到的關鍵字在官方 Doc 中出現率低於 20%，判定為衝突 (Hallucination)。
        """
        doc_content = reach_result.get("markdown", "").lower()
        if not doc_content: return False
        
        # 提取診斷中的關鍵字 (去停用詞內容性能性能)
        diag_text = (diagnosis.get("rootcause", "") + " " + diagnosis.get("prediction", "")).lower()
        diag_keywords = set(re.findall(r'\b\w{4,}\b', diag_text)) # 僅取 4 字母以上單字內容性能內容
        
        if not diag_keywords: return False
        
        # 計算重合度內容及性能內容性能性能
        found_keywords = [k for k in diag_keywords if k in doc_content]
        overlap_ratio = len(found_keywords) / len(diag_keywords)
        
        logger.info("🧪 [Spec-Guard:Audit] Overlap Ratio: %.2f (Threshold: 0.20)", overlap_ratio)
        
        return overlap_ratio < 0.20

    def _log_veto_outcome(self, result: Dict[str, Any]):
        """寫入成果事件到 D 階段 Telemetry內容內容內容及性能分析內容及其內容內容"""
        try:
            payload = OutcomePayload(
                task_id="ANTI-HALLUCINATION-VETO",
                phase="D",
                decision_id=result.get("decision_id", "VETO-000"),
                skill_id="spec_guard_v2",
                passed=False, # Veto 代表檢查沒通過 (Hallucination Detected)
                proof_present=True,
                metadata={
                    "status": "VETOED",
                    "resolver": result.get("resolver"),
                    "source": "spec_guard.veto"
                }
            )
            event = build_outcome_event(payload)
            append_skill_outcome_event(Path("."), event)
        except Exception as e:
            logger.error("   ↳ [Telemetry] Failed to log Veto: %s", e)
