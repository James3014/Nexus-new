---
name: sf-systematic-xray-varlock-47ccfd5a
description: Secure-by-default environment variable management for Claude Code sessions.
metadata: {"source_status":"systematic_compiled_interface", "runtime_eligible":false, "ablation_eligible":true}
---

# varlock

## Load when
- You need to work with environment variables or secrets in a Claude Code session without exposing their values.
- The task involves validating, loading, or auditing secrets while keeping them out of logs, diffs, and assistant context.
- You want a secure-by-default workflow built around Varlock instead of direct `.env` inspection.

## Do not load when
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.

## Required receipts
- selected
- injected
- used
- evidence_present
- gate_passed
- outcome_contributed

## Source
- /private/tmp/nexus-sf-round4/sickn33-antigravity-awesome-skills/plugins/antigravity-awesome-skills-claude/skills/varlock/SKILL.md
