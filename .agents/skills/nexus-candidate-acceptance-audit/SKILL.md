---
name: nexus-candidate-acceptance-audit
description: Independently audit an exact Nexus Candidate and its contract, evidence, revisions and reviewer identity. Emit bounded acceptance guidance; not implementation, Owner approval, merge, or production certification.
---

# Nexus Candidate Acceptance Audit

Independently audit an exact Nexus Candidate and its contract, evidence, revisions and reviewer identity. Emit bounded acceptance guidance; not implementation, Owner approval, merge, or production certification.

## Role-specific requirements

Use `nexus.candidate_acceptance.v5` only when formal Candidate Acceptance is required for a GOVERNED task whose execution transport is not truthfully represented by Nexus MCP or DevSpace-specific lineage. v5 consumes `TRANSPORT_NEUTRAL_DIRECT_EVIDENCE`, but its mutation authority must come from a physical `TRACKED_TASK_CARD` already present in the authorized base; transport identity never grants authority. Eligible DIRECT_CANONICAL / DIRECT_DELEGATED work keeps the repository's direct verification and Owner merge gates and does not acquire a mandatory v5 acceptance step. Current Nexus MCP and DevSpace-specific acceptance may continue to use `nexus.candidate_acceptance.v4`; v4 is not redefined by v5. Preserve v3 and historical v4 replay semantics unchanged.

Keep producer/consumer and verification/acceptance proof separate. Expected provider/model configuration cannot substitute for observed attestation. Missing material proof remains blocked or insufficient.

## Workflow

1. Bind the current request, exact input/source identity and authorized role. Reuse settled context; ask only for information whose absence changes safety or the required result.
2. Read the complete shared `PROCEDURE.md`. For v4, also read `PROCEDURE_V4.md` and its mandatory schema/template references. For GOVERNED v5 transport-neutral execution, apply the v4 independent-acceptance and claim-discipline gates unchanged, then use the v5 successor contract documented in `references/acceptance-result-schema-v4.md`; the validator dispatches by the result schema.
3. Perform only the role-specific work permitted by the procedure and current host. Keep execution evidence, Core verification, certification, Candidate acceptance, Owner approval and integration distinct.
4. Validate the prescribed artifact/schema and applicable physical evidence. Report source, scope, observations, not-run checks, unresolved conflicts and one exact remaining gate. Do not claim a tool ran without its result.
## Procedure and conditional loading

Before any formal acceptance recommendation, read the complete applicable procedure and mandatory contract/schema references. Read-only triage may use only relevant sections.

For GOVERNED v5 transport-neutral work, read [v4 procedure](PROCEDURE_V4.md) for the unchanged acceptance/independence gates, then read the **v5 successor / compatibility** section of [the result-schema reference](references/acceptance-result-schema-v4.md). v5 requires a Git-tracked Task Card in the authorized base and independently published review provenance; neither executor metadata nor local review JSON can mint those authorities. The existing `scripts/validate_acceptance_result_v4.py` path is a schema-dispatch wrapper: v4 inputs execute the saved v4 validator unchanged, while v5 inputs enter the transport-neutral branch. This shared path exists because the current governed execution surface cannot create a new validator target file; it is not a semantic rewrite of v4. Historical/current v4 and v3 replay paths remain unchanged.

Before repository-bound execution, compilation or an authority/acceptance judgment, read [Nexus governance](references/nexus-governance.md). For snapshot/frontier claims, read [dated source observations](references/nexus-observed-state-20260908.md) and then rebind material live evidence. Do not load unrelated historical material.

## Host and source binding

Read [host compatibility](references/host-compatibility.md) when host, tool surface, dependencies, file locations or execution identity are material. Missing evidence stays unknown; missing capabilities do not authorize installing tools or bypassing gates.

[Source binding](references/source-binding.json) records the inherited bundle provenance. [v4 source binding](references/source-binding-v4.json) records current and historical v4 semantics, DevSpace producer ownership, Nexus Core protocol bindings, and the canonical editable collaboration source. The installed Skill is a derived runtime copy after repository integration; it is not an independent source authority. The skill Candidate revision is not a live admission, installation or deployment receipt.

## Output and stop boundary

For new GOVERNED transport-neutral execution that requires formal acceptance, produce and validate `nexus.candidate_acceptance.v5`. Keep v3 and every v4 replay branch physically testable and semantically unchanged. v5 evidence never grants Owner approval, merge, release, deployment, routing, Workforce, or production authority, and it does not make formal Candidate Acceptance mandatory for otherwise eligible DIRECT merges. Stop at the explicit task/role boundary, unresolved material conflict or missing required capability. Preserve independent reviewer/oracle requirements and no-self-approval rules.