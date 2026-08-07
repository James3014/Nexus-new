# OpenWiki Canonical Integration Pilot Specification

- **Spec ID:** `SPEC-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808`
- **Status:** `READY_FOR_TASK_CARDS`
- **Basis snapshot:** `/Users/jameschen/Workspace/nexus`, branch `nexus/integration/main`, HEAD `dac6e7279981828ed135f27c1c42449b0a1fd9c7`, clean; explicit Owner decisions through 2026-08-08
- **Supersedes:** `none`
- **Claim ceiling:** `OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY`

## 1. Problem statement

Nexus has verified that OpenWiki can generate useful repository-derived implementation documentation, but the existing OpenWiki campaign is only a simplified Task Card contract. It does not yet provide validator-compatible requirement lineage, explicit V3 currentness/wiring classification, or a complete fail-closed boundary between derived OpenWiki observations and Nexus governance authority.

## 2. Desired outcome

Establish one validator-compatible governance contract for a manual-only OpenWiki pilot scaffold so that a later isolated implementation Candidate may create exactly `.openwikiignore`, `openwiki/INSTRUCTIONS.md`, and `.github/workflows/openwiki-update.yml` without granting OpenWiki authority over Nexus routing, governance, approval, integration, or the governed Wiki.

## 3. Basis, coverage, and freshness

Current repository evidence was re-read at `/Users/jameschen/Workspace/nexus`, branch `nexus/integration/main`, HEAD `dac6e7279981828ed135f27c1c42449b0a1fd9c7`, clean.

The current root `AGENTS.md`, the OpenWiki simplified campaign/index, its active Task Card, `.github/workflows/benchmark-ci.yml`, `nexus_wiki_vault/99_Schema/WIKI_GOVERNANCE_CHARTER.md`, and `nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml` were used as repository evidence.

The Wiki authority manifest records older verification metadata than the current repository HEAD. This specification therefore uses it only for the Wiki authority mapping it declares and does not use it as evidence of current runtime behavior.

Reads of `.openwikiignore`, `openwiki/INSTRUCTIONS.md`, and `.github/workflows/openwiki-update.yml` at the basis snapshot returned that they are not regular files. The specification therefore claims only that the three proposed implementation paths are not regular files at this snapshot.

## 4. Source and decision ledger

| ID | Class | Statement | Authority/location | Freshness/snapshot | Status | Limitation |
| --- | --- | --- | --- | --- | --- | --- |
| DEC-001 | DEC | James Chen approved creation of the governed OpenWiki canonical-integration pilot. | Owner decision | 2026-08-08 | BINDING | Limited to the OpenWiki pilot |
| DEC-002 | DEC | James Chen approved completing the OpenWiki specification and Task Card contract while using manual Agy handoff because Nexus MCP to Agy dispatch is not yet reliable. | Owner decision | 2026-08-08 | BINDING | Manual handoff does not grant Agy approval or integration authority |
| DEC-003 | DEC | ChatGPT owns contract authoring and independent review; Agy is a bounded executor for exact file application and later bounded implementation. | Owner decision | 2026-08-08 | BINDING | Does not change CapabilityPlanner or HybridRouteDecision authority |
| CUR-001 | CUR | Canonical repository is `/Users/jameschen/Workspace/nexus` on `nexus/integration/main`, HEAD `dac6e7279981828ed135f27c1c42449b0a1fd9c7`, clean at specification freeze. | Nexus workspace snapshot | HEAD dac6e7279981828ed135f27c1c42449b0a1fd9c7 | EVIDENCE | Source snapshot only |
| CUR-002 | CUR | `.github/workflows/benchmark-ci.yml` uses `GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}` as an existing repository secret convention. | `.github/workflows/benchmark-ci.yml` | HEAD dac6e7279981828ed135f27c1c42449b0a1fd9c7 | EVIDENCE | Does not prove the secret is populated |
| CUR-003 | CUR | `.openwikiignore`, `openwiki/INSTRUCTIONS.md`, and `.github/workflows/openwiki-update.yml` are not regular files at the basis snapshot. | Bounded Nexus reads | HEAD dac6e7279981828ed135f27c1c42449b0a1fd9c7 | EVIDENCE | Does not claim anything about external or ignored filesystem locations |
| CON-001 | CON | Root `AGENTS.md` is repository authority; `MUSE_PROTO.md` is only a response/domain overlay; CapabilityPlanner and HybridRouteDecision remain route authority; delegated models cannot approve, integrate, push, or claim production readiness. | `AGENTS.md` | HEAD dac6e7279981828ed135f27c1c42449b0a1fd9c7 | BINDING | Repository governance scope |
| CON-002 | CON | Generated Wiki retrieval material is derived, read-only, non-authoritative, and authority originates from `WIKI_AUTHORITY_MANIFEST.yaml`. | `nexus_wiki_vault/99_Schema/WIKI_GOVERNANCE_CHARTER.md` and `WIKI_AUTHORITY_MANIFEST.yaml` | Repository content at HEAD dac6e7279981828ed135f27c1c42449b0a1fd9c7; manifest verification metadata is older | BINDING | Used for authority boundary, not current runtime truth |
| CON-003 | CON | The current Git-tracked OpenWiki campaign authorizes exactly the three-file manual pilot scaffold, pinned OpenWiki 0.3.1, telemetry disabled, existing `GEMINI_API_KEY` convention, no schedule, no repository write permission, no generated Wiki integration, no approval/integration/push, and `AUTO_CHAIN=false`. | `tasks/openwiki-canonical-integration-pilot-20260808/INDEX.md` and active Task Card | HEAD dac6e7279981828ed135f27c1c42449b0a1fd9c7 | BINDING | Simplified contract being normalized by this specification |
| DER-001 | DER | Excluding `tasks/` from OpenWiki input reduces the risk that planned or authorized future work is misrepresented as current implementation evidence. | Derived from CON-001 and the implementation-observation purpose | 2026-08-08 | CONTEXT_ONLY | Safety derivation; does not create a new governance authority |
| REJ-001 | REJ | Automatic scheduling, generated-Wiki canonical integration, autonomous `nexus_wiki_vault/` mutation, repository write permission, automatic PR/push, OpenWiki authority promotion, and auto-chain are rejected for this pilot phase. | Approved current pilot contract | HEAD dac6e7279981828ed135f27c1c42449b0a1fd9c7 | REJECTED | May be reconsidered only by a later Owner decision |

