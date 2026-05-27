from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any

class DualGateVerifier:
    """🛡️ Dual-Gate Verifier: checks physical existence (Gate 1) and semantic alignment (Gate 2)"""
    
    def verify_receipt(self, evidence_path: str | Path | None, intent: str) -> dict[str, Any]:
        result = {
            "physical_gate_passed": False,
            "semantic_gate_passed": False,
            "evidence_size_bytes": 0,
            "alignment_confidence": 0.0,
            "reason": ""
        }
        
        if not evidence_path:
            result["reason"] = "Physical evidence path is empty or None (Gate 1 FAILED)"
            return result
            
        path = Path(evidence_path)
        if not path.exists():
            result["reason"] = f"Physical evidence file does not exist at: {path} (Gate 1 FAILED)"
            return result
            
        size = path.stat().st_size
        result["evidence_size_bytes"] = size
        if size == 0:
            result["reason"] = "Physical evidence file exists but is empty (0 bytes) (Gate 1 FAILED)"
            return result
            
        # Gate 1 Passed
        result["physical_gate_passed"] = True
        
        # Gate 2: Semantic Verification (Dual-Gate)
        # Mock-fallback based on intent feature mapping & consistency checks
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            # Extract keywords from intent
            keywords = [kw.lower() for kw in re.findall(r"\b[a-zA-Z0-9_\-]+\b", intent) if len(kw) > 3]
            
            matches = 0
            for kw in keywords:
                if kw in content.lower():
                    matches += 1
            
            match_ratio = (matches / len(keywords)) if keywords else 1.0
            result["alignment_confidence"] = round(match_ratio, 2)
            
            # Semantic alignment is successful if confidence meets the threshold (e.g. >= 0.4 or if intent has low complexity)
            if match_ratio >= 0.4 or not keywords:
                result["semantic_gate_passed"] = True
                result["reason"] = f"Evidence aligned with intent (confidence: {match_ratio:.2f}) (Gate 2 PASSED)"
            else:
                result["reason"] = f"Semantic mismatch: intent keywords {keywords} not found in output (Gate 2 FAILED)"
        except Exception as exc:
            result["reason"] = f"Error performing semantic verification: {exc} (Gate 2 FAILED)"
            
        return result


class PolicyDriftDetector:
    """🛡️ PolicyDriftDetector: auto-audits execution paths against allowed and forbidden paths from AGENTS.md"""
    
    ALLOWED_SUBDIRS = ("scripts/ops", "nexus_wiki_vault", "docs")
    FORBIDDEN_PATTERNS = re.compile(r"(\.obsidian|benchmarks|logs|nexus_swarm|packages)/")
    
    def __init__(self, proto_path: str | Path = "MUSE_PROTO.md"):
        self.proto_path = Path(proto_path)
        
    def detect_drift(self, active_path: list[str]) -> dict[str, Any]:
        result = {
            "drift_detected": False,
            "violations": [],
            "reason": "All active paths comply with agent boundary policy."
        }
        
        for path_str in active_path:
            # 1. Check forbidden paths pattern
            if self.FORBIDDEN_PATTERNS.search(path_str):
                result["drift_detected"] = True
                result["violations"].append(f"Forbidden path accessed: {path_str}")
                continue
                
            # 2. Check general routing constraints (e.g. unruled actions/scripts outside permitted zones)
            # Ensure operations are within allowed path scope
            is_allowed = False
            # Check if it's in project root files directly (e.g. scripts or markdown files in root)
            path_parts = Path(path_str).parts
            if len(path_parts) <= 1:
                is_allowed = True
            else:
                # Check permitted directories
                for allowed in self.ALLOWED_SUBDIRS:
                    if path_str.replace("\\", "/").startswith(allowed):
                        is_allowed = True
                        break
                        
            # If a path isn't allowed, it represents an unruled action or potential breakout
            if not is_allowed:
                result["drift_detected"] = True
                result["violations"].append(f"Unruled out-of-boundary path action: {path_str}")
                
        if result["drift_detected"]:
            result["reason"] = f"Drift detected. Violations: {result['violations']}"
            
        return result
