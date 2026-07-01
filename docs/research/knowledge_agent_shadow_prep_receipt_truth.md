# Knowledge Agent Shadow Prep — Receipt Truth

**Date**: 2026-06-30
**Status**: Shadow-only preparation (no runtime integration)

## Knowledge Agent Scope

Shadow-only. No runtime integration in C14.

## Why Receipt Truth Examples Belong in Knowledge Corpus

Receipt truth helps diagnose why local model solve fails. Knowledge Agent can
retrieve past receipt patterns to identify common failure modes.

## Corpus Categories

### Executor reached but no model output
- Provider invoked but model returned empty
- Model returned output but no SEARCH/REPLACE markers
- Pipeline ran but patch synthesis failed

### Model output but protocol failure
- SEARCH_MISMATCH: SEARCH didn't match source
- NO_BLOCKS_FOUND: No SEARCH/REPLACE markers
- FENCED_SEARCH_REPLACE: Output wrapped in fences
- REFUSAL: Model refused to provide fix

### Successful pipeline
- Pipeline produced final_patch
- Candidate isolation succeeded
- Verifier passed

## Future Use (NOT implemented in C14)

1. **Failure pattern recognition**: Identify common receipt patterns
2. **Diagnostic guidance**: Suggest next steps based on receipt
3. **Model selection**: Track which models produce better receipts
4. **Prompt optimization**: Correlate prompt changes with receipt improvements

## Explicitly Forbidden in C14

- No runtime prompt injection
- No route decision
- No KnowledgeHitSignal runtime field yet
- No parser weakening
- No automatic model selection