## 5. Current verified state

The canonical checkout is clean at HEAD `dac6e7279981828ed135f27c1c42449b0a1fd9c7` (CUR-001).

Root `AGENTS.md` defines repository, route, execution, verification, and Owner-only authority boundaries relevant to this pilot (CON-001).

The governed Wiki explicitly distinguishes generated retrieval aids from authoritative Wiki content (CON-002).

The current OpenWiki campaign already contains the intended three-file pilot objective but in a simplified contract form (CON-003).

The proposed implementation paths are not regular files at the current source snapshot (CUR-003).

## 6. Owner decisions

* DEC-001 authorizes the governed OpenWiki pilot.
* DEC-002 authorizes completing its specification/Task Card contract and permits manual Agy handoff while MCP dispatch remains unreliable.
* DEC-003 assigns contract authorship and independent review to ChatGPT and keeps Agy in bounded executor/implementer scope.

## 7. Canonical terminology

`derived_non_authoritative` means repository-derived observation that may assist understanding but cannot replace repository authority, Wiki authority, route authority, verification, approval, integration, or production evidence.

`implementation_status` describes whether an implementation artifact is current code, test-only, historical/legacy, or unknown.

`wiring_status` describes whether current wiring to a named execution surface is physically evidenced.

`runtime_surfaces` names the concrete surfaces to which wiring is evidenced, such as main CLI, MCP Gateway, local runtime, standalone ops, benchmark, or test.

`authority_roles` records only physically supported authority roles and must distinguish route, execution, governance, derived-only, and none.

`evidence_basis` records the evidence class supporting the observation, such as current caller, entrypoint, service registration, runtime dispatch, test-only evidence, historical documentation, package metadata, or unknown.

`claim_ceiling` states the maximum claim the available evidence supports.

`manual canary` means a later Owner-controlled OpenWiki execution used to evaluate the generated output. It is not production validation or governed-Wiki promotion.

## 8. Change delta

Mode: BROWNFIELD

Baseline: the current simplified OpenWiki campaign and Task Card at repository HEAD `dac6e7279981828ed135f27c1c42449b0a1fd9c7`.

### ADDED

A formal source specification with stable `DEC-*`, `CUR-*`, `CON-*`, `DER-*`, `REJ-*`, `REQ-*`, and `AC-*` lineage is added.

