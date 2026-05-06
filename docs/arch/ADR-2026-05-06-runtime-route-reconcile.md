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
