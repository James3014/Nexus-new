---
name: github8-skilless-deep-research-learn-ask
description: Prompt-only learn/ask challenger derived from skilless.ai research. Use for scoped question answering, multi-source synthesis, and explicit uncertainty handling; do not run search.py, yt-dlp, ffmpeg, or external scripts.
source_repo: https://github.com/BrikerMan/skilless.ai
source_commit: 5fe27b67631a76e27b61eb542b9e909cf4ca6e73
source_skill: src/skilless.ai-research/SKILL.md
runtime_mount_candidate: false
sf_challenger_only: true
---

# Skilless Deep Research Learn Ask

Use only as a Nexus SF challenger for `learn_ask`. Adapt skilless research depth and uncertainty handling into prompt-only Nexus answer discipline.

## Boundaries

- Do not run web.py, search.py, youtube.py, yt-dlp, ffmpeg, or downloader tools.
- Do not ask for clarification during automated SF probes; infer the smallest safe scope and mark assumptions.

## Method

1. Classify the question as quick lookup, focused research, or deep investigation.
2. State scope, assumptions, source classes, and confidence requirement.
3. For synthesis, separate facts, uncertainty, conflicts, and missing evidence.
4. Cite evidence refs already available to Nexus; do not invent sources.
5. Emit answer verdict with evidence presence, gate result, and outcome contribution.
