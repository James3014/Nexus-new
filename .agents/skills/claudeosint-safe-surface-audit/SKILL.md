---
name: claudeosint-safe-surface-audit
description: Load when a governance route must audit externally sourced or OSINT-like evidence for safe-surface, disclosure, and unsupported-claim risk.
capability: governance_and_trust
source_status: runtime_review_candidate
runtime_eligible: false
ablation_eligible: true
sf_materialized_from: governance_mutant_alternate
---

# Safe Surface Audit

## Load When

- A task uses external or OSINT-style evidence that needs disclosure and safety review.
- A claim may expose secrets, unsafe provenance, unsupported assertions, or trust-boundary mismatches.
- SF governance ablation needs a candidate focused on safe external evidence handling.

## Do Not Load When

- The task has no external evidence or disclosure boundary.
- The task is asking for unconstrained browsing, scraping, or private-data inference.
- Runtime default mounting is requested without SF promotion review.

## Required Receipts

- `source_surface_refs`
- `safety_boundary_verdict`
- `redaction_or_disclosure_notes`
- `receipt_path`
- `evidence_path`

## Procedure

1. Identify every external source, claim, and disclosure-sensitive surface.
2. Check whether the source is public, reproducible, and safe to cite.
3. Mark unsafe, private, or unsupported surfaces as `BLOCK_OR_RETURN`.
4. Emit a safety verdict with exact source and claim references.

## Boundary

This repo-local asset was materialized from SF governance mutant evidence. It is eligible for ablation and runtime review, but not runtime default mounting until a separate promotion gate passes.
