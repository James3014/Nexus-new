# V4-D.3 14B Strict Prompt Guard Integration

## Status: V4D3_14B_STRICT_PROMPT_GUARD_READY

## Changes

Added 14B model policy checks to `runbook_compliance.py`:
- 14B requires strict_prompt_evidence or explicit owner approval
- 14B cannot be marked default executor
- 14B must not be treated as validated repair executor
- 3B must not be treated as validated repair executor

## Tests Added

| Test | Status |
|------|--------|
| valid 14B strict-prompt receipt | ✅ |
| 14B without strict prompt evidence | N/A (not in current artifacts) |
| 14B marked default executor | N/A |
| 3B treated as validated | ✅ tested |

## Policy

```
7B:  DEFAULT_VALIDATED_EXECUTOR
14B: STRICT_PROMPT_FALLBACK_CANDIDATE (owner-approved only)
3B:  UNVALIDATED_AUXILIARY_CANDIDATE
```

## Guard Rules

1. 14B must have `strict_prompt_evidence=true` or owner approval
2. 14B cannot be default executor
3. 14B result must satisfy normal repair gates
4. 14B cannot be used for env blockers
5. 14B cannot enable public claim or training export
