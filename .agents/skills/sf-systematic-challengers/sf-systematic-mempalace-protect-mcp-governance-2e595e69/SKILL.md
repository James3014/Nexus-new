---
name: sf-systematic-mempalace-protect-mcp-governance-2e595e69
description: Agent governance skill for MCP tool calls — Cedar policy authoring, shadow-to-enforce rollout, and Ed25519 receipt verification.
metadata: {"source_status":"systematic_compiled_interface", "runtime_eligible":false, "ablation_eligible":true}
---

# protect-mcp-governance

## Load when
- Agent governance skill for MCP tool calls — Cedar policy authoring, shadow-to-enforce rollout, and Ed25519 receipt verification.

## Do not load when
- When you need general application security auditing (use `@security-auditor`)
- When you need to scan code for vulnerabilities (use `@security-audit`)
- When you need compliance framework guidance without agent-specific governance

## Required receipts
- selected
- injected
- used
- evidence_present
- gate_passed
- outcome_contributed

## Source
- /private/tmp/nexus-sf-round4/sickn33-antigravity-awesome-skills/plugins/antigravity-awesome-skills/skills/protect-mcp-governance/SKILL.md
