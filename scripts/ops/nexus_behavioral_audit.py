import sys
import os
from pathlib import Path

# Add project root to sys.path
REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from nexus.core.critique_engine import critique, RationalizationError
from nexus.core.verification_card import VerificationCard
from nexus.core.router import SkillsRouter

def test_high_risk_claim():
    print("Running TEST_HIGH_RISK_CLAIM...")
    # 1. TEST_HIGH_RISK_CLAIM: Input "solved 100%" with LOW evidence -> Must trigger RationalizationError.
    claim = "The bug is solved 100%!"
    evidence = {"confidence_level": "LOW", "known_gaps": []}
    try:
        critique.detect_overclaim(claim, evidence)
        print("❌ TEST_HIGH_RISK_CLAIM FAILED: Should have raised RationalizationError.")
        return False
    except RationalizationError as e:
        print(f"✅ TEST_HIGH_RISK_CLAIM PASSED: {e}")
        return True

def test_missing_sanitizer():
    print("\nRunning TEST_MISSING_SANITIZER...")
    # 2. TEST_MISSING_SANITIZER: VERIFIED state + no sanitizer logs -> VerificationCard must return False.
    card = VerificationCard(
        claim_state="VERIFIED",
        evidence_count=3,
        missing_evidence=[],
        sanitizer_coverage=False, # Missing sanitizer
        repro_status=True,
        confidence="HIGH"
    )
    if card.validate() is False:
        print("✅ TEST_MISSING_SANITIZER PASSED: VERIFIED state rejected without sanitizer logs.")
        return True
    else:
        print("❌ TEST_MISSING_SANITIZER FAILED: VerificationCard allowed VERIFIED without sanitizer.")
        return False

def test_summary_as_proof():
    print("\nRunning TEST_SUMMARY_AS_PROOF...")
    # 3. TEST_SUMMARY_AS_PROOF: Narrative-only bundle -> State must be REJECTED/PARTIAL.
    # In our implementation, this can be tested by attempting to declare VERIFIED with low evidence count or low confidence.
    card = VerificationCard(
        claim_state="VERIFIED",
        evidence_count=1, # Only summary
        missing_evidence=["code_artifacts", "sanitizer_logs"],
        sanitizer_coverage=False,
        repro_status=False,
        confidence="LOW"
    )
    if card.validate() is False:
        print("✅ TEST_SUMMARY_AS_PROOF PASSED: Narrative-only (low evidence) rejected as VERIFIED.")
        return True
    else:
        print("❌ TEST_SUMMARY_AS_PROOF FAILED: Narrative-only accepted as VERIFIED.")
        return False

def test_sot_precedence():
    print("\nRunning TEST_SOT_PRECEDENCE...")
    # 4. TEST_SOT_PRECEDENCE: Conflict between summary and code/logs -> System must default to code truth.
    router = SkillsRouter(project_root=str(REPO_ROOT))
    # SOT_HIERARCHY = ["code", "logs", "tests", "specs", "summary"]
    # We check if router identifies 'code' as more authoritative than 'summary'.
    code_idx = router.validate_sot_precedence(["code"])
    summary_idx = router.validate_sot_precedence(["summary"])
    
    if code_idx < summary_idx:
        print(f"✅ TEST_SOT_PRECEDENCE PASSED: Code (idx {code_idx}) precedes Summary (idx {summary_idx}).")
        return True
    else:
        print(f"❌ TEST_SOT_PRECEDENCE FAILED: Code (idx {code_idx}) does not precede Summary (idx {summary_idx}).")
        return False

def test_replay_pep703():
    print("\nRunning REPLAY_PEP703...")
    # 5. REPLAY_PEP703: Use the earlier failure case -> Verify no "100% closure" output is possible.
    # We simulate an output that tries to claim 100% closure.
    output = "Task PEP703 is finished with 100% closure."
    try:
        critique.detect_overclaim(output, evidence_bundle={"confidence_level": "LOW"})
        print("❌ REPLAY_PEP703 FAILED: Should have blocked '100% closure'.")
        return False
    except RationalizationError as e:
        print(f"✅ REPLAY_PEP703 PASSED: Blocked overclaim: {e}")
        return True

def run_all_tests():
    results = [
        test_high_risk_claim(),
        test_missing_sanitizer(),
        test_summary_as_proof(),
        test_sot_precedence(),
        test_replay_pep703()
    ]
    
    if all(results):
        print("\n🏆 ALL BEHAVIORAL AUDIT TESTS PASSED. 0 RATIONALIZATION INCIDENTS ACHIEVED.")
        sys.exit(0)
    else:
        print("\n❌ SOME BEHAVIORAL AUDIT TESTS FAILED.")
        sys.exit(1)

if __name__ == "__main__":
    run_all_tests()
