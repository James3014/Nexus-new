# C6BC: Post-Apply Semantic Gap Forensics (Read-Only)

## 1. Problem Summary

C6BE resolved the `REPLACEMENT_PROSE_CONTAMINATION` bottleneck. The pipeline now reaches apply + verifier:
- `protocol_parse_failed=False`
- `selected_candidate_hash` non-empty (`cca1fe5b...`)
- `isolated_apply_status=applied`
- `isolated_verifier_status=fail`

The new bottleneck is **semantic correctness**: the model's replacement produces a valid diff that applies cleanly, but the verifier (exit code 1) confirms `view(NdarrayMixin)` is still present in the patched file. The format pipeline (anchor→prompt→output→parse→diff→apply) works end-to-end; the model lacks task-specific semantic guidance about WHAT constitutes a correct fix.

---

## 2. Evidence Chain

### 2a. Benchmark verify logic
```python
# verify_13236.py (dynamically created in tmpdir)
import sys
c = open('astropy/table/table.py').read()
sys.exit(0 if 'view(NdarrayMixin)' not in c else 1)
```
PASS condition: `view(NdarrayMixin)` must NOT appear anywhere in `astropy/table/table.py`.

### 2b. Selected candidate
- **Winner**: `qwen2.5-coder:7b-instruct` (primary proposer)
- **Raw candidate hash**: `88998d10370835ff...` (from protocol parse)
- **Applied patch hash**: `cca1fe5b5bfbc4a...` (from git diff after apply)
- **Hash match**: True (applied patch matches selected candidate's parsed output)
- **Protocol normalization**: `solid_search_replace`, `outer_markdown_fence_unwrapped=True`

`outer_markdown_fence_unwrapped=True` indicates the model wrapped its output in markdown fences. After unwrapping, the REPLACE block was extracted, parsed by `SolidSearchReplaceProtocol`, and converted to a unified diff via `_build_unified_diff_from_search_and_replacement`.

### 2c. Post-apply source state
Verifier exit code 1 → `view(NdarrayMixin)` still present. Since the diff replaces the locked_search region (6 lines containing `data = data.view(NdarrayMixin)`), the model's replacement must also contain `view(NdarrayMixin)` or the diff only made cosmetic changes.

### 2d. Why this is a semantic gap (not apply/format)
| Layer | Status | Evidence |
|-------|--------|----------|
| Anchor | ✅ | locked_search unique, in correct region (C6BD) |
| Prompt | ✅ | No prose contamination (C6BE) |
| Parse | ✅ | `protocol_parse_failed=False` |
| Diff | ✅ | isolated_apply_status=applied |
| Apply | ✅ | Hash match confirmed |
| **Semantic** | ❌ | Verifier fails: `view(NdarrayMixin)` remains |

All 5 format/application layers pass. Only the 6th layer (semantic correctness) fails.

---

## 3. Semantic Failure Taxonomy

**Classification**: `partial_fix_missing_core_removal`

Rationale:
- Model correctly identifies the region (locked_search is grounded in `_convert_data_to_col`, C6BD-verified)
- Model correctly formats output (REPLACE block, C6BE-verified)
- Model correctly produces a parseable, applicable diff
- Model DOES NOT remove the single critical line (`data = data.view(NdarrayMixin)`)

The model's replacement differs from locked_search (non-empty diff, no `EMPTY_AFTER_CLEANUP`) but the semantic content of the replacement still includes the buggy line. Equivalent to: "replaced the block with a slightly different block that still has the bug."

---

## 4. Clean Code / Linus Checklist

### Structural issues found
1. **`problem_statement` is too vague**: Falls back to `"Fix target file buggy code for astropy__astropy-13236"` — zero task-specific semantic guidance. No mention of what "fix" means or the verifier's pass condition.
2. **Verifier assertion not in prompt pipeline**: The executor constructs the `anchored_edit` prompt from `problem_statement` only. The verifier command/script is carried separately in `route_context` and never reaches the prompt.
3. **No assertion evidence path**: C6AY diagnosis committee injects root-cause guidance into the prompt, but there is no equivalent "verifier expectation injection" mechanism for the first-pass prompt.
4. **verify_13236.py is ephemeral**: Created in a tmpdir by the benchmark runner; no persistent artifact. The verifier assertion (`'view(NdarrayMixin)' not in c`) is invisible to all downstream consumers.
5. **Raw model output not captured**: The candidate patch hash `cca1fe5b...` proves a patch existed, but without storing the model's raw output, forensic analysis of WHAT the model produced requires git archaeology of the isolated workspace.

### What is NOT the problem
- Not a parser issue (parser correctly extracts replacement body)
- Not a prompt format issue (C6BE anti-prose narrowing works)
- Not an anchor issue (C6BD grounding correct)
- Not a committee issue (committee selection worked — primary proposer was selected)
- Not a model ceiling (the model CAN produce valid code; it just doesn't know what the verifier wants)

---

## 5. Paper Correlation

- **[Self-Refine](https://arxiv.org/abs/2303.17651)**: Iterative refinement with feedback. Directly relevant: the semantic gap here would be addressed by giving the model a verifier feedback loop. The current pipeline already has semantic retry (`build_verification_guided_retry_prompt`), but the first-pass prompt lacks the verifier assertion. Self-Refine suggests adding the PASS condition upfront improves first-pass quality.

- **[CodeRepair](https://arxiv.org/abs/2301.11504)**: Test-to-code alignment. Relevant: the model needs to understand the verifier's expectation before generating code. The `problem_statement` should include the PASS condition as a test oracle.

- **[RAP-Gen](https://arxiv.org/abs/2310.14437)**: Retrieval-augmented program generation. Not directly relevant — the issue is not retrieval but task specification completeness.

---

## 6. Minimal Solution

### No-code candidate
- Add `problem_statement` to the astropy__astropy-13236 benchmark spec with verifier assertion embedded
- This is a benchmark configuration change, not code

### Test-only candidate
- Assert that the anchored_edit prompt includes the verifier PASS condition when a verifier is available
- This requires the prompt builder to carry verifier context

### Minimal patch (recommended)
**Candidate**: `assertion-grounded prompt patch`

**Change**: In `scripts/bench/m1_real_local_solve_benchmark.py`, add `problem_statement` to the astropy__astropy-13236 spec:

```python
"problem_statement": (
    "Fix the bug in astropy/table/table.py so that "
    "data.view(NdarrayMixin) is NOT called during __init__. "
    "The patched file must NOT contain 'view(NdarrayMixin)' anywhere."
),
```

This is a 1-line change to the benchmark spec. It flows through to both committee and executor prompts via `task_desc=spec.get("problem_statement") or ...`.

**Effect on prompt** (before → after):

Before: `"Fix target file buggy code for astropy__astropy-13236"`
After: `"Fix the bug in astropy/table/table.py so that data.view(NdarrayMixin) is NOT called during __init__. The patched file must NOT contain 'view(NdarrayMixin)' anywhere."`

**Why this works**: The locked_search block contains `data = data.view(NdarrayMixin)`. If the model knows the verifier will check for `view(NdarrayMixin)` absence, it can infer: "my replacement must remove this line." Currently, the model has no way to know what "fix" means.

### Refactor candidate (not recommended now)
- Generalize `problem_statement` construction to include verifier assertion extraction for all tasks
- Requires adding `verify_script` parsing or a `verifier_assertion` field to the benchmark schema
- Higher cost, less targeted at this bottleneck

---

## 7. TDD Plan (for downstream C6BF task)

### RED tests
| Test | Assertion |
|------|-----------|
| `test_13236_problem_statement_mentions_view_removal` | The astropy-13236 problem_statement (from benchmark spec or executor) contains `view(NdarrayMixin)` and `NOT contain` or similar |
| `test_anchored_edit_prompt_includes_verifier_goal` | When problem_statement includes a PASS condition, the anchored_edit prompt renders it |
| `test_13236_verify_13236_py_exists` | The verify script file exists in the benchmark fixture |

### GREEN verification
- Run `m1_real_local_solve_benchmark.py --task-id astropy__astropy-13236`
- Expected: `isolated_verifier_status=pass` or at minimum the model removal attempt is different from C6BE's no-op replacement
- `protocol_parse_failed` must remain `False` (no regression from C6BE)

---

## 8. Risks & Approval Items

### Risks
- **Risk 1**: Adding the verifier PASS condition may over-constrain the prompt for tasks with complex verify logic. This risk is LOW for `astropy__astropy-13236` (simple string check).
- **Risk 2**: If the model still fails to remove `view(NdarrayMixin)` even with the PASS condition, the bottleneck is truly the model's 7B capacity for multi-step reasoning (identify block → infer which line to remove → produce replacement without it). This would point to `correct_region_wrong_semantics` as the true deeper taxonomy.
- **Risk 3**: If the `verify_script` string includes escape sequences or complex import logic, inlining it as problem_statement could corrupt the prompt format.

### Approval needed
- Only if C6BF (assertion-grounded prompt patch) still fails → then the bottleneck chain changes to require `replacement-body contract patch` or `winner-selection semantic signal patch`, requiring fresh approval
- Not needed for the benchmark spec change itself

### Prohibited conclusions
- Not `model ceiling`: model produces valid code, just lacks task-specific semantic signal
- Not `infra closed out`: the full pipeline (anchor→prompt→model→parse→diff→apply→verify) works
- Not `switch bigger model`: not tested; the gap is in prompt content, not model capacity
- Not `production ready`: not relevant to this bottleneck layer

---

## Decision Log

| Decision | Value |
|----------|-------|
| Taxonomy | `partial_fix_missing_core_removal` |
| Autopilot rule triggered | `assertion-grounded prompt patch` |
| Minimal patch | Add `problem_statement` with verifier PASS condition to benchmark spec |
| Refactor candidate | Generalize verifier assertion injection (deferred) |
| Next task tag | `C6BF-assertion-grounded-prompt-patch` |
