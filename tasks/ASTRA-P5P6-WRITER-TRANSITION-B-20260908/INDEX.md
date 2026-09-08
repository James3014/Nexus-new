# Campaign Index: ASTRA-P5P6-WRITER-TRANSITION-B-20260908

artifact_authority: current
owner: James Chen
status: active, governed and sequential
AUTO_CHAIN: false

## Objective

Implement the source-owned writer admission, lease, hold, drain, and typed quiescence receipt collector consumed by Card A and Card F, preserving UNKNOWN for missing or unregistered writers and never claiming ACTIVE. Owner approved A-F source work. Card A independently accepted HEAD d4b58d6ade0b7ed2d078e4b2166695a5b5d7312e tree af7261f07d266be584b55dda9b829ab04a10a77b. Follow approved SOURCE_SPEC_ADDENDUM.md SHA bcedf2026499698c40ccf66c7973eaa02a1c570dbb808a2f2618eeb9f8fee2c6 and bounded Card B test matrix at /private/tmp/astra-writer-transition-dependency-review-20260908/CARD_B_TEST_MATRIX.md. Exactly six source files; actual source-owned root/role/process/thread/generation registry, admission leases, durable logical hold epoch, no mutex held while waiting, real Gateway service thread/assist-process and pending-action observations. Missing/orphan/unregistered writers remain UNKNOWN. Exact source-owned collector evidence integrates with accepted Card A private loader seam through Gateway, with no caller override or cross-instance rebind. Source receipt and snapshot bytes verified; no fabricated receipts. Collector produces evidence only, never ACTIVE. Adapter coverage C-E and cohort F remain separate; do not claim legacy writers drained from fixtures. Positive real fixture tests, unknown/forgery/restart/crash and concurrency verifiers required. No live hold/deployment/cutover, actual grant/authority publication, API-key/SDK/Agy/Gemini/provider/native/network, main/push/merge, cleanup or production claims. AUTO_CHAIN=false. Worker may exact scoped candidate commit after independent review; cannot approve/integrate.

## Ordered cards

| Order | Task ID | Card | Status | Dependency |
|---:|---|---|---|---|
| 0 | `astra-p5p6-writer-transition-b-20260908` | `00-astra-p5p6-writer-transition-b-20260908.md` | ACTIVE | Owner confirmation |