A derived safety rule excludes `tasks/` from OpenWiki input so planned work cannot silently become evidence of current implementation.

### MODIFIED

The existing monolithic pilot objective is normalized into six complete future requirements:

* REQ-001 makes the derived authority boundary explicit.
* REQ-002 replaces a single coarse wiring label with a six-axis V3 evidence model.
* REQ-003 makes the read boundary explicit and adds `tasks/` plus `.nexus/` to governance/runtime exclusions.
* REQ-004 makes the manual-only pinned workflow contract falsifiable.
* REQ-005 makes restoration and changed-path containment falsifiable.
* REQ-006 makes isolated Candidate scope and Owner-only approval/integration explicit.

Impact: `EVIDENCE_ONLY` and `OPERATIONAL`. The intended pilot scope remains three implementation files.

### REMOVED

none

### RENAMED

The simplified campaign identity `openwiki-canonical-integration-pilot-20260808` is normalized to `CAMPAIGN-OPENWIKI-CANONICAL-INTEGRATION-PILOT-20260808`.

The simplified Task ID `OPENWIKI-INTEGRATION-PILOT-01` is normalized to `TASK-OPENWIKI-INTEGRATION-PILOT-01`.

The prior identities remain preserved in supersession history.

## 9. Scope

In scope is the contract for a later isolated Candidate that creates exactly:

* `.openwikiignore`
* `openwiki/INSTRUCTIONS.md`
* `.github/workflows/openwiki-update.yml`

The pilot may read current Nexus implementation sources in order to generate a derived implementation Wiki during a later manual canary.

## 10. Non-goals

The pilot does not authorize automatic scheduling, automatic commits, automatic PR creation, push, approval, integration, release, deployment, production claims, autonomous governed-Wiki updates, route changes, model-workforce changes, or generated Wiki commits.

## 11. User and operator stories

1. As the Nexus Owner, James can manually request an OpenWiki canary without giving the workflow repository write authority.
2. As a reviewer, ChatGPT can distinguish code existence, current wiring, runtime surface, authority, evidence basis, and claim ceiling in generated observations.
3. As a governed-Wiki maintainer, James can review OpenWiki output without allowing it to overwrite `nexus_wiki_vault/`.
4. As an implementation worker, Agy can create only the three approved scaffold files and cannot approve or integrate its own Candidate.

## 12. Architecture and authority boundaries

`AGENTS.md` governs repository/agent authority.

CapabilityPlanner and HybridRouteDecision remain Nexus route authority.

`nexus_wiki_vault/99_Schema/WIKI_AUTHORITY_MANIFEST.yaml`, under the Wiki governance charter, identifies Wiki authority. OpenWiki output cannot modify or replace that authority.

`MUSE_PROTO.md` remains a response/domain overlay and is not promoted into parallel repository or Wiki authority.

OpenWiki is a derived implementation-observation producer only.

Agy is a Candidate producer only.

Verification and independent review do not grant Owner approval or integration authority.

## 13. Requirements

### REQ-001 — Derived authority boundary

- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-003, CON-001, CON-002, CON-003, REJ-001`
- **Behavior:** The OpenWiki pilot SHALL treat generated `openwiki/` material as `derived_non_authoritative` implementation observation and SHALL NOT grant OpenWiki route, architecture, repository-governance, Wiki-governance, verification, receipt, approval, integration, release, or public-claim authority.
- **Failure behavior:** Any pilot configuration or output path that promotes OpenWiki material to governed truth or modifies `nexus_wiki_vault/` SHALL fail the pilot.
- **Rationale:** The implementation Wiki is useful only if it cannot compete with Nexus governance authority.
- **Authority/interface:** `AGENTS.md`; Wiki governance charter and authority manifest; generated `openwiki/`.
- **Non-goal linkage:** Section 10.

### REQ-002 — V3 multi-axis implementation classification

- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-003, CON-001, CON-003`
- **Behavior:** `openwiki/INSTRUCTIONS.md` SHALL require important subsystem, service, engine, router, executable, workflow, capability, and runtime claims to record `implementation_status`, `wiring_status`, `runtime_surfaces`, `authority_roles`, `evidence_basis`, and `claim_ceiling`. It SHALL state that code existence does not prove current wiring, wiring does not prove canonical authority, tests prove tested behavior only, historical documents/package metadata do not prove current wiring, and ambiguity SHALL remain explicit when current evidence is insufficient.
- **Failure behavior:** Missing axes, conflation of existence with wiring, unsupported authority promotion, or unsupported current-runtime promotion SHALL fail verification.
- **Rationale:** V2 showed that a single wired/unwired status cannot represent components that are current on one runtime surface but absent from another.
- **Authority/interface:** `openwiki/INSTRUCTIONS.md`.
- **Non-goal linkage:** Section 10.

