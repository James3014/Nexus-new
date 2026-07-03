# Local Model Sprint C15-4A: Solved Claim Gate and Delegated Retry Coverage

**Date**: 2026-07-04  
**Status**: CLOSED - claim gate tightened; receipt-path truth gap fixed; first-pass solve, in-pipeline semantic retry solve, and delegated retry coverage separated.

## 1. Scope

Goal:

```text
Do not treat C15-3 as "fully solved".
Separate:
1. toy first-pass solved
2. in-pipeline semantic retry solved
3. delegated retry branch wiring
4. delegated retry solved
```

Inputs reviewed:

```text
- /Users/jameschen/.codex/attachments/f4a67b9b-659b-4a9c-a42c-08d20ccc5d69/pasted-text.txt
- docs/reports/local_model_sprint_c15_3v_delegated_retry_source_alignment.md
- docs/reports/local_model_sprint_c15_3w_verifier_evidence_and_logic_repair.md
- .nexus/reports/local_model/m1_real_local_solve_results.jsonl
- .nexus/reports/local_heal/toy-math-solve/receipt.json
- .nexus/reports/local_heal/toy-math-forced-retry/receipt.json
- /Users/jameschen/Downloads/Nexus_Knowledge_Agent_Integration_v2.md
```

## 2. Dirty Tree Audit

Observed before edits:

```text
git status --short
...
M scripts/bench/m1_real_local_solve_benchmark.py
...
```

Dirty diff meaning:

```text
scripts/bench/m1_real_local_solve_benchmark.py had an unstaged new task:
toy-math-forced-retry
```

Interpretation:

```text
This was not runtime noise.
It was a deliberate next-step claim-gate probe intended to test forced retry coverage.
```

## 3. Commit Chain Summary

Confirmed chain:

```text
b3d6671c7 fix(localheal): C15-3W align verifier telemetry projection and add actionable task description to achieve verified SOLVED status
4c70ef06d fix(localheal): C15-3V pre-populate localized_files with locked_search to eliminate delegated retry SEARCH_MISMATCH
3827b9f09 fix(localheal): C15-3U map model aliases in delegated retry wrappers and write mitigation report
84fbaa90e fix(localheal): C15-3U implement delegated retry provider observability fields and fix report hygiene
164add5a1 fix(localheal): C15-3T diagnose delegated retry provider wiring and add stage telemetry
8f05bad77 docs: record LocalHeal C15-3S reanchor locked search stability closure
bae86a438 fix(localheal): C15-3S fix reanchor stale-read when pipeline modifies target file
```

## 4. Claim Gate Findings

### 4.1 Proven first-pass solved

Evidence:

```text
docs/reports/local_model_sprint_c15_3w_verifier_evidence_and_logic_repair.md
Outcome=SOLVED
task_id=toy-math-solve
verifier_result=pass
solved=true
delegated_retry_stage=not_invoked
```

Conclusion:

```text
toy first-pass verified solve is PROVEN.
```

### 4.2 Proven in-pipeline semantic retry solve

Evidence:

```text
.nexus/reports/local_model/m1_real_local_solve_results.jsonl
latest live rerun row
task_id=toy-math-forced-retry
receipt_path=/Users/jameschen/Workspace/nexus/.nexus/reports/local_heal/toy-math-forced-retry/receipt.json
verifier_result=pass
solved=true
semantic_retry_invoked=true
semantic_retry_count=1
pipeline_retry_delegated=false
delegated_retry_stage=not_invoked
retry_not_invoked_reason=already_solved
duration_sec=30.66
```

Receipt evidence:

```text
.nexus/reports/local_heal/toy-math-forced-retry/receipt.json
solve_eligible=true
latency_ledger.phases includes:
- verify_attempt_1 success=false
- patch_attempt_2 success=false error=FILE_NOT_FOUND:UNKNOWN_PENDING
- patch_attempt_3 success=true
- verify_attempt_3 success=true
eval_metrics.retry_count=2
```

Conclusion:

```text
Forced verifier-failure recovery is PROVEN inside the primary LocalHeal pipeline.
This proves semantic retry repair can recover to SOLVED in at least one bounded toy case.
This does NOT prove delegated retry solved.
```

### 4.3 Delegated retry branch remains wired-but-not-solved

Evidence:

```text
docs/reports/local_model_sprint_c15_3v_delegated_retry_source_alignment.md
delegated_retry_stage=first_patch_failed
delegated_retry_status=SUCCESS
semantic_retry_status=VERIFIER_FAILED
verifier_result=fail
solved=false
```

Conclusion:

```text
Delegated retry branch reachability is PROVEN.
Delegated retry solved is NOT proven.
```

## 5. Receipt Truth Gap Fixed

Problem:

```text
Benchmark rows wrote:
receipt_path=.nexus/receipts/<task>_receipt.json
```

But actual receipt lives at:

```text
.nexus/reports/local_heal/<task>/receipt.json
```

Impact:

```text
Claim-gate reports and downstream readers could point to a non-existent file even when a real receipt existed.
```

Fix:

```text
scripts/bench/m1_real_local_solve_benchmark.py now resolves receipt_path from:
1. finalized.receipt_path
2. receipt.final_receipt_path
3. receipt.receipt_path
4. adapter.receipt_path
5. adapter.metadata.receipt_path
6. fallback: .nexus/reports/local_heal/<task>/receipt.json
```

Boundary:

```text
This is receipt projection repair only.
No route/planner/verifier/candidate-isolation behavior changed.
```

## 6. Capability Claim Matrix

| Capability | Status | Evidence |
| --- | --- | --- |
| CapabilityPlanner route authority | PROVEN | benchmark rows keep `route_truth_source=CapabilityPlanner`, `adapter_output_is_route_truth=false` |
| LocalModelExecutor downstream consumer | PROVEN | C15-3V/C15-3W reports plus latest forced-retry live row |
| HealPipeline first-pass patch | PROVEN | C15-3W report `toy-math-solve solved=true` |
| locked_search / reanchor | PROVEN | latest forced-retry live row `protocol_used=pipeline_result_locked_search_reanchored` |
| candidate isolation | PROVEN | C15-3V report and latest forced-retry live row |
| hash gate | PROVEN | C15-3V report and latest forced-retry live row |
| provider alias mapping | PROVEN | C15-3U report plus non-empty provider responses in later rows |
| provider prompt/response observability | PROVEN | delegated retry provider fields populated in attempt 13 |
| delegated retry branch reachability | PROVEN | attempt 13 `pipeline_retry_delegated=true` |
| delegated retry provider call | PROVEN | earlier C15-3T/C15-3U evidence; attempt 13 status path advanced past provider |
| delegated retry source alignment | PROVEN | C15-3V row cleared SEARCH_MISMATCH |
| delegated retry SEARCH_MISMATCH clearance | PROVEN | attempt 13 `delegated_retry_status=SUCCESS` |
| semantic retry valid patch generation | PARTIAL | attempt 13 valid patch but verifier fail; attempt 16 recovered via primary pipeline semantic retry |
| semantic retry verifier-guided logic repair | PARTIAL | attempt 16 solved after retries, but delegated branch still not solved |
| verifier result projection | PROVEN | C15-3W plus current receipt-path fix removed evidence-pointer ambiguity |
| toy first-pass solved | PROVEN | C15-3W report |
| forced repair solved | PROVEN | latest forced-retry live rerun |
| forced delegated repair solved | NOT_TESTED | latest forced-retry live rerun used in-pipeline semantic retry, not delegated branch |
| multi-task generalization | NOT_TESTED | no new multi-task live proof in this packet |
| learning closure correctness | PARTIAL | learning artifacts exist, but C15-4A did not audit closure semantics deeply |
| production readiness | DO_NOT_CLAIM | no qualifying evidence |
| public claim readiness | DO_NOT_CLAIM | receipts explicitly `public_claim_allowed=false` |

## 7. Non-Claims

Do not claim:

```text
- C15-3 fully complete
- delegated retry repair solved
- local armor ready
- production_ready
- public_claim_allowed
- multi-task robustness
```

Accurate claim:

```text
- toy first-pass verified solve achieved
- forced verifier-failure repair solve achieved inside the primary LocalHeal pipeline
- delegated retry branch is wired and observable
- delegated retry solved remains unproven
```

## 8. Knowledge Agent Alignment

Reference:

```text
/Users/jameschen/Downloads/Nexus_Knowledge_Agent_Integration_v2.md
```

Relevant alignment for this lane:

```text
Knowledge Agent should be prepared as downstream knowledge infrastructure, not new route authority.
For local-model / LocalHeal work, any knowledge-hit signal must remain:
- consumer-side
- observational or planner-input only
- incapable of bypassing CapabilityPlanner or verifier authority
```

Implication for the next sprint:

```text
Do not mix Knowledge Agent integration with C15-4A claim gating.
Prepare interface points only:
- receipt-backed knowledge evidence inputs
- planner-readable signal fields
- closure writeback hooks
Do not add new route mode, topology, or selector behavior in this lane.
```

## 9. Next Recommended Sprint

```text
C15-4B Delegated Retry Solved Proof
```

Required outcome:

```text
Produce one bounded task where:
1. first verification fails
2. delegated retry branch is actually invoked
3. delegated retry branch reaches verifier pass
4. report clearly distinguishes delegated solve from in-pipeline semantic retry solve
```

Suggested guardrails:

```text
- keep toy scope bounded
- keep parser/verifier/candidate isolation unchanged
- keep CapabilityPlanner as route truth
- record which retry mechanism solved the task:
  first_pass
  pipeline_semantic_retry
  delegated_retry
```

## 10. Verification Evidence

Commands:

```bash
git status --short
git diff -- scripts/bench/m1_real_local_solve_benchmark.py
git log -8 --oneline
git show --stat --oneline --no-renames HEAD
tail -n 5 .nexus/reports/local_model/m1_real_local_solve_results.jsonl
sed -n '1,240p' .nexus/reports/local_heal/toy-math-solve/receipt.json
sed -n '1,260p' .nexus/reports/local_heal/toy-math-forced-retry/receipt.json
uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -q
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py
```
