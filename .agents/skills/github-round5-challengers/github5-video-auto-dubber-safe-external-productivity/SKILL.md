---
name: github5-video-auto-dubber-safe-external-productivity
description: "Use for external_productivity work that needs privacy-safe media workflow planning, subtitle/voiceover QA, preview/final export checklists, and artifact handoff without executing media tools. This prompt-only SF challenger is adapted from p8552015-lab/video-auto-dubber; do not use for direct video processing, shell execution, package installation, runtime default changes, or public benchmark claims."
metadata: {"source_repo":"https://github.com/p8552015-lab/video-auto-dubber","source_commit":"4428ad5dda7cf9d131b9b9121cdef2da82b50b7c","source_path":"SKILL.md","source_status":"generated_prompt_only_candidate","runtime_eligible":true,"ablation_eligible":true}
---

# GitHub Round5 Video Auto Dubber Safe External Productivity Candidate

## Load when
- Nexus is running an internal SF ablation for `external_productivity`.
- The task needs media workflow planning, privacy checks, subtitle/voiceover QA, or export handoff.
- The expected output is a safe productivity plan with artifact gates, not actual media processing.

## Do not load when
- The task would execute ffmpeg, media tools, shell commands, or package installation.
- The workflow requires access to private media without explicit user approval.
- Runtime policy or public benchmark claims would be changed from this internal test.

## Operating contract
- Stay prompt-only.
- Identify privacy-sensitive media inputs and redaction requirements.
- Separate preview checks, final export checks, and delivery artifacts.
- Require evidence paths for subtitles, voiceover, and final media before completion.

## Required receipt fields
- `selected`
- `injected`
- `used`
- `evidence_present`
- `gate_passed`
- `outcome_contributed`

## Output shape
Return:

1. Media workflow stages.
2. Privacy and consent checks.
3. Subtitle/voiceover QA gates.
4. Preview/final export criteria.
5. Evidence bundle checklist.

