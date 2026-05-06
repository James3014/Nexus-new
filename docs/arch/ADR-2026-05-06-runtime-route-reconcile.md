# ADR: Runtime Route Reconcile Before Flash Promotion

## Context

Flash 8x1 can pass while route quality still regresses. In P820, two repair tasks solved successfully, but `runtime_pruning.with_nexus` stayed at `0.25` because the planner selected `autoreason` and `judge_panel` even when the route already estimated `candidate_factory.status=SKIPPED`.

## Decision

Repair tasks with a skipped candidate factory must not select ranking layers from low-confidence or generic evidence wording alone. They should use `hyper` and `repair_loop` until runtime produces multiple candidates. If runtime later proves `autoreason` actually ran successfully, receipt generation reconciles the plan by adding the executed capability before building receipts.

## Lesson

Planner estimates and runtime facts are different evidence classes. Flash should not be the first detector for this gap; pre-Flash Nexus self-tests must include route payload checks and runtime receipt reconciliation checks for candidate-factory skipped repair tasks.

## Verification

- Route payload self-test: repair + `candidate_factory.status=SKIPPED` no longer selects `autoreason` or `judge_panel`.
- Receipt self-test: actual runtime `autoreason.status=SUCCESS` adds an `autoreason` receipt even when the initial route estimate skipped ranking layers.

## P846 Lesson: Receipt Public Safety Requires Claim Verification

During the Autoreason/Receipt runtime seam extraction, a unit test initially treated `autoreason.status=SUCCESS` plus a winner as enough to mark the receipt `public_claim_safe`. The receipt adapter correctly failed that expectation because Autoreason evidence is only public-safe when the surrounding claim is verified.

Decision: runtime receipt tests must include `capabilities.claim_verified=true` before expecting public-safe Autoreason output. Raw runtime success can prove invocation and evidence, but not public claim safety by itself.

Prevention: seam tests now keep the adapter's fail-closed behavior visible: route reconciliation may add an executed capability, but the receipt still requires evidence and gate state before it can support public benchmark claims.

## P875 Lesson: Semantic Judge Is Opt-In, Not Assumed

A selected `llm_judge_panel` capability is only a planning request until a configured provider returns a valid ranking. Nexus must not infer semantic judging from Autoreason's deterministic Borda fallback.

Decision: LLM judge providers are loaded only from explicit environment configuration. Gemini/Codex adapters use local command contracts, and missing commands produce no provider. If a provider errors or returns invalid output, Autoreason falls back to deterministic evidence quality and reports `semantic_judged=false`.

Prevention: tests cover opt-in fake provider wiring, command JSON round-trip, missing command exclusion, provider failure fallback, and runtime Autoreason semantic mode only when the provider is explicitly configured.

## P890 Lesson: Provider Failure Needs a Distinct Mode

A missing provider and a failed provider are not the same operational state. Without a distinct mode, reports could show deterministic judging while hiding that semantic judging had been requested but could not execute.

Decision: Autoreason now reports `judge_mode=heuristic_fallback` when judge providers were configured but produced no valid semantic votes. `semantic_judged` remains false.

Prevention: provider-unavailable tests assert `heuristic_fallback`, so Flash reports can distinguish true deterministic local mode from failed semantic provider execution.

## P1040 Lesson: Long Pre-Flash Runs Need Progress Classification

A Flash-style repair subset can run for more than a minute with no stdout while still making real progress on stderr JSONL task events. Treating that state as an opaque long wait makes the operator see only a final PASS/FAIL and hides whether Nexus improved or simply stalled.

Decision: the pre-Flash gate records duration, timeout budget, parsed progress events, last progress event, stdout-empty state, and a failure category for repair subset execution.

Prevention: tests cover success with stderr-only progress, timeout before any progress, timeout after task start, and non-zero failures with progress so the next Flash run can explain state instead of only reporting pass/fail.

## P1060 Lesson: Wear-Nexus Smoke Must Use Real Execution, Not Explain-Only

A direct `research:auto-flow --explain-route` invocation only prints the route and exits; it does not prove Nexus can modify code or produce artifact receipts. The first real CLI smoke then failed on a simple `normalize_flag(value)` repair because the local mutator only recognized `return text`.

Decision: wear-Nexus smoke must run without `--explain-route` before Flash. The deterministic local normalize repair now derives the actual argument name from the function signature instead of hard-coding `text`.

Prevention: local mutator tests now cover both `normalize_flag(text)` and `normalize_flag(value)` so Flash is not the first detector for simple local repair regressions.

## P1080 Lesson: Healing Artifacts Need Tamper Evidence Before Swarm Promotion

The safety telemetry diagnosis calls out unsigned `HealingArtifact` packets as a cross-node repair risk. A packet can be transport-only and still dangerous if another node cannot tell whether the artifact body changed in transit.

Decision: `HealingArtifact` now carries optional `signature` and `signature_key_id` fields. The core healing artifact module provides deterministic HMAC-SHA256 signing and verification over a canonical JSON body that excludes signature fields.

Prevention: tests cover valid signature verification and tamper rejection, so Flash is not the first place where cross-node healing evidence trust is exercised.
