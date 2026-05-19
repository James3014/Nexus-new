---
name: research-citation-chain-verifier
description: Use when Nexus route capability is research, research_and_source_discipline, research_control_plane and the task needs research claim-to-source tracing, citation chain verification, and source-discipline receipts; return receipt/evidence/gate/outcome-backed guidance for SF or runtime review. Do not use for unrelated one-off writing or tasks without runtime evidence needs.
metadata: {"capability":"research_and_source_discipline","source_status":"candidate_only","runtime_eligible":false,"ablation_eligible":true}
---

# Research Citation Chain Verifier

## Load When

- A research answer includes factual claims that must be tied to stable source references.
- The task requires claim-to-source traceability, citation-chain status, or source validation receipts.
- A source-discipline ablation row needs an explicit citation-chain behavior candidate.

## Do Not Load When

- The task is general summarization without source verification requirements.
- The source set is unavailable and no receipt can be produced.
- Runtime policy is asking for a default skill. This asset is candidate-only until SF promotion evidence exists.

## Required Receipts

- `claim_to_source_refs`
- `citation_chain_status`
- `source_validation_status`
- `evidence_path`
- `receipt_path`

## Procedure

1. List the research claims that need support.
2. Map each claim to one or more source references.
3. Mark unsupported, circular, or stale source links as failed validation.
4. Return a citation-chain status that can be consumed by the SF catalog.

## Boundary

This skill is not runtime-eligible by itself. It may enter only the research SF candidate pool until a live ablation run proves outcome contribution without trust mismatch.
