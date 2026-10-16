# V5-C Patch Protocol Adapter and Strict Diff Contract

## Status: V5C_PATCH_PROTOCOL_ADAPTER_READY

## Summary

Formal patch protocol layer replacing ad-hoc prompt text with reusable strict diff contract.

## Protocol Modes

| Mode | Description |
|------|-------------|
| strict_unified_diff | Standard unified diff format |
| strict_search_replace | SEARCH/REPLACE blocks (current format) |
| format_repair_prompt | Template for retry on format failure |
| parser_error_classification | Classify format vs semantic failure |

## Protocol Fields

```python
class PatchProtocol:
    protocol_name: str
    model_policy: str  # "7b_default" | "14b_strict_fallback"
    allowed_models: list[str]
    strict_prompt_text: str
    forbidden_output_patterns: list[str]
    parser_error_type: str
    retry_allowed: bool
    max_format_retries: int
    fallback_policy: str
```

## Strict Prompt Constraints

1. Output patch only
2. No markdown fence
3. No prose before/after
4. No explanation
5. No JSON unless parser expects JSON
6. Exact file path required
7. Valid hunk headers required
8. Stop if uncertain

## Validation Rules

| Rule | Action |
|------|--------|
| Markdown fence detected | FORMAT_ERROR |
| Prose before/after patch | FORMAT_ERROR |
| Missing file path | FORMAT_ERROR |
| Invalid hunk header | FORMAT_ERROR |
| Empty patch | FORMAT_ERROR |
| Multiple incompatible formats | FORMAT_ERROR |

## 14B Requirement

14B use must record `strict_prompt_evidence=true`. Without this, compliance checker fails.

## Tests

| Test | Status |
|------|--------|
| valid 7B strict diff | ✅ |
| valid 14B strict diff with strict evidence | ✅ |
| 14B without strict prompt evidence fails | ✅ |
| markdown fence fails | ✅ |
| prose contamination fails | ✅ |
| invalid hunk fails | ✅ |
| empty patch fails | ✅ |
| format-only failure classification | ✅ |
| format retry not counted as model success | ✅ |

## Files

- `nexus/services/local_heal/patch_protocol.py` — protocol adapter
- `tests/unit/local_heal/test_patch_protocol.py` — 9 tests
