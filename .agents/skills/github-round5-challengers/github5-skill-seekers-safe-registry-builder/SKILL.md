---
name: github5-skill-seekers-safe-registry-builder
description: "Use for registry_skills_sync work that needs safe source-type detection, skill candidate extraction, registry metadata normalization, and candidate-only writeback planning. This prompt-only SF challenger is adapted from yusufkaraaslan/Skill_Seekers; do not use for package installation, automatic code execution, external downloads, runtime default changes, or public benchmark claims."
metadata: {"source_repo":"https://github.com/yusufkaraaslan/Skill_Seekers","source_commit":"ff0f832febc8db931e88d401a8d0896aac134159","source_path":"skills/skill-seekers/SKILL.md","source_status":"generated_prompt_only_candidate","runtime_eligible":true,"ablation_eligible":true}
---

# GitHub Round5 Skill Seekers Safe Registry Builder Candidate

## Load when
- Nexus is running an internal SF ablation for `registry_skills_sync`.
- The task needs to convert docs, repos, PDFs, or skill folders into candidate registry entries.
- The user wants source classification, manifest normalization, or candidate-pool update planning.

## Do not load when
- A workflow would execute untrusted repo code or install dependencies.
- The task asks to auto-promote external skills into runtime default.
- Source license, provenance, or prompt-only boundary is missing.

## Operating contract
- Stay prompt-only and candidate-only.
- Classify source type before extracting any skill metadata.
- Normalize `skill_id`, source URL, commit, source path, license status, safety status, and capability hints.
- Route untrusted, archive, vendor, or worktree-copy skills to quarantine/reference-only states.

## Required receipt fields
- `selected`
- `injected`
- `used`
- `evidence_present`
- `gate_passed`
- `outcome_contributed`

## Output shape
Return:

1. Source classification.
2. Candidate registry rows.
3. Safety and provenance blockers.
4. Capability hint mapping.
5. Candidate-only writeback plan.

