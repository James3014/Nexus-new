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

The first real `flash_lite_route` run passed but only reduced wall time from 74.55s to 71.11s. Trace inspection showed the route was already light; the cost was a 55.39s Gemini baseline call despite a deterministic local `apply_events` repair existing. The next fix added a narrow hidden-contract local-first fast path for duplicate-event reducers. Re-run result: 14.68s, 0 model calls, hidden verifier PASS. This is a Nexus pre-model fast path, not a public same-model uplift claim, so it must be followed by a broader A/B before publication.

Teacher/student reports must split model-assisted success from deterministic Nexus tool success. A `local_hidden_contract_fast_path` run is valid evidence for Nexus cost avoidance and local-first routing, but it is not evidence that Flash itself improved. Gap reports therefore mark these rows as `local_deterministic_success`, set model-uplift eligibility to false, and recommend keeping the result separate from public weak-model uplift claims.

Long-loop closure requires an explicit Phase 0-9 plan artifact. The closure planner must block publication when the run has fewer than 12 tasks, no model-uplift-eligible rows, or only local/tool successes. This prevents short benchmark loops from becoming a story generator instead of a route optimizer.

Fail-fast cannot rely on process return code alone. A benchmark task can return zero while the `with_nexus` row is `run_eligible=false` with `infra_invalid_reason=nexus_delivery_invalid`. The weak-model long loop must inspect the generated with-Nexus JSONL row after every task and stop on semantic or eligibility failure before spending more model calls.

The weak-model uplift lane must require a model baseline call. Hidden-contract tasks can be solved by a local-first Nexus fast path, which is useful cost-avoidance evidence but blocks weak-model uplift claims. Long-loop commands therefore default to `--strict-llm-baseline`; local/tool success is only allowed in an explicit cost-avoidance lane.

Cost tuning needs per-task promotion rules, not one global knob. Lowering `--llm-candidate-cap` to 1 preserved verified delivery for the sampled high-cost rows, but the outcomes split three ways: `evidence-001` improved wall and token cost enough to promote, `hidden-002` and `trust-001` still need a Lite route because bare Flash already verifies them, and `repair-001` fell back to local/unreliable token accounting so it cannot be counted as weak-model uplift. Route-cost optimization must classify these cases before policy promotion.
