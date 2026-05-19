---
name: github9-teaching-web-visual-ui-validator
description: Prompt-only UI validator challenger derived from teaching-site web-visual-verification. Use for rendered UI behavior, viewport, console-error, and visual regression checks; do not run Playwright or create screenshots unless the Nexus runner already provides them.
source_repo: https://github.com/kevintsai1202/teaching-site-skills
source_commit: 8ef63880775765d21513a480d7aa662b30e3a0ac
source_skill: web-visual-verification/SKILL.md
runtime_mount_candidate: false
sf_challenger_only: true
---

# Teaching Web Visual UI Validator

Use only as a Nexus SF challenger for `ui_validator`. Convert the web visual verification discipline into receipt-friendly UI validation guidance.

## Boundaries

- Do not launch Playwright, browser tools, or screenshot capture unless the runner already supplies them.
- Do not mutate app state or write runtime defaults.

## Method

1. Separate verify, capture, diagnose, and probe roles.
2. Check runtime UI behavior: responsive layout, overflow, interaction state, console-error risk, and persistence.
3. Prefer explicit assertion-style findings over vague visual comments.
4. Record evidence refs and classify blocking vs diagnostic issues.
5. Emit selected, used, evidence_present, gate_passed, and outcome_contributed when asked for receipt material.
