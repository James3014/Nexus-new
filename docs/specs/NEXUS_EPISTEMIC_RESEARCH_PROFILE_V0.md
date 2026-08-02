# Nexus Epistemic Research Profile V0 Specification

## A. Purpose & Separation of Concerns

### Epistemic Research Profile Answers:
- **What is the source?** (`SourceArtifactRef`, `SourceLineageRef`)
- **What did the source actually say?** (`EvidenceExtractionRef`)
- **How was this content evaluated?** (`EvidenceAssessmentRef`)
- **Does it support or contradict which range of Claim?** (`EpistemicDirection`, `EpistemicScopeAlignment`)
- **What things CANNOT be established?** (`cannot_establish_present`, `conflict_unresolved`)

### Nexus Governance Kernel Answers:
- **Who has authority to execute?** (`nexus.lifecycle`, `nexus.task_card`)
- **Who can produce a Candidate?** (`nexus.acceptance`)
- **Who can verify/accept?** (`nexus.acceptance`, `owner_or_formal_integrator`)
- **Which Receipt is valid?** (`nexus.receipt`)
- **Which claim can be public?** (`ClaimBoundary`)
- **Which state can be integrated?** (`nexus.contracts.claim_evidence_read_model`)

---

## B. Architecture

```text
Nexus Governance Kernel
│
├── Lifecycle Identity
├── Task Authority
├── Receipt Core
├── ClaimBoundary
├── ClaimEvidenceReadModel
├── Replay Engine
├── Block Semantics
└── Candidate / Acceptance Lifecycle
     │
     └── Epistemic Research Profile (Foundation)
          ├── Position Commitment Ref
          ├── Masked Brief Ref
          ├── EpistemicArtifactRef
          ├── Extraction Ref
          ├── Assessment Ref
          ├── Cannot-establish Presence
          └── EpistemicVerificationResult / EpistemicReceiptExtension
```

---

## C. Current Capability Matrix

| Capability / Module | Status | Authority / Location |
| --- | --- | --- |
| Governance Kernel Core | `VERIFIED_CURRENT_CODE` | `nexus.contracts`, `nexus.evidence`, `nexus.replay` |
| Identity & Task Card Authority | `VERIFIED_CURRENT_CODE` | `nexus.lifecycle` |
| Epistemic Profile Foundation Contracts | `PROFILE_FOUNDATION` | `nexus.research.epistemic_profile` |
| Epistemic Authority Boundary | `PROFILE_FOUNDATION` | `nexus.research.epistemic_profile.authority` |
| ClaimEvidenceReadModel Adapter | `PROFILE_FOUNDATION` | `nexus.research.epistemic_profile.adapter` |
| Research Ledger Gate A Lab Code | `EXPERIMENTAL_REFERENCE` | `research-ledger/` (nested lab repo) |
| Live Pipeline Wiring | `NOT_WIRED` | N/A (out of scope for foundation) |
| Production Release / Public Claim | `NOT_ACCEPTED` | N/A (locked to `False`) |
| Runtime Policy Mutation | `OUT_OF_SCOPE` | N/A (forbidden) |

---

## D. Non-Goals

This Task (ERP-00) explicitly does **NOT** do any of the following:
- Live pipeline wiring.
- Model routing changes.
- Multi-model orchestration.
- Long-term Claim graph.
- Invalidation propagation.
- New database creation in Nexus.
- New Event Store in Nexus.
- New Receipt Core in Nexus.
- New Acceptance Engine in Nexus.
- New MCP Server.
- Production migration.
- Public benchmark claims or unlock.

---

## E. Next Gate

The next planned milestone is:
```text
ERP-01-epistemic-profile-read-only-tracer-bullet
```

*Note: ERP-01 is NOT authorized by this Task. ERP-01 will only perform synthetic Research Ledger export to `EpistemicProfileInput` and test read-model adapter conversion without live runtime wiring.*

---

## F. Benchmark Gate & Future Evaluation

In future milestones, research efficacy will be evaluated across:
1. Strong Prompt + Checklist baseline.
2. Nexus standard acceptance baseline.
3. Nexus + Epistemic Research Profile.

This ERP-00 foundation does NOT claim that Epistemic Research Profile has improved research quality or reduced errors.
