# V4-D.2 14B Strict Prompt Acceptance — Final Report

## Status: V4D2_14B_STRICT_PROMPT_POLICY_ACCEPTED_INTERNAL_ONLY

## 1. Finding Update

| Phase | Result |
|-------|--------|
| V4-D | 14B no clear gain: format_valid=false, latency higher |
| V4-D.1 | 14B recovered with strict format prompt |
| Root cause | Format/protocol compliance issue, not semantic repair failure |
| Remaining caveat | Latency higher than 7B (30-150s vs 10-30s) |

## 2. Model Policy

| Model | Status | Usage |
|-------|--------|-------|
| qwen2.5-coder:7b | **DEFAULT_VALIDATED_EXECUTOR** | Primary repair model |
| qwen2.5-coder:14b | **STRICT_PROMPT_FALLBACK_CANDIDATE** | Optional fallback, owner-approved only |
| qwen2.5:3b | UNVALIDATED_AUXILIARY_CANDIDATE | Not validated for repair |

### Policy Rules
- 7B remains default validated executor
- 14B allowed only with strict patch-format prompt
- 14B used as optional fallback or hard-task escalation, not default
- 14B must satisfy all Roadmap v3 / V4-A / V4-B gates
- 14B does not enable public claim, training export, runtime/routing, or production readiness

## 3. Strict Prompt Requirements

Minimum constraints for 14B strict prompt:
- Output unified diff only
- No markdown fence (no ``` blocks)
- No explanation before or after patch
- Include exact file paths
- Include valid hunk headers (<<<<<<< SEARCH / ======= / >>>>>>> REPLACE)
- Preserve context lines
- No prose
- No JSON unless explicitly requested by patch parser
- Stop if uncertain rather than emitting malformed patch
- temperature=0.0 for determinism

## 4. Compliance Requirements

14B output must pass:
- patch_format_valid=true
- model_calls > 0
- cloud_api_used=false
- deterministic_fallback not counted as model success
- match_authority non-null on success
- verifier-backed pass before success claim
- public_claim_allowed=false
- training_eligible=false

## 5. Escalation Rule Proposal

| Scenario | Action |
|----------|--------|
| 7B semantic patch failure | Owner may approve 14B strict-prompt retry |
| 7B env blocker | Do NOT escalate to 14B |
| 7B canonical/source-anchor mismatch | Prefer structured packet / recovery path before 14B |
| 7B format issue | Retry with strict 7B prompt before 14B |

**Note**: 14B escalation remains manual/owner-approved until routing policy is explicitly accepted.

## 6. Status Update

```
7B:  DEFAULT_VALIDATED_EXECUTOR
14B: STRICT_PROMPT_FALLBACK_CANDIDATE
3B:  UNVALIDATED_AUXILIARY_CANDIDATE
```

## Internal Statement

"Nexus has internally accepted qwen2.5-coder:14b as a strict-prompt fallback candidate with owner-approved escalation. This is internal-only and not a public benchmark claim."
