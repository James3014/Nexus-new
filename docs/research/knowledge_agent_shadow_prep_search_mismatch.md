# Knowledge Agent Shadow Prep — SEARCH_MISMATCH

**Date**: 2026-06-30
**Status**: Shadow-only preparation (no runtime integration)

## Knowledge Agent Scope

Shadow-only. No runtime integration in C12.

## Why SEARCH_MISMATCH Examples Belong in Knowledge Corpus

SEARCH_MISMATCH is the primary blocker for local model solve. The model produces
SEARCH/REPLACE-like output but SEARCH does not match the current source. This is a
knowledge problem (model doesn't know what the current source looks like), not a
parser problem.

Knowledge Agent can help by:
1. Providing exact source examples for similar patterns
2. Retrieving past SEARCH_MISMATCH failures and what worked
3. Supplying source anchoring lessons

## Future Retrieval Use (NOT implemented in C12)

When Knowledge Agent connects to runtime (future sprint):

1. **Prompt examples**: Retrieve valid SEARCH/REPLACE examples where SEARCH matches source exactly
2. **Failure feedback examples**: Retrieve similar SEARCH_MISMATCH failures and successful retries
3. **Similar failure diagnosis**: Find past cases where the same source pattern caused SEARCH_MISMATCH
4. **Source anchoring lessons**: Retrieve rules about copying source exactly

## Corpus Entries to Collect

### Exact locked_search examples
- SEARCH blocks that match source character-for-character
- Cases where SEARCH was copied from provided source context
- Successful patches where SEARCH accuracy was critical

### Stale source examples
- SEARCH blocks that used outdated source code
- Cases where file changed between context capture and patch application
- Lessons about source freshness

### Paraphrased SEARCH examples
- SEARCH blocks that were reformatted or re-indented
- Cases where model "cleaned up" source code in SEARCH
- Lessons about byte-exact copying

### Whitespace mismatch examples
- SEARCH blocks with trailing whitespace differences
- Cases where indentation was shifted
- Lessons about whitespace preservation

### Fenced-but-otherwise-valid examples
- SEARCH/REPLACE blocks wrapped in markdown fences
- Cases where the content was correct but format was wrong
- Lessons about forbidden output formats

### Successful exact SEARCH examples
- End-to-end cases where exact SEARCH led to solved
- Cases where SEARCH accuracy was the differentiator
- Lessons about what makes SEARCH succeed

## Explicitly Forbidden in C12

- No route decision from Knowledge Agent
- No runtime prompt injection
- No KnowledgeHitSignal runtime field yet
- No parser/protocol weakening
- No SEARCH auto-correction
- No fuzzy matching

## Alignment with Downstream Enforcement

Knowledge Agent output is informational only. It cannot:
- Weaken SolidSearchReplaceProtocol
- Auto-correct SEARCH to match source
- Bypass candidate isolation
- Override verifier
