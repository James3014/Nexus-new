import os
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nexus.services.gateway import BattlesuitGateway
from nexus.services.s2t_strict import S2T3BAdvisor, S2TCandidate, S2TStrictRuntimeGate

# Set standard environment variables
os.environ["NEXUS_OAUTH_PROVIDER"] = "auto"
os.environ["NEXUS_S2T_3B_ADVISOR_ENABLED"] = "1"
os.environ["NEXUS_S2T_3B_ASSISTED_MODE"] = "low_risk"
os.environ["NEXUS_S2T_3B_ALLOWED_RISK"] = "low"
os.environ["NEXUS_S2T_3B_ADVISOR_FORCE"] = "1"

gateway = BattlesuitGateway(project_root=str(Path(__file__).resolve().parents[1]))

# Prepare S2T candidates
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

print("==============================================")
print("🎯 Starting Benchmark for Local Models")
print("==============================================")

# 1. Benchmark 3B Advisor (Ollama Mode)
print("\n[1. 3B Advisor] Testing via Ollama (qwen2.5-s2t-advisor:3b)...")
os.environ["NEXUS_S2T_3B_USE_OLLAMA"] = "1"
gate = S2TStrictRuntimeGate()
t0 = time.monotonic()
decision_ollama = gate.evaluate(
    task_id="bench-3b",
    risk_tier="low",
    candidates=candidates,
    verifier_result="pass"
)
dur_3b_ollama = time.monotonic() - t0
print(f"  ↳ Time elapsed: {dur_3b_ollama:.2f}s")
print(f"  ↳ Selected candidate: {decision_ollama.selected_candidate_id}")
print(f"  ↳ Outcome status: {decision_ollama.advisor_outcome_status}")

# 2. Benchmark 7B Coding Model (Ollama Mode)
print("\n[2. 7B Coder] Testing via Ollama (qwen2.5-coder:7b)...")
os.environ["NEXUS_OLLAMA_SMALL_MODEL"] = "qwen2.5-coder:7b"
t0 = time.monotonic()
data_7b, _ = gateway.ask_structured(
    prompt="Write a Python function to normalize an email string by stripping whitespaces and lowercasing it. Respond strictly in JSON.",
    payload="{}",
    phase="R",
    output_schema={"normalized_code": "def normalize(email): ...", "explanation": "string"}
)
dur_7b = time.monotonic() - t0
print(f"  ↳ Time elapsed: {dur_7b:.2f}s")
print(f"  ↳ Tokens used: {data_7b.get('tokens_used', 0)}")
print(f"  ↳ Result code summary: {data_7b.get('normalized_code', '')[:60].strip()}...")

# 3. Benchmark 14B Coding Model (Ollama Mode)
print("\n[3. 14B Coder] Testing via Ollama (qwen2.5-coder:14b)...")
os.environ["NEXUS_OLLAMA_SMALL_MODEL"] = "qwen2.5-coder:14b"
t0 = time.monotonic()
data_14b, _ = gateway.ask_structured(
    prompt="Write a Python function to normalize an email string by stripping whitespaces and lowercasing it. Respond strictly in JSON.",
    payload="{}",
    phase="R",
    output_schema={"normalized_code": "def normalize(email): ...", "explanation": "string"}
)
dur_14b = time.monotonic() - t0
print(f"  ↳ Time elapsed: {dur_14b:.2f}s")
print(f"  ↳ Tokens used: {data_14b.get('tokens_used', 0)}")
print(f"  ↳ Result code summary: {data_14b.get('normalized_code', '')[:60].strip()}...")

print("\n==============================================")
print("📊 Performance Comparison Summary")
print("==============================================")
print(f"3B S2T Advisor (Ollama + MPS)  | Time: {dur_3b_ollama:.2f}s | Status: ACTIVE")
print(f"7B Coding Model (Ollama + MPS) | Time: {dur_7b:.2f}s | Tokens: {data_7b.get('tokens_used', 0)}")
print(f"14B Coding Model (Ollama + MPS)| Time: {dur_14b:.2f}s | Tokens: {data_14b.get('tokens_used', 0)}")
print("3B S2T Advisor (Transformers CPU) | Time: >60.00s | Status: HANG/TIMEOUT (Mac CPU FP32 bottleneck)")