### REQ-003 — OpenWiki read boundary

- **Status:** `SETTLED`
- **Source:** `DEC-001, CON-001, CON-002, CON-003, DER-001`
- **Behavior:** `.openwikiignore` SHALL exclude at minimum `nexus_wiki_vault/`, `tasks/`, `.nexus/`, `nexus-evolve`, `MUSE_PROTO.md`, `.antigravitycli/`, `.pyre/`, and `docs/incidents/LATEST_RCA.md`. It SHALL NOT globally exclude the implementation roots `nexus/`, `scripts/`, `src/`, or `tests/`.
- **Failure behavior:** Missing a required exclusion or globally excluding a required implementation root SHALL fail verification.
- **Rationale:** Governance/planning overlays, symlink aliases, protected state, and generated/runtime noise must not be mistaken for implementation truth.
- **Authority/interface:** `.openwikiignore`.
- **Non-goal linkage:** Section 10.

### REQ-004 — Manual-only pinned workflow

- **Status:** `SETTLED`
- **Source:** `DEC-001, DEC-002, CON-003, CUR-002, REJ-001`
- **Behavior:** `.github/workflows/openwiki-update.yml` SHALL use `workflow_dispatch` only, SHALL contain no schedule trigger, SHALL use `contents: read` and no repository write permission, SHALL install or invoke OpenWiki pinned to `0.3.1`, SHALL set `OPENWIKI_TELEMETRY_DISABLED`, SHALL use the repository `GEMINI_API_KEY` secret convention, SHALL expose generated `openwiki/` only through an ephemeral workflow artifact, and SHALL contain no commit, push, PR creation, approval, or integration step.
- **Failure behavior:** Any scheduled trigger, repository write permission, automatic commit/push/PR, unpinned OpenWiki execution, or missing telemetry-disable/secret binding SHALL fail verification.
- **Rationale:** The first canonical pilot must be manually invoked and observational.
- **Authority/interface:** GitHub Actions workflow.
- **Non-goal linkage:** Section 10.

### REQ-005 — Fail-closed side-effect containment

- **Status:** `SETTLED`
- **Source:** `DEC-001, CON-001, CON-002, CON-003, REJ-001`
- **Behavior:** After OpenWiki execution, the workflow SHALL restore `AGENTS.md`, `CLAUDE.md`, and `.github/workflows/openwiki-update.yml` from `HEAD`, SHALL explicitly detect any `nexus_wiki_vault/` change as failure, and SHALL fail closed if any remaining repository change exists outside `openwiki/`.
- **Failure behavior:** Any unresolved modification or untracked path outside `openwiki/`, or any observed `nexus_wiki_vault/` mutation, SHALL make the workflow fail and SHALL NOT be written back.
- **Rationale:** OpenWiki may maintain root instruction blocks, so the workflow must neutralize side effects before accepting its output as an artifact.
- **Authority/interface:** GitHub Actions post-generation containment.
- **Non-goal linkage:** Section 10.

### REQ-006 — Bounded isolated Candidate implementation

- **Status:** `SETTLED`
- **Source:** `DEC-002, DEC-003, CON-001, CON-003, REJ-001`
- **Behavior:** The implementation Task Card SHALL authorize creation of only `.openwikiignore`, `openwiki/INSTRUCTIONS.md`, and `.github/workflows/openwiki-update.yml`. Implementation SHALL occur in an isolated Candidate, SHALL NOT run OpenWiki against canonical during implementation, SHALL NOT commit generated Wiki pages, SHALL preserve `AUTO_CHAIN=false`, and SHALL leave approval/integration/push to the Owner-controlled downstream gate.
- **Failure behavior:** Any out-of-scope mutation, generated Wiki commit, canonical OpenWiki execution, worker approval/integration/push, or successor-task execution SHALL hard-block the Candidate.
- **Rationale:** The first implementation step should establish containment before any canonical canary is attempted.
- **Authority/interface:** Governed Task Card and isolated Candidate.
- **Non-goal linkage:** Section 10.

## 14. Behavioral and interface decisions

