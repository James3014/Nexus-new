---
name: sf-systematic-memory-project-skill-audit-cc8b7621
description: Audit a project and recommend the highest-value skills to add or update.
metadata: {"source_status":"systematic_compiled_interface", "runtime_eligible":false, "ablation_eligible":true}
---

# project-skill-audit

## Load when
- When the user asks what skills a project needs or which existing skills should be updated.
- When recommendations should be grounded in project history, memory files, and local conventions.

## Do not load when
- runtime default promotion is requested without receipt review

## Required receipts
- selected
- injected
- used
- evidence_present
- gate_passed
- outcome_contributed

## Source
- /private/tmp/nexus-sf-round4/sickn33-antigravity-awesome-skills/plugins/antigravity-awesome-skills/skills/project-skill-audit/SKILL.md
