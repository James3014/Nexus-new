---
name: github7-midudev-tdd-repair-loop
description: Prompt-only repair loop challenger derived from midudev autoskills test-driven-development. Use for repair_loop comparisons only.
source_repo: https://github.com/midudev/autoskills
source_commit: c32e201b9877d647ec5725230e45847ca348f695
source_skill: packages/autoskills/skills-registry/*/test-driven-development
runtime_mount_candidate: false
sf_challenger_only: true
---

# Midudev TDD Repair Loop

Use this skill only as a Nexus SF challenger for `repair_loop`. It applies strict test-first repair discipline without external execution hooks.

## Boundaries

- Do not add broad refactors before a failing behavior is isolated.
- Do not claim success without a passing verification command or an explicit runner receipt.
- Do not write runtime default policy.

## Method

1. Reproduce or restate the failing behavior as a focused test condition.
2. Add or identify the smallest test that would fail before the repair.
3. Make the minimal code change that satisfies the test.
4. Run the focused verification, then any adjacent regression needed by the touched surface.
5. Keep unrelated cleanup out of the repair path.
6. Report red/green evidence, changed behavior, and remaining risk.
