# LocalHeal Sprint C15-4D-0: Delegated Retry Protocol Contract Reuse Audit

**Status**: `C15_4D_0_DELEGATED_RETRY_PROTOCOL_CONTRACT_REUSE_AUDIT_PASS`

**Date**: 2026-07-03

---

## Files Inspected

- `nexus/services/local_heal/local_model_executor.py` (delegated retry path)
- `nexus/services/local_heal/orchestrator.py` (orchestrator semantic retry path)
- `nexus/services/local_heal/corrector.py` (SelfCorrector.build_retry_prompt)
- `nexus/services/local_heal/prompt_builder.py` (PromptBuilder.build_patch_system_prompt, build_verification_guided_retry_prompt)
- `nexus/services/local_heal/pipeline.py` (HealPipeline)

---

## C11/C13 Protocol Contract Summary

C11/C13 established the SEARCH/REPLACE output protocol contract via `PromptBuilder.build_patch_system_prompt()`:

| Contract Element | C11/C13 Contract |
|-----------------|------------------|
| Exact SEARCH/REPLACE format | ✅ Required (`<<<<<<< SEARCH` / `=======` / `>>>>>>> REPLACE`) |
| Valid example first | ✅ Few-shot example included |
| Forbidden output types | ✅ No markdown fences, no unified diff, no prose |
| Instruction not to use markdown fences | ✅ Explicit "FORBIDDEN: Markdown code fences" |
| Instruction not to include line numbers | ✅ "Do NOT include line numbers" |
| Source anchoring | ✅ "SEARCH must be copied EXACTLY from CURRENT SOURCE" |
| Indentation rules | ✅ "The indentation of the code inside REPLACE must match" |
| No placeholders | ✅ "No placeholders ('# ...', '... code ...')" |

---

## Delegated Retry Prompt Path Map

```
LocalModelExecutor (localheal_pipeline topology)
  │
  ├── delegated retry eligibility check
  │     (semantic_retry_evidence_ready=true, failure_class=verification_failed,
  │      candidate_isolated=true, hash_match=true)
  │
  ├── retry_prompt = SelfCorrector().build_retry_prompt(
  │     original_user_prompt=request.problem_statement,
  │     error=PatchError(kind=LOGIC_REGRESSION, message="Verifier failed..."),
  │     targeted_files=request.target_file,
  │   )
  │
  ├── heal_ctx = LegacyHealContext(user_prompt=retry_prompt, ...)
  │
  ├── result_ctx = pipeline.run(heal_ctx)
  │
  └── pipeline → orchestrator → PatchSynthesisPhase → PromptBuilder.build_patch_user_prompt()
```

**Key finding**: The delegated retry uses `SelfCorrector.build_retry_prompt()` which appends error-specific instructions to the original user prompt. The actual SEARCH/REPLACE protocol contract comes from `PromptBuilder.build_patch_system_prompt()` which is called inside `PatchSynthesisPhase`.

---

## Checklist of Protocol Contract Fields

| Contract Element | C11/C13 Primary | Delegated Retry | Status |
|-----------------|-----------------|-----------------|--------|
| Exact SEARCH/REPLACE format | ✅ `build_patch_system_prompt` | ✅ `SelfCorrector` says "Output a valid SEARCH/REPLACE block" | **CONTRACT_REUSED** |
| Valid example first | ✅ Few-shot in system prompt | ✅ System prompt is same (`build_patch_system_prompt`) | **CONTRACT_REUSED** |
| Forbidden output types | ✅ "FORBIDDEN: Markdown code fences" | ✅ Same system prompt | **CONTRACT_REUSED** |
| Instruction not to use markdown fences | ✅ Explicit | ✅ Same system prompt | **CONTRACT_REUSED** |
| Instruction not to include line numbers | ✅ "Do NOT include line numbers" | ✅ Same system prompt | **CONTRACT_REUSED** |
| Source anchoring | ✅ "SEARCH must be copied EXACTLY" | ✅ Same system prompt | **CONTRACT_REUSED** |
| Indentation rules | ✅ "indentation must match" | ✅ Same system prompt | **CONTRACT_REUSED** |
| No placeholders | ✅ "No placeholders" | ✅ Same system prompt | **CONTRACT_REUSED** |
| Verifier evidence | ❌ Not in primary | ✅ C15-3A/B/C injected | **ADDED (improvement)** |
| Prior failure reason | ❌ Not in primary | ✅ SelfCorrector adds error-specific instructions | **ADDED (improvement)** |

