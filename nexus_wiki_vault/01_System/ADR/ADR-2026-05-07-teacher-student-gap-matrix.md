---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR-2026-05-07: Use GPT-5.5+Nexus As Teacher, Not Fallback

## Context

The optimization goal is to make weak models perform more like strong reasoning models while wearing Nexus. The goal is not to route production work away from weak models to `GPT-5.5+Nexus`.

## Decision

Treat `GPT-5.5+Nexus` as a teacher trace:

- compare `Flash+Nexus` against `GPT-5.5+Nexus`
- identify cost and strategy gaps per task bucket
- tune Flash Nexus profiles toward teacher behavior
- export successful teacher/student traces into learning and training loops

## Lesson

`GPT-5.5+Nexus` solved the current 3-task set with lower tokens per verified success than `GPT-5.5 direct`, while `Flash+Nexus` also reached full verification but at much higher wall and token cost. That means Nexus is valuable, but the weak-model profile needs teacher-guided tuning rather than a fallback-to-strong-model policy.
