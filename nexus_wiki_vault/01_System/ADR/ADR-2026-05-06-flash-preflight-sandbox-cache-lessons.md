---
type: ADR
status: accepted
tags: [nexus, ADR, evolution]
---

# ADR: Flash Preflight Sandbox Cache Lesson

Date: 2026-05-06

## Context

The first Gemini Flash benchmark preflight attempt failed inside the default
sandbox before benchmark validation started:

```text
failed to open file `/Users/jameschen/.cache/uv/sdists-v9/.git`: Operation not permitted
```

The same command passed when re-run with approved external execution.

## Decision

Gemini/Flash benchmark commands that use `uv run` and model CLIs must be treated
as external-runtime checks. A sandbox permission failure in `~/.cache/uv` is an
infrastructure preflight failure, not a Nexus route-quality result.

## Lesson

Benchmark evidence must separate harness/sandbox availability from model or
route behavior. If the command cannot reach the runner because of local cache
permissions, rerun with the approved benchmark execution path before drawing any
capability conclusion.
