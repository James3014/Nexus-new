---
name: create-plan
description: Create a concise, execution-ready plan for a coding task. Use when the route capability is forecast_pregate, plan quality, risk forecast, or implementation pregate review.
metadata:
  capability_id: forecast_pregate
  source_url: https://github.com/ComposioHQ/awesome-codex-skills
  source_commit: 9c9da64cf1bbea611d43dd14a10788d55369b353
  source_skill_path: create-plan/SKILL.md
  license: Apache-2.0
  sf_materialized_from_external: true
  runtime_eligible: false
  ablation_eligible: true
  public_benchmark_allowed: false
---

# Create Plan

## Goal

Turn a task request into a single, actionable plan with clear scope, ordered work, validation, and risk handling.

## Load when

- The route capability is `forecast_pregate`.
- The task needs plan quality review, implementation sequencing, risk forecast, or pregate readiness.
- A user asks for a plan before coding, migration, refactor, benchmark, rollout, or verification work.

## Do not load when

- The user asks to execute immediately and the route already has a verified implementation plan.
- Runtime default mounting is requested without SF promotion review.
- Public benchmark or production policy update is requested.
- The task is pure code execution, data extraction, or final delivery verification rather than planning.

## Minimal workflow

1. Scan only the relevant local context quickly: README, obvious docs, architecture notes, and likely touched modules.
2. Ask follow-up questions only if blocked; otherwise state assumptions and proceed.
3. Produce a compact plan with:
   - scope in/out,
   - ordered action items,
   - validation commands or evidence,
   - edge cases and risk,
   - explicit stop conditions.
4. Keep the plan implementation-oriented and avoid speculative work.

## Evidence required

- Capability-only baseline row.
- Skill-arm row with selected/injected/used/evidence/outcome receipt.
- Negative-control row that BLOCKs or RETURNs.
- SF replacement record that proves the candidate beats the current pairing on the selected metric gate.
- Runtime promotion review before any default mount.

## Boundary

This is a repo-local SF candidate materialized from an Apache-2.0 external skill. It may be used for SF ablation and promotion review, but it must not be treated as a runtime default until a separate runtime policy gate passes.
