import os
import json
import time
import logging
from typing import Dict, Any, Tuple
from pathlib import Path
from datetime import datetime

# 🛡️ Nexus Feynman Bridge (FNE v2.0)
# A secure, SLA-preserving bridge to getcompanion-ai/feynman.

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("FeynmanBridge")

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPLIANCE_AUDIT_DIR = REPO_ROOT / "compliance" / "audit"

class ComplexityRouter:
    """
    Phase X (eXplore) Router: Decides whether to trigger Feynman's /lit and /deepresearch
    based on task complexity, preserving the <5s P95 SLA for simple bug fixes.
    """
    FAST_PATH_TYPES = ["bug", "hotfix", "chore"]
    DEEP_PATH_TYPES = ["feature", "arch", "research", "epic"]
    
    def __init__(self):
        pass

    def route_task(self, task_metadata: Dict[str, Any]) -> Tuple[str, float]:
        """
        Routes the task and returns (routing_decision, latency_seconds).
        """
        start_time = time.perf_counter()
        
        task_type = task_metadata.get("type", "unknown").lower()
        complexity = task_metadata.get("complexity", "low").upper()

        decision = "FAST_PATH"
        if task_type in self.DEEP_PATH_TYPES or complexity in ["HIGH", "CRITICAL"]:
            decision = "DEEP_PATH"
            logger.info(f"FeynmanRouter: Routing task '{task_metadata.get('id', 'unknown')}' to DEEP_PATH (Feynman /lit)")
        else:
            logger.info(f"FeynmanRouter: Routing task '{task_metadata.get('id', 'unknown')}' to FAST_PATH (Bypass)")

        latency = time.perf_counter() - start_time
        return decision, latency

class DualTrackAudit:
    """
    Phase A (Audit) Verifier: Uses Feynman's /audit functionality as an observe-only
    track to avoid non-deterministic CI blockers, while retaining evidence for SOC2.
    """
    def __init__(self):
        COMPLIANCE_AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    def run_advisory_audit(self, pr_diff: str, task_spec: str) -> Dict[str, Any]:
        """
        Simulates calling Feynman's /audit to compare the PR diff against the original Spec.
        Returns the findings and writes a compliance warning file if drift is detected.
        """
        start_time = time.time()
        
        # 🚀 Mocking Feynman's LLM /audit call
        # In a real environment, this would call `feynman audit --diff ...`
        logger.info("FeynmanVerifier: Running background source-grounded audit...")
        
        findings = {
            "status": "PASS",
            "warnings": [],
            "source_links": [],
            "feynman_latency": 0.0
        }
        
        # Simulate logic drift detection
        if "TODO" in pr_diff or "FIXME" in pr_diff:
            findings["status"] = "WARN"
            findings["warnings"].append("Logical drift: Unresolved TODOs detected in PR diff.")
            findings["source_links"].append("https://feynman.is/audit-rule-01")
        
        findings["feynman_latency"] = time.time() - start_time
        
        # 📝 Write observe-only compliance evidence (SOC2 Traceability)
        if findings["status"] != "PASS":
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_path = COMPLIANCE_AUDIT_DIR / f"feynman_warnings_{timestamp}.json"
            with open(report_path, "w") as f:
                json.dump(findings, f, indent=2)
            logger.warning(f"FeynmanVerifier: Advisory warnings generated at {report_path}")
            
        return findings

if __name__ == "__main__":
    # Quick CLI test
    router = ComplexityRouter()
    print(router.route_task({"id": "BUG-01", "type": "bug", "complexity": "low"}))
    print(router.route_task({"id": "FEAT-02", "type": "feature", "complexity": "high"}))
