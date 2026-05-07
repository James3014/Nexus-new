# ADR-2026-05-07 Teacher Student Sweep Plan

## Context

Flash+Nexus can verify the same 3-task set as GPT-5.5+Nexus, but the first teacher/student matrix showed Flash taking roughly 1.74x-2.96x wall time and 2.18x-2.37x tokens versus the teacher.

The goal is not to route hard work to GPT-5.5. The goal is to use GPT-5.5+Nexus as a teacher trace so weak models wearing Nexus can approach the teacher's verified runtime profile.

## Decision

Add `scripts/bench/teacher_student_sweep_plan.py`.

The tool converts teacher/student gap recommendations into profile-specific Flash+Nexus benchmark commands:

- `flash_compact_context` for token-heavy but verified tasks
- `flash_lite_route` for verified tasks with >=2x wall overhead
- `flash_teacher_repair_copy` for tasks where Nexus is required but Flash's repair runtime is too heavy

Every generated profile carries promotion gates:

- verified delivery must not drop
- trust mismatch must stay zero
- wall ratio to teacher must improve by at least 15%
- token ratio to teacher must improve by at least 10%
- stop on the first failed task and inspect that trace

## Lesson

Benchmark optimization must not become repeated short runs with vague conclusions. The sweep plan turns each teacher/student gap into an explicit profile, command, and promotion gate before another model call is spent.

The first preflight attempt failed because a cost-saving profile lowered `--llm-candidate-cap` below 3 while still enabling DDTree executor evidence. That mixes cost experiments with public-readiness claims. The corrected sweep keeps the candidate floor at 3, uses `--nexus-only` targeted treatment replays to save duplicate baseline cost, and treats the run as a non-public profile optimization until a full same-model A/B is rerun.
