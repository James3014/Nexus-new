---
name: github3-openai-skill-creator-safe-registry-sync
description: 當使用者要求 Nexus 執行 registry_skills_sync or skill creation/update work that needs official skill structure, validation readiness, packaging boundaries, and trigger/overlap evaluation; return receipt/evidence/gate/outcome-backed guidance. Do not use to execute bundled scripts or install skills automatically.
metadata: {"source_repo":"https://github.com/openai/skills","source_path":"skills/.system/skill-creator/SKILL.md","source_status":"generated_safe_candidate_from_external_repo","runtime_eligible":false,"ablation_eligible":true,"target_capability":"registry_skills_sync","safety_boundary":"prompt_only_no_external_script_execution"}
---

# Github3 Openai Skill Creator Safe Registry Sync

Candidate-only safe adaptation for Nexus `registry_skills_sync` route-fit testing.

## Source Summary

- Repo: https://github.com/openai/skills
- Source path: skills/.system/skill-creator/SKILL.md
- Original description: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowledge, workflows, or tool integrations.

## Safety Boundary

- Do not execute upstream scripts, plugin commands, installers, scanners, MCP servers, or external tools.
- Do not mutate runtime default, permissions, global config, or skill registries.
- Use this skill only as prompt/context guidance inside ablation-only SF tests.

## Required Receipts

- selected
- injected_or_used
- evidence_present
- gate_passed
- outcome_contributed

## Adapted Workflow

> ---
> name: skill-creator
> description: Guide for creating effective skills. This skill should be used when users want to create a new skill (or update an existing skill) that extends Codex's capabilities with specialized knowl
> metadata:
>   short-description: Create or update a skill
> ---
> # Skill Creator
> This skill provides guidance for creating effective skills.
> ## About Skills
> Skills are modular, self-contained folders that extend Codex's capabilities by providing
> specialized knowledge, workflows, and tools. Think of them as "onboarding guides" for specific
> domains or tasks—they transform Codex from a general-purpose agent into a specialized agent
> equipped with procedural knowledge that no model can fully possess.
> ### What Skills Provide
> 1. Specialized workflows - Multi-step procedures for specific domains
> 2. Tool integrations - Instructions for working with specific file formats or APIs
> 3. Domain expertise - Company-specific knowledge, schemas, business logic
> 4. Bundled resources - Scripts, references, and assets for complex and repetitive tasks
> ## Core Principles
> ### Concise is Key
> The context window is a public good. Skills share the context window with everything else Codex needs: system prompt, conversation history, other Skills' metadata, and the actual user request.
> **Default assumption: Codex is already very smart.** Only add context Codex doesn't already have. Challenge each piece of information: "Does Codex really need this explanation?" and "Does this paragra
> Prefer concise examples over verbose explanations.
> ### Set Appropriate Degrees of Freedom
> Match the level of specificity to the task's fragility and variability:
> **High freedom (text-based instructions)**: Use when multiple approaches are valid, decisions depend on context, or heuristics guide the approach.
> **Medium freedom (pseudocode or scripts with parameters)**: Use when a preferred pattern exists, some variation is acceptable, or configuration affects behavior.
> **Low freedom (specific scripts, few parameters)**: Use when operations are fragile and error-prone, consistency is critical, or a specific sequence must be followed.
> Think of Codex as exploring a path: a narrow bridge with cliffs needs specific guardrails (low freedom), while an open field allows many routes (high freedom).
> ### Anatomy of a Skill
> Every skill consists of a required SKILL.md file and optional bundled resources:
> ```
> skill-name/
> ├── SKILL.md (required)
> │   ├── YAML frontmatter metadata (required)
> │   │   ├── name: (required)
> │   │   └── description: (required)
> │   └── Markdown instructions (required)
> ├── agents/ (recommended)
> │   └── openai.yaml - UI metadata for skill lists and chips
> └── Bundled Resources (optional)
>     ├── scripts/          - Executable code (Python/Bash/etc.)
>     ├── references/       - Documentation intended to be loaded into context as needed
>     └── assets/           - Files used in output (templates, icons, fonts, etc.)
> ```
> #### SKILL.md (required)
> Every SKILL.md consists of:
> - **Frontmatter** (YAML): Contains `name` and `description` fields. These are the only fields that Codex reads to determine when the skill gets used, thus it is very important to be clear and comprehe
> - **Body** (Markdown): Instructions and guidance for using the skill. Only loaded AFTER the skill triggers (if at all).
> #### Agents metadata (recommended)
> - UI-facing metadata for skill lists and chips
> - Read references/openai_yaml.md before generating values and follow its descriptions and constraints
> - Create: human-facing `display_name`, `short_description`, and `default_prompt` by reading the skill
> - Generate deterministically by passing the values as `--interface key=value` to `scripts/generate_openai_yaml.py` or `scripts/init_skill.py`
> - On updates: validate `agents/openai.yaml` still matches SKILL.md; regenerate if stale

## Output Contract

Return `scope`, `checks`, `evidence_plan`, `fail_closed_boundaries`, and `recommended_catalog_verdict`.

