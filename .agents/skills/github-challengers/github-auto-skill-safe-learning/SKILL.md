---
name: github-auto-skill-safe-learning
description: 當使用者要求 Nexus 執行 learning_closure, metabolism_resume, or registry_skills_sync work that needs safe cross-skill learning, experience writeback planning, or skill registry maintenance without modifying global IDE rules; return receipt/evidence/gate/outcome-backed guidance for SF review. Do not use for automatic global rule edits, forced always-on behavior, or memory writes without explicit approval.
metadata: {"source_repo":"https://github.com/Toolsai/auto-skill","source_commit":"636a2696f686e382877e941280723c9b5327a85c","source_status":"generated_candidate","runtime_eligible":false,"ablation_eligible":true}
---

# GitHub Auto Skill Safe Learning

Candidate-only adaptation of Toolsai/auto-skill principles.

## Load when
- Nexus needs a safe learning-closure or registry-sync skill candidate.
- The task asks for experience writeback planning, knowledge indexing, or skill maintenance.

## Do not load when
- A workflow tries to edit global IDE rules automatically.
- A skill declares itself mandatory for every task.
- Memory writes lack explicit user approval.

## Required receipts
- source_screen
- explicit_user_approval_for_writeback
- changed_index_paths
- rollback_plan

## Boundary
This is a generated candidate. It is not the original auto-skill and must not inherit its forced self-install or global-rule mutation behavior.

