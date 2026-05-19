# Nexus Optimization Artifact Index - 2026-05-20

## Scope
- Internal optimization evidence and gate artifacts only.
- Not a runtime apply approval.
- Not a public benchmark claim.

## Artifacts
- `nexus/contracts/retrieval_receipt.py`
- `nexus/contracts/claim_evidence_read_model.py`
- `nexus/contracts/context_assembly.py`
- `nexus/contracts/route_context_seam_freeze.py`
- `scripts/ops/build_claim_evidence_read_model.py`
- `scripts/ops/build_context_assembly_contract.py`
- `scripts/ops/build_route_context_seam_freeze.py`
- `scripts/ops/build_evidence_dataset_manifest.py`
- `scripts/ops/check_optimization_artifact_hygiene.py`
- `nexus/contracts/sf_replacement.py`

## Claim Boundary
- Retrieval receipts explain retrieval selection and scoring.
- Claim/evidence read models summarize gates without mutating runtime policy.
- Hygiene hooks validate artifacts and must not delete files.
- SF replacement gates may approve review candidates but do not unlock public benchmark claims.
