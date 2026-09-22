# Nexus Candidate Acceptance Audit v4

Use the shared v3 human-report sections in `acceptance-template.md`, with these v4 additions.

## Evidence-union binding

- Executor evidence kind: `NEXUS_MCP_RECEIPT | DEVSPACE_DIRECT_EVIDENCE`
- Executor evidence SHA-256:
- Verification evidence kind: `MCP_VERIFIED_RECEIPT | CORE_GENERIC_VERIFICATION_RESPONSE`
- Verification evidence SHA-256:
- Physical executor schema / identity:
- Physical verification schema / identity:

## Branch-specific binding

For `NEXUS_MCP_RECEIPT`:

- v3 compatibility validation report:
- Task Card / Owner-inline contract binding:
- packet / manifest / receipt lineage:
- runtime Workforce Admission, if applicable:

For `DEVSPACE_DIRECT_EVIDENCE`:

- Owner-inline AcceptanceContract hash:
- DevSpace task / attempt / agent / workspace:
- source commit/tree:
- Candidate commit/tree/diff:
- Core session / binding hash:
- direct producer claim ceiling:- synthetic Task Card / campaign / MCP lineage present: `false`
- Core generic response status:
- Core AcceptanceContract hash match:
- Core change-manifest hash match:
- Direct manifest ordering profile: `UNICODE_CODEPOINT_LEXICAL_V1` for current v4; historical `2026-09-15-v4-tgb` uses frozen legacy validator only
- Acceptance validator source revision / package binding:
- separate Core certification present, if any:

## Authority statement

- Candidate Acceptance recommendation only: `true`
- Core verification treated as certification: `false`
- Executor evidence treated as acceptance: `false`
- Candidate approved: `false`
- Integrated / merged / released: `false`
- Owner action still required: `true`

## Compatibility statement

- v3 historical artifact semantics preserved:
- v4 branch selected only by explicit discriminator:
- no historical receipt laundering:
- no third executor-evidence branch inferred:

Then continue with the shared template's evidence axes, exact-base differential, independent verification/oracle provenance, Candidate verdict, approval readiness, next gate and prohibited actions.