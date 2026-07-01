# Knowledge Agent Shadow Prep — Protocol Adherence

**Date**: 2026-06-30
**Status**: Shadow-only preparation (no runtime integration)

## Knowledge Agent Scope

Shadow-only. No runtime integration in C13.

## Why Protocol Adherence Examples Belong in Knowledge Corpus

Local model output is non-deterministic: sometimes produces SEARCH/REPLACE blocks,
sometimes produces natural language, sometimes produces code without markers. This
is a protocol adherence problem that Knowledge Agent can help address by providing
examples and failure patterns.

## Corpus Categories

### Natural language instead of blocks
- Model output explanations instead of SEARCH/REPLACE
- Model apologizes or refuses
- Model describes what it would do instead of doing it

### Code without SEARCH/REPLACE
- Model outputs raw code changes without markers
- Model outputs unified diff format
- Model outputs code with explanations

### Search mismatch
- SEARCH block doesn't match current source
- SEARCH uses stale source
- SEARCH paraphrases source

### Fenced output
- SEARCH/REPLACE wrapped in markdown code fences
- Content is correct but format is wrong

### Refusal
- Model refuses to provide fix
- Model says it can't help
- Model apologizes

### Successful exact block
- Model produces correct SEARCH/REPLACE
- SEARCH matches source exactly
- REPLACE makes valid change

## Future Use (NOT implemented in C13)

1. **Prompt construction**: Retrieve successful examples for similar tasks
2. **Failure feedback**: Retrieve similar past failures and what worked
3. **Pattern recognition**: Identify which prompts produce better adherence
4. **Model selection**: Track which models have better adherence rates

## Explicitly Forbidden in C13

- No runtime prompt injection
- No route decision
- No KnowledgeHitSignal runtime field yet
- No parser weakening
- No automatic model selection
