---
name: github7-browserbase-ui-test-safe-ui-validator
description: Prompt-only UI validation challenger derived from Browserbase ui-test/safe-browser principles. Use for UI validator capability comparisons only; do not execute Browserbase CLI or external browser tools.
source_repo: https://github.com/browserbase/skills
source_commit: b2ae7283497efec71533d292b19b874dd9d0fc4e
source_skill: skills/ui-test + skills/safe-browser
runtime_mount_candidate: false
sf_challenger_only: true
---

# Browserbase UI Test Safe UI Validator

Use this skill only as a Nexus SF challenger for the `ui_validator` capability. It adapts Browserbase-style adversarial UI testing into a prompt-only, receipt-first checklist.

## Boundaries

- Do not run Browserbase CLI, npm packages, MCP tools, or remote browser automation.
- Do not change runtime defaults or route policy.
- Treat this skill as evidence-generation guidance inside an existing Nexus/Flash route.

## Method

1. Identify the user-facing workflow, target state, and observable acceptance criteria.
2. Probe the workflow like a critical tester: empty states, invalid input, slow/failed loading, navigation loops, auth or permission edges, and visual regressions.
3. Record failures as reproducible observations with expected behavior, actual behavior, and evidence reference.
4. Distinguish blocking failures from cosmetic or diagnostic observations.
5. Return a compact verdict with `selected`, `used`, `evidence_present`, `gate_passed`, and `outcome_contributed` fields when the runner asks for receipt material.