The OpenWiki classification contract is multi-axis rather than a single status.

`implementation_status` may express current implementation, test-only implementation, historical/legacy implementation, or unknown.

`wiring_status` may express wired, unwired, or unknown and must name supporting current evidence.

`runtime_surfaces` must name the concrete observed surface rather than implying system-wide wiring.

`authority_roles` must not infer authority from class names, package metadata, tests, or existence.

`evidence_basis` must distinguish current callers/entrypoints/registration/runtime dispatch from test-only, historical-document, package-metadata, or unknown evidence.

`claim_ceiling` must never exceed the strongest evidence basis.

The workflow is manually invoked and read-only with respect to the repository. Generated OpenWiki content is an artifact, not a repository mutation.

## 15. Verification seam

The highest evidence level required for this scaffold is static Candidate verification.

Verification must inspect the complete isolated Candidate diff, exact three-file scope, workflow permissions/triggers, OpenWiki pin, telemetry/secret binding, restoration logic, path-containment logic, V3 instruction tokens, ignore boundary, and negative controls.

A green worker report alone is insufficient. The exact Candidate commit/tree and verifier output must be independently reviewed.

## 16. Acceptance criteria

### AC-001 — Derived authority boundary verification

- **Requirement:** `REQ-001`
- **Evidence level:** `STATIC`
- **Verification seam:** `openwiki/INSTRUCTIONS.md`, workflow contract, and exact Candidate diff
- **Pass:** The scaffold explicitly marks OpenWiki output `derived_non_authoritative` and prohibits route, governance, approval, integration, release, and governed-Wiki authority promotion.
- **Negative control:** Merely mentioning that OpenWiki is derived without prohibiting authority promotion does not pass.
- **Fail:** Any authority promotion or `nexus_wiki_vault/` write path is present.
- **Receipt binding:** Candidate commit/tree plus verifier outputs.

### AC-002 — V3 classification verification

- **Requirement:** `REQ-002`
- **Evidence level:** `STATIC`
- **Verification seam:** Static content assertions on `openwiki/INSTRUCTIONS.md`
- **Pass:** All six axes are present and existence, wiring, surface, authority, evidence, and claim ceiling are explicitly separated.
- **Negative control:** A single `WIRED_CURRENT` or `PRESENT_UNWIRED` field alone cannot satisfy the criterion.
- **Fail:** Any required axis or ambiguity rule is absent.
- **Receipt binding:** Candidate commit/tree plus verifier outputs.

### AC-003 — Read-boundary verification

- **Requirement:** `REQ-003`
- **Evidence level:** `STATIC`
- **Verification seam:** Static content assertions on `.openwikiignore`
- **Pass:** Every required governance/runtime exclusion is present and `nexus/`, `scripts/`, `src/`, and `tests/` are not globally excluded.
- **Negative control:** A broad ignore that also removes required implementation roots does not pass.
- **Fail:** Any required exclusion is missing or any required implementation root is globally ignored.
- **Receipt binding:** Candidate commit/tree plus verifier outputs.

### AC-004 — Manual workflow verification

- **Requirement:** `REQ-004`
- **Evidence level:** `STATIC`
- **Verification seam:** Static inspection of `.github/workflows/openwiki-update.yml`
- **Pass:** `workflow_dispatch`, `contents: read`, OpenWiki `0.3.1`, telemetry disable, `GEMINI_API_KEY`, and artifact upload are present; schedule, repository write permissions, commit, push, and PR creation are absent.
- **Negative control:** A workflow that is read-only in practice but requests write permission does not pass.
- **Fail:** Any prohibited trigger, permission, write action, or unpinned invocation is present.
- **Receipt binding:** Candidate commit/tree plus verifier outputs.

### AC-005 — Side-effect containment verification

- **Requirement:** `REQ-005`
- **Evidence level:** `STATIC`
- **Verification seam:** Workflow restoration and changed-path logic
- **Pass:** The workflow explicitly restores the three named root/workflow files, separately guards `nexus_wiki_vault/`, and fails if post-restoration changes remain outside `openwiki/`.
- **Negative control:** Relying only on GitHub runner ephemerality does not pass.
- **Fail:** Restoration, Wiki guard, or outside-`openwiki/` fail-closed logic is missing.
- **Receipt binding:** Candidate commit/tree plus verifier outputs.

### AC-006 — Candidate scope verification

