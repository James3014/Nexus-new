# Issue #1362: Close remaining Agy quota-preflight, failure-taxonomy, and durable-timeline gaps for DevSpace #330

## Goal
Close the remaining Nexus Agy runtime-owned acceptance gaps found by the post-merge DevSpace #330 live canary:
1. Quota preflight: explicit admission/probe state distinction (`KNOWN_ELIGIBLE`, `UNVERIFIED_POLICY_ALLOWED`, `KNOWN_BLOCKED`), observable progress, bounded total operation deadline.
2. Model canonicalization: resolve model aliases (e.g. `claude-opus-4-6` to `claude-opus-4-6-thinking`) in attestation and dispatch without losing deterministic rejection.
3. Durable timeline: persist `reconciled_at` and ensure all required timeline fields (`provider_started_at`, `first_stream_activity_at`, `provider_stream_last_activity_at`, `first_effect_at`, `time_to_first_effect_ms`, `finished_at`, `reconciled_at`) are durably represented.
