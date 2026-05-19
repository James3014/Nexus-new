---
name: github4-sickn33-antigravity-awesome-skills-wiki-qa
description: Answer repository questions grounded entirely in source code evidence. Use when user asks a question about the codebase, user wants to understand a specific file, function, or component, or user asks \"how does X work\" or \"where is Y defined\". Use only as Nexus SF prompt-only ablation candidate with runtime receipt evidence; do not execute upstream tools, install dependencies, call subagents, or mutate global settings.
metadata: {"source_repo":"https://github.com/sickn33/antigravity-awesome-skills","source_commit":"9e5d4ddefa24be7b50cc83f56a2450401cdf3317","source_path":"skills/wiki-qa/SKILL.md","source_status":"external_round4_prompt_only_runtime_reviewed","runtime_eligible":true,"ablation_eligible":true}
---

# github4-sickn33-antigravity-awesome-skills-wiki-qa

Prompt-only Nexus SF candidate adapted from `SKILL.md`.

## Load when
Answer repository questions grounded entirely in source code evidence. Use when user asks a question about the codebase, user wants to understand a specific file, function, or component, or user asks \"how does X work\" or \"where is Y defined\".

## Runtime boundary
- Use only the written workflow principles below.
- Do not execute upstream scripts, install packages, call external services, invoke subagents, or mutate global IDE/agent settings.
- Must produce selected/injected/used/evidence/gate/outcome-backed receipt evidence.

## Safe workflow principles
# Wiki Q&A

Answer repository questions grounded entirely in source code evidence.

## When to Use
- User asks a question about the codebase
- User wants to understand a specific file, function, or component
- User asks "how does X work" or "where is Y defined"

## Procedure

1. Detect the language of the question; respond in the same language
2. Search the codebase for relevant files
3. Read those files to gather evidence
4. Synthesize an answer with inline citations

## Response Format

- Use `##` headings, code blocks with language tags, tables, bullet lists
- Cite sources inline: `(src/path/file.ts:42)`
- Include a "Key Files" table mapping files to their roles
- If information is insufficient, say so and suggest files to examine

## Rules

- ONLY use information from actual source files
- NEVER invent, guess, or use external knowledge
- Think step by step before answering

### When to Use
This skill is applicable to execute the workflow or actions described in the overview.

## Limitations
- Use this skill only when the task clearly matches the scope described above.
- Do not treat the output as a substitute for environment-specific validation, testing, or expert review.
- Stop and ask for clarification if required inputs, permissions, safety boundaries, or success criteria are missing.
