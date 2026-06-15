from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Any, Optional

class OracleAdvisor:
    """
    🔮 Nexus Oracle Advisor v2: 支援維度感應與「絲滑補全」顯示。
    """
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.shadow_dir = self.project_root / ".nexus" / "shadow_runs"

    def synthesize_advice(self, shadow_tid: str, intake_data: Dict[str, Any]) -> str:
        log_file = self.shadow_dir / f"{shadow_tid}.json"
        
        dims = intake_data.get("found_dimensions", {})
        missing = intake_data.get("missing_dimensions", [])
        
        action_type = "bypass"
        affected_scope = []
        evidence_refs = []
        next_step = "fallback_rule_selector"
        confidence = 0.0
        details = {}
        
        if log_file.exists():
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                res = data.get("result", {})
                details = res
                confidence = res.get("confidence", 0.0)
                
                selected_id = res.get("selected_candidate_id")
                abstain_reason = res.get("abstain_reason")
                
                if abstain_reason:
                    action_type = "abstain"
                    next_step = f"fallback_rule_selector: {abstain_reason}"
                elif selected_id:
                    action_type = "select_route"
                    affected_scope = [str(selected_id)]
                    next_step = f"run_verifier: {res.get('required_verifier', 'pytest')}"
            except:
                action_type = "error_fallback"
                next_step = "fallback_rule_selector: failed_to_parse_shadow_log"
        else:
            action_type = "pending_shadow"
            next_step = "wait_for_shadow_execution"

        pact_data = {
            "action_type": action_type,
            "affected_scope": affected_scope,
            "risk_level": "medium",
            "evidence_refs": evidence_refs,
            "next_step": next_step,
            "metadata": {
                "shadow_tid": shadow_tid,
                "confidence": confidence,
                "found_dimensions": dims,
                "missing_dimensions": missing,
                "shadow_details": details
            }
        }
        return json.dumps(pact_data, ensure_ascii=False, indent=2)