---

## Contract Reuse Classification

**`CONTRACT_REUSED`**

The delegated retry path fully reuses the C11/C13 SEARCH/REPLACE output protocol contract. The system prompt (`build_patch_system_prompt`) is the same for both primary and delegated retry paths. The delegated retry adds:
1. Verifier evidence (C15-3A/B/C improvement)
2. Error-specific retry instructions (SelfCorrector improvement)

Neither addition weakens the protocol contract. Both additions are additive improvements.

---

## Evidence Snippets

### Delegated retry uses same system prompt

`local_model_executor.py:1741-1748`:
```python
retry_prompt = SelfCorrector().build_retry_prompt(
    original_user_prompt=request.problem_statement,
    error=PatchError(
        kind=PatchErrorKind.LOGIC_REGRESSION,
        message=f"Verifier failed with exit code {raw_meta['verifier_exit_code']}",
    ),
    targeted_files=request.target_file,
)
```

`SelfCorrector.build_retry_prompt()` appends error-specific instructions to the original user prompt. The system prompt is set separately via `PromptBuilder.build_patch_system_prompt()` inside `PatchSynthesisPhase`.

### SelfCorrector includes SEARCH/REPLACE format requirement

`corrector.py:39`:
```python
f"Output a valid SEARCH/REPLACE block with the corrected logic."
```

### System prompt includes full C11/C13 contract

`prompt_builder.py:33-55` (7B model):
```python
"HARD OUTPUT CONTRACT: Your response MUST be exactly one SEARCH/REPLACE block.\n"
"Any prose, explanation, markdown, or text outside the block will be REJECTED.\n\n"
"VALID EXAMPLE (copy this format exactly):\n"
"FILE: src/utils.py\n"
"<<<<<<< SEARCH\n    return os.path.join(a, b)\n=======\n"
"    return os.path.join(a, b) if a and b else ''\n>>>>>>> REPLACE\n\n"
"SOURCE ANCHORING (CRITICAL):\n"
"- SEARCH must be copied EXACTLY from the CURRENT SOURCE / LOCKED SEARCH below.\n"
...
"FORBIDDEN (will be rejected):\n"
"- Markdown code fences (```) around SEARCH/REPLACE\n"
"- Unified diff format (--- a/ or +++ b/)\n"
"- Explanations, prose, or text before/after blocks\n"
```

---

## Residual Risk

The protocol contract is fully reused. The delegated retry failures (REPLACE_SYNTAX_ERROR, SEARCH_MISMATCH) are **model output quality issues**, not protocol contract issues. The model is producing patches that violate the existing contract (wrong indentation, SEARCH mismatch), not patches that bypass the contract.

---

## Recommended Next Task

**C15-4D-1 Delegated Retry Output Quality Ceiling / Claim Boundary**

Since the protocol contract is fully reused, the next task should:
1. Define what can be claimed about delegated retry given current model quality
2. Determine if delegated retry output quality can be improved without prompt changes
3. If not, define the claim boundary for delegated retry

---

## Statements

- **No runtime behavior changed**: This task only performed read-only inspection.
- **No route authority changed**: No new RouteMode, Router, Planner, or topology selector.
- **No parser/verifier/candidate isolation changed**: No changes to these systems.
- **delegated_retry solved NOT_PROVEN**: This task does not prove delegated_retry solved.
- **production_ready=false**: This audit is not production-ready.
- **public_claim_allowed=false**: No public claims are allowed.
