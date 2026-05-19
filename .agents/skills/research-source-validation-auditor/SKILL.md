---
name: research-source-validation-auditor
description: Use when Nexus route capability is lancedb and the task needs LanceDB-backed source validation, missing-source audit, and retrieval evidence discipline; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata: {"capability":"research_and_source_discipline","source_status":"candidate_only","runtime_eligible":false,"ablation_eligible":true}
---

# Research Source Validation Auditor

## Load When

- A research artifact must be audited for missing, circular, weak, or conflicting evidence.
- The task needs citation-chain, source-conflict, and source-validation behavior in one candidate.
- A source-discipline ablation row needs an independent verifier-style skill.

## Do Not Load When

- The task only needs drafting or style edits.
- The artifact has no claims or source references to audit.
- Runtime policy is asking for a default skill. This asset is candidate-only until SF promotion evidence exists.

## Required Receipts

- `audit_findings`
- `missing_source_refs`
- `source_validation_status`
- `evidence_path`
- `receipt_path`

## Procedure

1. Inspect the artifact for claim-to-source coverage.
2. Flag missing, circular, stale, or ambiguous source paths.
3. Separate source-validation failures from writing-quality issues.
4. Return audit findings with enough structure for SF replay and catalog verdicts.

## Boundary

This skill rejects missing or circular evidence paths. It is candidate-only and cannot be runtime-mounted as a default until live SF evidence proves contribution.