- **Requirement:** `REQ-006`
- **Evidence level:** `STATIC`
- **Verification seam:** Single-commit diff and Task Card authority review
- **Pass:** The implementation Candidate commit changes exactly `.openwikiignore`, `.github/workflows/openwiki-update.yml`, and `openwiki/INSTRUCTIONS.md`, with `AUTO_CHAIN=false` and no generated Wiki pages.
- **Negative control:** Any additional path, generated OpenWiki page, or worker approval/integration step fails.
- **Fail:** Candidate scope or authority exceeds the Task Card.
- **Receipt binding:** Candidate commit SHA, tree SHA, Task Card SHA, Spec SHA, and verifier outputs.

## 17. Traceability matrix

| Requirement | Sources | Delta | Acceptance | Evidence level | Claim ceiling | Task-card handoff group |
| --- | --- | --- | --- | --- | --- | --- |
| REQ-001 | DEC-001, DEC-003, CON-001, CON-002, CON-003, REJ-001 | MODIFIED | AC-001 | STATIC | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | OPENWIKI-PILOT-SCAFFOLD |
| REQ-002 | DEC-001, DEC-003, CON-001, CON-003 | MODIFIED | AC-002 | STATIC | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | OPENWIKI-PILOT-SCAFFOLD |
| REQ-003 | DEC-001, CON-001, CON-002, CON-003, DER-001 | MODIFIED | AC-003 | STATIC | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | OPENWIKI-PILOT-SCAFFOLD |
| REQ-004 | DEC-001, DEC-002, CON-003, CUR-002, REJ-001 | MODIFIED | AC-004 | STATIC | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | OPENWIKI-PILOT-SCAFFOLD |
| REQ-005 | DEC-001, CON-001, CON-002, CON-003, REJ-001 | MODIFIED | AC-005 | STATIC | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | OPENWIKI-PILOT-SCAFFOLD |
| REQ-006 | DEC-002, DEC-003, CON-001, CON-003, REJ-001 | MODIFIED | AC-006 | STATIC | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | OPENWIKI-PILOT-SCAFFOLD |

## 18. Evidence and claim ceiling

This specification and the first implementation Candidate can establish only static scaffold conformance.

They cannot establish successful OpenWiki generation, correctness of generated documentation, GitHub Actions execution, provider availability, production readiness, governed-Wiki correctness, or public claimability.

Maximum claim: `OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY`.

## 19. Rollback and failure handling

A governance Candidate that fails structure or lineage review is rejected without canonical mutation.

An implementation Candidate that fails scope or static verification is rejected without approval or integration.

A later manual canary that detects OpenWiki side effects, provider failure, misleading classifications, or governed-Wiki mutation fails closed. Its generated artifact remains non-authoritative.

## 20. Documentation and learning write-back

The campaign INDEX and Task Card may record bounded completion evidence.

Generated OpenWiki pages do not automatically update `nexus_wiki_vault/`.

Any future promotion of an OpenWiki observation into governed documentation requires a separate evidence review and Owner/governance decision.

## 21. Risks and unknowns

The main residual risks are OpenWiki version-specific behavior, model-generated semantic errors, GitHub Actions environment differences, provider availability, and false currentness claims in generated documentation.

These risks are intentionally deferred to the later manual canary and do not broaden the scaffold claim ceiling.

## 22. Unresolved owner decisions

none

## 23. Task-card handoff boundary

| Task group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OPENWIKI-PILOT-SCAFFOLD | REQ-001; REQ-002; REQ-003; REQ-004; REQ-005; REQ-006 | AC-001; AC-002; AC-003; AC-004; AC-005; AC-006 | Repository contains a manual-only, read-only OpenWiki pilot scaffold with V3 classification and fail-closed side-effect boundaries, without generated Wiki integration. | none | static file contract + isolated Candidate diff + `git diff --check` | OPENWIKI_PILOT_SCAFFOLD_READY_FOR_MANUAL_CANARY | small | not applicable | none |

## 24. Out of scope

Automatic scheduling, autonomous PR/push, generated Wiki commits, direct `nexus_wiki_vault/` mutation, model-workforce changes, Nexus route changes, release/deployment, production claims, and automatic successor execution remain out of scope.

## 25. Supersession and change history

2026-08-08: This specification formalizes the already approved simplified OpenWiki pilot campaign at current canonical HEAD `dac6e7279981828ed135f27c1c42449b0a1fd9c7`.

It does not treat prior rejected isolated governance Candidates as authority.
