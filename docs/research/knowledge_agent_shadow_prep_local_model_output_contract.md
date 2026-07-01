# Knowledge Agent Shadow Prep — Local Model Output Contract

**Date**: 2026-06-30
**Status**: Shadow-only preparation (no runtime integration)

## Knowledge Agent Role

Knowledge Agent is **infrastructure**, not a new capability. It provides knowledge retrieval
to improve Nexus decision quality. It does NOT:
- Make route decisions
- Override CapabilityPlanner
- Change execution_topology
- Auto-select models
- Inject prompts at runtime

## Shadow-Only Scope (C11)

This sprint prepares Knowledge Agent inputs without connecting to runtime routing.

## Candidate Knowledge Domains

### 1. `nexus-lessons/local_model_output_contract`

Captures patterns about what makes local model output valid vs invalid.

**Source examples to collect:**
- Valid SEARCH/REPLACE blocks (output_class = VALID_SEARCH_REPLACE)
- Fenced SEARCH/REPLACE (output_class = FENCED_SEARCH_REPLACE)
- Unified diff output (output_class = UNIFIED_DIFF)
- Natural language only (output_class = NATURAL_LANGUAGE)
- Refusal responses (output_class = REFUSAL)
- Empty responses (output_class = EMPTY)

### 2. `nexus-policy/downstream_enforcement`

Captures downstream enforcement patterns and why they reject certain outputs.

**Source examples to collect:**
- SEARCH_MISMATCH failures (model output SEARCH doesn't match source)
- REPLACEMENT_MARKDOWN_FENCE rejections
- REPLACEMENT_SYNTAX_INVALID rejections
- NO_BLOCKS_FOUND rejections
- MICRO_VERIFY_CONTEXT_MISSING failures

### 3. `nexus-ops/localheal_failure_taxonomy`

Captures the full taxonomy of LocalHeal failure modes.

**Failure classes:**
- `NO_BLOCKS_FOUND` — model output contains no SEARCH/REPLACE markers
- `REPLACEMENT_MARKDOWN_FENCE` — replacement wrapped in ``` fences
- `UNIFIED_DIFF_OUTPUT` — model used --- a/ / +++ b/ format
- `NATURAL_LANGUAGE_OUTPUT` — model output prose instead of code blocks
- `MALFORMED_SEARCH_REPLACE` — partial markers (SEARCH without REPLACE or vice versa)
- `REFUSAL_DETECTED` — model refused to provide fix
- `SEARCH_MISMATCH` — SEARCH block doesn't match source file
- `REPLACE_SYNTAX_ERROR` — REPLACE block has Python syntax errors
- `MICRO_VERIFY_CONTEXT_MISSING` — no task-scoped interpreter for verification

## Future Usage (NOT implemented in C11)

When Knowledge Agent connects to runtime (future sprint):

1. **Prompt example retrieval**: Retrieve valid SEARCH/REPLACE examples relevant to the task
2. **Failure feedback examples**: Retrieve similar past failures and what worked
3. **Retry guidance**: Suggest retry strategies based on failure class
4. **Report generation**: Auto-generate failure analysis reports

## Future Signal Field (NOT implemented in C11)

```python
# In SignalSnapshot (future):
knowledge_hit_score: float = 0.0  # 0.0 = no hit, 1.0 = high confidence

# In CapabilityPlanner (future):
# knowledge_hit_score is READ-ONLY input
# CapabilityPlanner remains sole route truth
# knowledge_hit_score cannot override route decision
```

## Explicitly Forbidden in C11

- No route decision from Knowledge Agent
- No CapabilityPlanner bypass
- No runtime prompt injection
- No KnowledgeHitSignal runtime field yet
- No automatic model selection change
- No automatic topology change
- No LearningClosure runtime update

## Alignment with Downstream Enforcement

Knowledge Agent output is informational only. It cannot:
- Weaken SolidSearchReplaceProtocol
- Weaken verifier
- Weaken candidate isolation
- Override pipeline_final_patch_len = 0

The downstream enforcement gates remain the sole authority for:
- Accepting/rejecting patches
- Running verification
- Marking solved/unsolved
