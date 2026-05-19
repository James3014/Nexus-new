---
name: acceptance-evidence-failclosed
description: Use when Nexus route capability is artifact_gate, governance_and_trust, ultra_review and the task needs rejecting unsupported acceptance, delivery, claim, artifact, and governance evidence; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata: {"capability":"governance_and_trust","source_status":"runtime_review_candidate","runtime_eligible":false,"ablation_eligible":true,"sf_materialized_from":"governance_mutant_alternate"}
---

# Acceptance Evidence Fail-Closed

## Load When

- A task asks whether delivery or acceptance evidence is complete enough to pass a gate.
- A governance mutant is missing evidence, has a false PASS, or attempts to use delivery success without receipt support.
- SF governance ablation needs a fail-closed evidence-audit candidate.

## Do Not Load When

- The task is pure implementation with no claim, acceptance, or evidence boundary.
- Runtime default mounting is requested without SF promotion review.
- The available artifacts cannot produce an evidence path and receipt path.

## Required Receipts

- `acceptance_evidence_refs`
- `missing_evidence_reasons`
- `gate_verdict`
- `receipt_path`
- `evidence_path`

## Procedure

1. Enumerate the acceptance claim and every artifact cited as support.
2. Reject claims that lack tests, schema/replay output, evidence bundle, or receipt references.
3. Mark false PASS, missing receipt, and ambiguous evidence as `BLOCK_OR_RETURN`.
4. Emit a concise gate verdict with explicit missing evidence reasons.

## Boundary

This repo-local asset was materialized from SF governance mutant evidence. It is eligible for ablation and runtime review, but not runtime default mounting until a separate promotion gate passes.
