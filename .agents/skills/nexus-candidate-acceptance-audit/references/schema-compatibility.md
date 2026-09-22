# Artifact compatibility — package-side contract

Current acceptance output for new work: `nexus.candidate_acceptance.v4`.

Historical compatibility remains: `nexus.candidate_acceptance.v3`. Its schema, procedure and `scripts/validate_acceptance_result.py` validator remain preserved and must continue to validate historical v3 fixtures without reinterpretation.

Current upstream MCP executor lineage remains `nexus.compiled_model_task_packet.v3`, `nexus.chatgpt_mcp_execution.v4`, and `nexus.mcp_execution_receipt.v2`; legacy manifest v3 / receipt v1 stay compatibility branches only.

v4 adds an executor evidence union (`NEXUS_MCP_RECEIPT | DEVSPACE_DIRECT_EVIDENCE`) and a verification evidence union (`MCP_VERIFIED_RECEIPT | CORE_GENERIC_VERIFICATION_RESPONSE`), each with an exact SHA-256 binding to physical bytes.

`DEVSPACE_DIRECT_EVIDENCE` consumes `devspace.direct_candidate_execution.v1` under `OWNER_INLINE`; it must not synthesize Task Card, campaign, compiled-packet, MCP-manifest or MCP-receipt lineage. Its Core verification companion is `nexus.core.generic-verification-response.v1-experimental` with factual `verification.status=VERIFIED` and exact contract/change-manifest binding.

The v4 discriminator selects a validator branch only. It does not create execution, verification, certification, acceptance, Owner approval, merge, release or public-claim authority. Core verification remains distinct from certification; Candidate Acceptance remains a recommendation gate.

Do not rename old fields/versions, insert guessed fields, fabricate missing attestation or executor lineage, or bypass a failed v3/v4 validator.
New direct-evidence v4 manifest paths use canonical Unicode code-point lexical ordering matching Nexus Core. Historical `2026-09-15-v4-tgb` direct-evidence replay remains available only through the frozen legacy v4 validator/schema snapshot; do not silently reinterpret those bytes under current ordering semantics. Missing current `devspace.direct_candidate_execution.v1` evidence remains `ACCEPTANCE_BLOCKED` and is never synthesized by the acceptance consumer.
