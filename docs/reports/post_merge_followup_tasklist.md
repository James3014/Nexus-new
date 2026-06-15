# Post-Merge Follow-up Tasklist (Limited Mount Execution)

This document outlines the actionable follow-up checklist immediately after the merge of branch `feature/bridge-fastmatcher-20260606`.

---

## 📅 Actionable Checklist

### 1. Immediate After Merge (Day 1)
- [ ] **Verify Production Feature Flag State**:  
  Check environment configs. Confirm `NEXUS_SHADOW_ADVISOR_ENABLED` is set to `True` for shadow observations, and `NEXUS_GATEKEEPER_15B_ENABLED` is set to `1` (enabled as optional layer).
- [ ] **Confirm Append-Only Log Initialization**:  
  Verify that the path `.nexus/metrics/s2t_shadow_contract_evidence.jsonl` exists and permissions are set to write/append.
- [ ] **Simulate Core Fallback Recovery (Rollback Drill)**:  
  Execute a manual connection timeout simulation or force L0 offline, confirming that the system retreats back to Python/rule-based core baseline logic in $\le 500$ ms.

### 2. First-Week Observation (Days 2 - 7)
- [ ] **Perform Daily Telemetry Watch**:  
  Inspect the evidence log daily to review performance statistics. Run a daily check script to extract:
  - `verified_success_rate`
  - `trust_mismatch_rate`
  - `public-claim precision`
- [ ] **Short-Task Latency Watch**:  
  Confirm that short task latency remains under 900ms (verifying that the 1.5B Gatekeeper is screening out heavy 7B/14B deliberation queries).
- [ ] **Whitelist Violation Watch**:  
  Check if any 7B/14B model has been triggered on normal syntax check, formatting, or doc-update tasks. Whitelist hit rate must be 100.00%.
- [ ] **Reviewer Feedback Incorporation**:  
  Conduct a manual review of PR comments. If any architectural reviewer requests adjustment to the whitelisted families, manually modify the allowed tags list in `experimental_gate.py`.

### 3. Stop Conditions (Immediate Rollback Criteria)
- [ ] **Trust Mismatch Stop**:  
  If the daily trust mismatch rate rises above **0.00%** (i.e. 3B Advisor overrides or diverges from baseline correctness in active lanes), immediately set `NEXUS_SHADOW_ADVISOR_ENABLED=False` and report to the security officer.
- [ ] **Public-Claim Precision Drop**:  
  If the public-claim precision drops below **100.00%**, disable the corresponding experimental mount points and schedule a rollback drill review.
- [ ] **Latency Penalty Overflow**:  
  If short task average latency exceeds 1000ms due to pre-gate overhead, disable the optional 1.5B gatekeeper by setting `NEXUS_GATEKEEPER_15B_ENABLED=0`.
