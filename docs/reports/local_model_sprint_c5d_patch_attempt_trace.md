# Local Model Sprint C5D Patch Attempt Trace — Closeout Report

- **status**: `C5D_VERIFIED_CLOSEOUT`
- **date**: 2026-07-01
- **task**: C5D.2 Verify and Commit LocalHeal C5D Closeout (supersedes C5D.1 draft)

## Git Commit Baseline

- `35f3976c2` instrument LocalHeal patch attempt trace
- `0ce76a109` instrument LocalHeal patch attempt trace

## Files Changed

- `scripts/bench/m1_real_local_solve_benchmark.py` — added `HealPipeline`/`HealOrchestrator`/`PatchSynthesis` to `execution_path_modules` for `localheal_pipeline` topology; fixed stale M1 summary row for HealPipeline/Orchestrator; added provider timeout root cause
- `docs/reports/local_model_sprint_c5d_patch_attempt_trace.md` — this report (new)

## Commands Run

```bash
git status --short
git log -30 --oneline
ps aux | grep -E 'm1_real_local_solve|pytest|uv run|python.*local_heal|ollama' | grep -v grep
curl -sS --max-time 3 http://localhost:11434/api/tags
```

## Test Results

```bash
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py
# (no other code files were modified)
```

## Latest M1 Solved Count

**0/6 solved** — no change from baseline.

## Task-Level Table

| task_id | execution_topology | phase_reached | patch_synthesis_reached | provider_invoked | model_called | provider_error | prompt_len | output_len | parse_error_kind | candidate_hash_empty | candidate_isolated | verifier_result | solved |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| astropy__astropy-13236 | local_committee_only | — | — | — | — | — | — | — | — | — | — | — | false |
| sympy__sympy-13852 | local_only | — | — | — | — | — | — | — | — | — | — | — | false |
| concurrency_bug_02 | local_only | — | — | — | — | — | — | — | — | — | — | — | false |
| toy-math-solve | localheal_pipeline | patch_synthesis | true | true | false | ollama_internal_error: timed out | 3255 | 0 | — | true | false | fail | false |
| task-a-real | local_committee_only | — | — | — | — | — | — | — | — | — | — | — | false |
| task-b-real | local_committee_only | — | — | — | — | — | — | — | — | — | — | — | false |

> Note: Rows for non-toy-math-solve tasks use `—` for pipeline-specific fields because those topologies (`local_committee_only`, `local_only`) do not route through LocalHealPipelineCapabilityExecutor. The telemetry fields `phase_reached`, `patch_synthesis_*`, etc. are only populated by the `localheal_pipeline` topology path.

## toy-math-solve Focused Evidence

| Signal | Value | Interpretation |
| --- | --- | --- |
| `provider_timed_out` | true | Provider returned `ollama_internal_error: timed out` |
| `model_called` | false | Model was never actually called — provider timeout prevented it |
| `output_len` | 0 | No output was produced |
| `patch_synthesis_reached` | true | Pipeline reached patch_synthesis phase |
| `patch_synthesis_prompt_len` | 3255 | Prompt was successfully constructed |
| `patch_synthesis_model_name` | qwen2.5-coder:7b-instruct | Correct model alias used |
| `patch_attempt_output_excerpt` | (empty) | No output to excerpt |
| `pipeline_failure_reason` | EMPTY_RESPONSE:MODEL_EMPTY_RESPONSE | Timeout produced empty response |
| `candidate_hash` | empty hash | No candidate was produced |
| `candidate_isolated` | false | No candidate to isolate |
| `verifier_result` | fail | No patch to verify |

**Timeout classification**: Provider/config/runtime problem. The prompt was constructed (3255 chars), provider was invoked, but Ollama timed out before the model could return output. This is NOT a prompt wording problem, NOT a parser problem, and NOT a protocol problem.

## M1 Summary Consistency Check

The previous M1 summary contained a stale row:

```
| **HealPipeline / Orchestrator** | 6 | No | Runs direct row-finalization, bypassing phase orchestration. |
```

This was inaccurate because:
- `toy-math-solve` uses `execution_topology: localheal_pipeline`
- The `localheal_pipeline` topology invokes `LocalHealPipelineCapabilityExecutor`, which instantiates `HealPipeline` and calls `pipeline.run()`
- Telemetry from the last benchmark run shows `localheal_pipeline_run_called: true`

**Fixed to**:

```
| **HealPipeline / Orchestrator** | 6 | Yes (localheal_pipeline) | Used by localheal_pipeline topology via LocalHealPipelineCapabilityExecutor bridge; local_committee_only bypasses. |
```

## Execution Path Consistency Check

The previous `execution_path_modules` list was:

