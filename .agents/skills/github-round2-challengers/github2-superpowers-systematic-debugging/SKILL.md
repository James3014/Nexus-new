---
name: github2-superpowers-systematic-debugging
description: 當使用者要求 Nexus 執行 codeintel, xray, repair_loop, or regression_guard 工作且需要先追出 root cause、重現條件、資料流斷點與證據鏈，再提出修復方案時使用；不要用於單純寫作、研究引用、runtime default promotion，或任何未經 receipt 驗證的自動掛載。
metadata: {"source_repo":"https://github.com/obra/superpowers","source_commit":"f2cbfbefebbfef77321e4c9abc9e949826bea9d7","source_skill":"skills/systematic-debugging/SKILL.md","source_status":"external_challenger","runtime_eligible":false,"ablation_eligible":true}
---

# GitHub Round2 Superpowers Systematic Debugging

Candidate-only adaptation of `obra/superpowers/skills/systematic-debugging`.

## Load when

- A Nexus route needs code inspection, xray, regression triage, or repair-loop diagnosis.
- A failure needs root-cause evidence before proposing a fix.
- The task needs boundary tracing across planner, runner, receipt, verifier, catalog, or policy layers.

## Do not load when

- The task only needs public benchmark claims or runtime default promotion.
- The workflow has no way to produce receipt/evidence/gate/outcome records.
- A quick patch is being requested without reproducing or isolating the cause.

## Required receipts

- observed_failure
- reproduction_or_probe
- boundary_trace
- candidate_root_cause
- verification_command
- outcome_contribution

## Operating contract

1. Identify the failing row, command, artifact, or route boundary.
2. Reproduce or isolate the failure with the smallest safe probe.
3. Trace data flow backward until the first bad assumption or missing artifact.
4. Propose the smallest fix that changes the root cause, not the symptom.
5. Require fresh verification before marking the row or route as recovered.

## SF boundary

This skill is an external challenger. It may participate in ablation-only Flash+Nexus comparison, but it must not update runtime default policy without a separate promotion/apply gate.
