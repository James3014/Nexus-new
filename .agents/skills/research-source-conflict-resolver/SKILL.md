---
name: research-source-conflict-resolver
description: Load when sources disagree and the answer must preserve conflict, confidence, and provenance instead of flattening uncertainty.
capability: research_and_source_discipline
source_status: candidate_only
runtime_eligible: false
ablation_eligible: true
---

# Research Source Conflict Resolver

## Load When

- Two or more credible sources disagree on a material fact.
- The expected output must preserve conflict, confidence, and provenance.
- A source-discipline ablation row needs an explicit source-conflict behavior candidate.

## Do Not Load When

- The task has a single authoritative source and no conflict to resolve.
- The answer can be accepted without source provenance.
- Runtime policy is asking for a default skill. This asset is candidate-only until SF promotion evidence exists.

## Required Receipts

- `conflicting_source_refs`
- `resolution_reason`
- `source_validation_status`
- `evidence_path`
- `receipt_path`

## Procedure

1. Identify the conflicting claims and their source references.
2. Classify the conflict as unresolved, resolved by stronger evidence, or out of scope.
3. Preserve uncertainty instead of forcing a false consensus.
4. Return the resolution reason and validation status for SF catalog evaluation.

## Boundary

This skill must fail closed when source disagreement is unresolved. It may not update runtime policy or become a default skill without receipt-backed SF promotion evidence.