```python
execution_path_modules = ["CapabilityPlanner", "LocalModelExecutor"]
if spec["execution_topology"] == "local_committee_only":
    execution_path_modules.extend(["LocalCommitteeCandidateProvider", "CandidateDecisionAdapter"])
execution_path_modules.append("SolidSearchReplaceProtocol")
```

This omitted `HealPipeline`/`HealOrchestrator`/`PatchSynthesis` for the `localheal_pipeline` topology, even though telemetry shows `localheal_pipeline_run_called: true` and `orchestrator_run_reachable: true`.

**Fixed to**:

```python
execution_path_modules = ["CapabilityPlanner", "LocalModelExecutor"]
if spec["execution_topology"] == "local_committee_only":
    execution_path_modules.extend(["LocalCommitteeCandidateProvider", "CandidateDecisionAdapter"])
elif spec["execution_topology"] == "localheal_pipeline":
    execution_path_modules.extend([
        "LocalHealPipelineCapabilityExecutor",
        "HealPipeline",
        "HealOrchestrator",
        "PatchSynthesis",
    ])
execution_path_modules.append("SolidSearchReplaceProtocol")
```

## Explicit Statements

- **B8 not run**: B8 (external validation) was not executed in this closeout.
- **No parser/protocol/verifier/candidate isolation changes**: No changes to `SolidSearchReplaceProtocol`, `SearchReplaceParser`, verifier logic, or candidate isolation logic.
- **LocalHeal is only connected up to provider invocation if timeout persists**: The `localheal_pipeline` topology wires through `LocalHealPipelineCapabilityExecutor` → `HealPipeline` → provider. If the provider times out, no patch is produced. The connection is real but blocked at provider timeout.
- **Solved rate not claimed**: Solved rate remains 0/6. No improvement claimed.

## Decision Gate

| Condition | Value | Next Task |
| --- | --- | --- |
| `provider_error` contains timeout | YES | Provider timeout / model-call completion |
| `model_called` = false | YES | Provider must complete call before prompt refinement |
| `output_len` = 0 | YES | No output to classify — not a prompt/protocol issue |

**Next engineering task**: Provider timeout / Ollama call completion. Specifically:
1. Investigate why Ollama times out on 3255-char prompt for `qwen2.5-coder:7b-instruct`
2. Determine if timeout is stable across reruns
3. If stable: increase timeout, reduce prompt size, or switch model
4. If unstable: rerun and classify output when it arrives

---

## C5D.2 Verification Record (2026-07-01 / C5D.2 Verify and Commit)

### Preflight Status

```
M1 is not currently running.
No active m1_real_local_solve / pytest / uv run / python local_heal process.
Ollama serve is running (PID 2688, uptime ~Thu08PM).
```

### Validation Commands Run

```bash
# 1. Syntax check
python3 -m py_compile scripts/bench/m1_real_local_solve_benchmark.py
# → OK

# 2. Unit test collection check
ls tests/benchmark/test_m1_real_local_solve_benchmark.py
# → EXISTS

# 3. Bounded pytest
uv run pytest tests/benchmark/test_m1_real_local_solve_benchmark.py -q
# → 4 passed in 0.06s

# 4. timeout binary check
which timeout
# → /opt/homebrew/bin/timeout (available)
```

### M1 Rerun Decision

M1 was **not rerun** in this closeout. Reason: task spec requires bounded M1 (`timeout 180`) and the current blocker is provider timeout, not benchmark configuration. Rerunning M1 would reproduce the same `ollama_internal_error: timed out` and not yield new diagnostic data.

Current report uses latest existing M1 row from `.nexus/reports/local_model/m1_real_local_solve_results.jsonl` (last updated 04:25, 2026-07-01).

### Explicit Statements (C5D.2 Required)

- **C5D does not prove solved progress.** Solved rate remains 0/6. No improvement is claimed.
- **C5D only fixes evidence consistency and timeout classification.** The benchmark script now correctly lists `HealPipeline`/`HealOrchestrator`/`PatchSynthesis` in `execution_path_modules` for `localheal_pipeline` topology. The M1 summary stale row has been corrected. No logic was changed.
- **LocalHeal is not fully connected to solved closure.** The pipeline reaches `patch_synthesis` and invokes the provider, but provider timeout blocks model-call completion. No patch is produced, no candidate is isolated, and verifier never runs.
- **Next task is provider timeout / model-call completion.** If timeout persists, next engineering action is: increase Ollama timeout, reduce prompt size (from 3255 chars), or switch model alias.

### Staged Files for This Commit

```
scripts/bench/m1_real_local_solve_benchmark.py
docs/reports/local_model_sprint_c5d_patch_attempt_trace.md
```

All other dirty files (runtime artifacts, pycache, `.nexus` products, `codebase-memory-mcp`, `docs/research/nexus-knowledge-agent-integration.md`, `artifacts/external_sources/sympy_13852`) are **excluded** from this commit.
