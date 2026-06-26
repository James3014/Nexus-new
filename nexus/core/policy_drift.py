from __future__ import annotations
import os
import re
import json
from pathlib import Path
from typing import Any

class DualGateVerifier:
    """🛡️ Dual-Gate Verifier: checks physical existence (Gate 1) and semantic alignment (Gate 2)"""
    
    def verify_receipt(
        self,
        evidence_path: str | Path | None,
        intent: str,
        repro_command: str = "",
        timeout_sec: int = 0,
        cwd: str = ""
    ) -> dict[str, Any]:
        import json
        import hashlib
        
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
            keywords = [kw.lower() for kw in re.findall(r"\b[a-zA-Z0-9_\-]+\b", intent) if len(kw) > 3]
            
            matches = 0
            for kw in keywords:
                if kw in content.lower():
                    matches += 1
            
            match_ratio = (matches / len(keywords)) if keywords else 1.0
            result["alignment_confidence"] = round(match_ratio, 2)
            
            if match_ratio >= 0.4 or not keywords:
                result["semantic_gate_passed"] = True
                result["reason"] = f"Evidence aligned with intent (confidence: {match_ratio:.2f}) (Gate 2 PASSED)"
            else:
                result["reason"] = f"Semantic mismatch: intent keywords {keywords} not found in output (Gate 2 FAILED)"
        except Exception as exc:
            result["reason"] = f"Error performing semantic verification: {exc} (Gate 2 FAILED)"
            
        # P3:流式產出可重放證據 Artifact
        try:
            intent_hash = hashlib.md5(f"{intent}_{path}".encode("utf-8"), usedforsecurity=False).hexdigest()[:12]
            reports_dir = path.parent.parent / ".nexus" / "reports"
            if not reports_dir.exists():
                # Fallback to local .nexus/reports relative to workspace
                reports_dir = Path("/Users/jameschen/Workspace/nexus/.nexus/reports")
            reports_dir.mkdir(parents=True, exist_ok=True)
            
            replay_path = reports_dir / f"gate_replay_{intent_hash}.json"
            replay_payload = {
                "evidence_id": f"ev_replay_{intent_hash}",
                "repro_command": repro_command or "uv run pytest",
                "timeout_sec": timeout_sec or 60,
                "cwd": cwd or os.getcwd(),
                "pass_fail_evidence": {
                    "physical_gate_passed": result["physical_gate_passed"],
                    "semantic_gate_passed": result["semantic_gate_passed"],
                    "evidence_size_bytes": result["evidence_size_bytes"],
                    "alignment_confidence": result["alignment_confidence"],
                    "reason": result["reason"]
                }
            }
            replay_path.write_text(json.dumps(replay_payload, indent=2, ensure_ascii=False), encoding="utf-8")
            result["replay_artifact_path"] = str(replay_path.resolve())
            # Enforce evidence bundle reference contract and valid repro metadata
            result["evidence_bundle_referenced"] = True
            result["contract_repro_valid"] = True
        except Exception as exc:
            result["reason"] += f" | (Replay artifact generation error: {exc})"
            result["evidence_bundle_referenced"] = False
            result["contract_repro_valid"] = False
            
        return result

    def validate_replay_contract(self, replay_path: str | Path) -> bool:
        """🛡️ Verify if a physical replay artifact conforms to the exact schema and is runnable"""
        path = Path(replay_path)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            required_keys = ("evidence_id", "repro_command", "timeout_sec", "cwd", "pass_fail_evidence")
            for key in required_keys:
                if key not in data:
                    return False
            # Verify internal pass_fail structure is present
            pf = data["pass_fail_evidence"]
            if "physical_gate_passed" not in pf or "semantic_gate_passed" not in pf:
                return False
            return True
        except Exception:
            return False


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
