---
name: github5-slavingia-minimalist-forecast
description: "Use for forecast_pregate work that needs minimalist validation, MVP scoping, manual-first risk reduction, and decision gates before building. This prompt-only SF challenger is adapted from slavingia/skills; do not use for business advice as runtime policy, external market research calls, runtime default changes, or public benchmark claims."
metadata: {"source_repo":"https://github.com/slavingia/skills","source_commit":"eb9f57fba03ddb0382ed3bfe6654d3d7df128c70","source_path":"skills/validate-idea/SKILL.md + skills/mvp/SKILL.md + skills/processize/SKILL.md","source_status":"generated_prompt_only_candidate","runtime_eligible":true,"ablation_eligible":true}
---

# GitHub Round5 Minimalist Forecast Candidate

## Load when
- Nexus is running an internal SF ablation for `forecast_pregate`.
- The task needs pre-build validation, MVP scope control, manual-first delivery, or risk triage.
- The expected output is a forecast gate decision, not product strategy prose.

## Do not load when
- The task is already execution-ready and does not need pre-build risk gating.
- The workflow asks for external customer research without a separate research/source gate.
- The result would be used to auto-approve runtime or public benchmark promotion.

## Operating contract
- Prefer manual-first, smallest-testable-scope decisions.
- Identify the assumption that can invalidate the plan fastest.
- Separate forecast confidence, evidence needed, and delivery readiness.
- Fail closed if validation evidence is missing.

## Required receipt fields
- `selected`
- `injected`
- `used`
- `evidence_present`
- `gate_passed`
- `outcome_contributed`

## Output shape
Return:

1. Core assumption.
2. Smallest validation test.
3. MVP boundary.
4. Kill/continue criteria.
5. Evidence required before execution.

