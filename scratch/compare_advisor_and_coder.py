import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.engine.canonical_task_seam import execute_single_task_via_service
from nexus.services.s2t_strict import S2T3BAdvisor, S2TCandidate, S2TStrictRuntimeGate

# Set standard environment variables
os.environ["NEXUS_OAUTH_PROVIDER"] = "auto"
os.environ["NEXUS_S2T_3B_ADVISOR_ENABLED"] = "1"
os.environ["NEXUS_S2T_3B_ASSISTED_MODE"] = "low_risk"
os.environ["NEXUS_S2T_3B_ALLOWED_RISK"] = "low"
os.environ["NEXUS_S2T_3B_ADVISOR_FORCE"] = "1"
os.environ["NEXUS_USE_SURGICAL_REPAIR"] = "1"

def reset_easy001():
    project_root = Path("/Users/jameschen/Workspace/nexus/.nexus/bench_cases/easy-001")
    target_file = project_root / "target.py"
    buggy_content = """def normalize_flag(text: str) -> str:
    # intentionally buggy for benchmark
    return text
"""
    target_file.write_text(buggy_content, encoding="utf-8")
    # Clean cached packages to prevent cache hit
    research_file = project_root / "researchpack.json"
    if research_file.exists():
        research_file.unlink()

def run_bench(use_ollama: bool):
    os.environ["NEXUS_S2T_3B_USE_OLLAMA"] = "1" if use_ollama else "0"
    reset_easy001()
    
    project_root = Path("/Users/jameschen/Workspace/nexus/.nexus/bench_cases/easy-001")
    
    t0 = time.monotonic()
    success = execute_single_task_via_service(
        task_text="Fix off-by-one or casing in normalize_flag to output lowercase stripped value.",
        project_root=project_root
    )
    duration = time.monotonic() - t0
    return success, duration

def test_direct_3b_advisor(use_ollama: bool):
    os.environ["NEXUS_S2T_3B_USE_OLLAMA"] = "1" if use_ollama else "0"
    
    candidates = [
        S2TCandidate(
            candidate_id="cand_7b_fix",
            source="ollama",
            content_ref="ref1",
            selector_score=0.8,
            verifier_result="pass",
            evidence_refs=["tests/unit/test_validation.py"]
        ),
        S2TCandidate(
            candidate_id="cand_14b_fix",
            source="ollama",
            content_ref="ref2",
            selector_score=0.9,
            verifier_result="pass",
            evidence_refs=["tests/unit/test_validation.py"]
        )
    ]
    
    gate = S2TStrictRuntimeGate()
    t0 = time.monotonic()
    decision = gate.evaluate(
        task_id="easy-001",
        risk_tier="low",
        candidates=candidates,
        verifier_result="pass"
    )
    duration = time.monotonic() - t0
    return decision, duration

print("==============================================")
print("🔍 Testing Direct 3B S2T Advisor Performance")
print("==============================================")

print("Running 3B Advisor via Ollama...")
dec_ollama, dur_ollama = test_direct_3b_advisor(use_ollama=True)
print(f"Ollama Duration: {dur_ollama:.2f}s, Outcome: {dec_ollama.advisor_outcome_status}")

print("Running 3B Advisor via Native Transformers (CPU)...")
dec_trans, dur_trans = test_direct_3b_advisor(use_ollama=False)
print(f"Transformers Duration: {dur_trans:.2f}s, Outcome: {dec_trans.advisor_outcome_status}")

print("\n==============================================")
print("🚀 Running Full Benchmarks & Comparing")
print("==============================================")

print("Running easy-001 (Ollama Mode)...")
success_ollama, bench_dur_ollama = run_bench(use_ollama=True)
print(f"Ollama Mode Task Success: {success_ollama}, Time: {bench_dur_ollama:.2f}s")
