# Open SWE External Runtime Corrective Contract

contract_id: `OPEN_SWE_EXTERNAL_RUNTIME_CORRECTIVE_CONTRACT_V1`

- **Campaign:** `CAMPAIGN-OPEN-SWE-EXECUTION-PRODUCTIONIZATION-V1`
- **Mode:** `BOOTSTRAP_GOVERNANCE`
- **Status:** `ACTIVE_CORRECTIVE_CONSTRUCTION`
- **Owner authority:** corrective handoff issued 2026-09-01; external runtime topology is binding unless fresh evidence proves in-process runtime materially required
- **Bound repository:** `James3014/Nexus-new`
- **Corrective base:** `7a2eb15ded8f5a4053bac3ff25f67ef90f21d0d2`
- **Auto-chain:** `false`
- **Claim ceiling before independent acceptance:** `EXTERNAL_RUNTIME_CORRECTIVE_CANDIDATE_NOT_YET_VERIFIED`

## Mission

Correct the topology drift that embedded Open SWE / Deep Agents runtime internals in the Nexus Python dependency/process domain. Nexus remains the controller, policy authority, durable execution/reconciliation authority, Candidate verifier, acceptance authority, and GitHub/merge authority. Open SWE / Deep Agents runs as external execution infrastructure behind a thin typed subprocess/JSON boundary.

## Binding architecture

```text
Nexus control plane
  - CapabilityPlanner / Workforce Admission
  - request / attempt / replay / reconciliation
  - credential and GitHub authority
  - Candidate verification / acceptance
        |
        | versioned request/result protocol
        v
external `nexus-open-swe-runtime` process
  - Deep Agents semantic execution
  - diagnosis execution
  - bounded repair execution
  - runtime-local durable operation/session state
        |
        v
structured result / Candidate identity
        |
        v
Nexus independent verification / acceptance
```

The following are explicitly not architecture authority:

- the historical Pilot using Python imports;
- the historical TASK-001 instruction to add Open SWE dependencies to root `pyproject.toml` / `uv.lock`;
- the one-time four-hash trusted dependency transition;
- the historical activation contract decision that assumed the in-process topology.

## Governance invariants

1. **Authority:** Nexus keeps route/admission/replay/Candidate/acceptance/GitHub/merge/release authority.
2. **Scope:** corrective work may change only the existing Open SWE transport/service/tests, this campaign's corrective documentation, `runtimes/open_swe/**`, and root dependency declarations/lock needed to remove the accidental Core dependency ownership.
3. **Revision truth:** every later Candidate/acceptance claim binds exact commit/tree/diff.
4. **Minimum evidence:** external runtime tests, focused Nexus transport/service tests, dependency isolation checks, static checks, and `git diff --check` must pass or expose a bounded next-gate blocker.
5. **Integration boundary:** construction evidence is not acceptance, merge, loaded-runtime activation, release, deploy, or production truth.

## External runtime dependency domain

`runtimes/open_swe/` is the owner of Open SWE runtime dependencies:

- `deepagents==0.7.6`
- `google-genai==1.74.0`
- `langchain-core==1.5.2`
- `langchain-google-genai==4.3.2`

The runtime package SHALL have its own reproducible lock. Nexus root SHALL NOT need these packages merely to import/start the default control plane. A runtime upgrade should normally modify the nested runtime dependency domain only; Nexus root dependency changes are justified only when the versioned external protocol/client contract itself changes.

## Transport contract

The Nexus-owned adapter is a thin client. It may:

- spawn the configured `nexus-open-swe-runtime` executable;
- send a versioned JSON request over stdin;
- parse one bounded JSON result from stdout;
- bind request/operation/session/worker identities;
- enforce timeout and reconcile-before-retry semantics;
- sanitize child environment so only explicitly allowed provider credential material is propagated.

It SHALL NOT import Deep Agents/LangChain runtime internals, host graphs in-process, own a second queue/router/replay authority, or grant Open SWE Git/GitHub/approval/merge/release/deploy authority.

## Physical security invariant

Semantic and diagnosis graph tool surfaces physically exclude write/edit/delete, arbitrary execute/shell, task/subagent escape, generic HTTP/network, Git/GitHub mutation, merge, release, and deploy. Repair is limited to read/write/edit inside the controller-authorized isolated workspace paths. Reusable GitHub credentials remain controller-side.

## Corrective evidence log

- `EXTERNAL_RUNTIME_CONFIRMED`: existing Nexus semantic and worker transport contracts can express execution/result/reconciliation across a process boundary; no material requirement requiring co-process Deep Agents was found.
- Live runtime was rolled back to the OpenCLI/OpenCode control arm before corrective source work continued.
- Corrective worktree rebound at `7a2eb15ded8f5a4053bac3ff25f67ef90f21d0d2`.
- Nexus focused transport/service regression previously produced `98 passed` on the corrective worktree.
- External runtime suite now produces `7 passed` on the pinned runtime environment.
- The runtime suite caught and corrected two real compatibility/security defects: missing LangChain tool descriptions and a Deep Agents HarnessProfile key mismatch that otherwise reintroduced the `task` subagent tool.

## Current corrective gates

- **G6 — Corrective documents / authority:** **COMPLETE.** Spec, INDEX, historical TASK-001, and historical activation contract now point to this external-runtime corrective authority without rewriting historical evidence.
- **G7 — Dependency-domain isolation:** **COMPLETE.** `runtimes/open_swe` owns its pinned dependencies plus nested `uv.lock`; the Nexus thin client imports no Deep Agents/LangChain runtime. A fresh temporary rebuild from the nested lock installed successfully and ran the runtime suite `7 passed`.
- **G8 — Root dependency cleanup:** **COMPLETE.** The accidental root `open-swe` optional dependency is removed and root `uv.lock` regenerated with no `open-swe`, `deepagents`, `langchain-google-genai`, or `google-genai` references. Root and nested `uv lock --check` pass. The historical four-hash trusted-transition witness is intentionally deferred to G9.

## Corrective sealing gates

- **G9 — Trusted-transition cleanup:** **COMPLETE.** Root `pyproject.toml` and `uv.lock` returned exactly to the former trusted-baseline hashes. The PR #669 four-hash transition remains preserved as `RETIRED_TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION` historical evidence while the active validator exposes no transition exception; focused trusted-anchor transition tests pass.
- **G10 — Static / dependency verification:** **COMPLETE.** Root and nested Ruff pass; Open SWE thin-client/service Pyright reports 0 errors; root/nested `uv lock --check`, `git diff --check`, and deletion guard pass. `trusted_deletion_anchor.py` retains 22 pre-existing Pyright errors on both exact base and Candidate worktree and is classified as baseline debt rather than Candidate regression.
- **G11 — Final focused regression:** **COMPLETE.** Final corrective revision passes 98 External Intelligence/Open SWE service tests, 82 trusted-anchor tests, and 11 external runtime tests.
- **G12 — Security boundary:** **COMPLETE.** Real Deep Agents graph inventory excludes execute/shell/task/delete/http/git-push surfaces; bounded repair rejects out-of-scope writes; source audit finds no Nexus route/admission/GitHub/merge/release/deploy authority added to the runtime boundary.
- **G13 — Credential isolation:** **COMPLETE.** The Nexus process environment builder passes only system essentials plus the selected provider credential and excludes GitHub/GH/unrelated secrets; runtime durable state tests prove environment/secret values are not persisted.
- **G14 — Failure / recovery:** **COMPLETE.** Semantic STARTED-without-terminal and worker ambiguous repair both become `OPEN_SWE_OUTCOME_UNKNOWN` with `retry_safe=false`; reconciliation returns durable/read-only state and does not redispatch or reexecute the repair.
- **G15 — Identity / attestation:** **COMPLETE.** Nexus client rejects provider/model/worker attestation substitution and invalid session IDs; external runtime retained sessions now rebind workspace, provider, model, and worker identity and reject all four substitution classes with `SESSION_BINDING_MISMATCH`.
- **G16 — Immutable Candidate freeze:** **COMPLETE.** The corrective implementation, tests, dependency boundaries, retired trusted transition, and this contract are frozen as an exact scoped committed Candidate. The physical Candidate receipt binds the final base/head/tree/diff; independent acceptance remains a separate G17 authority.

## Remaining gates after G16

Independent Candidate acceptance; corrective PR/exact CI; protected merge; post-merge exact-main verification; external-runtime clean-install/package proof on merged main; production-shaped semantic/diagnosis/repair/timeout canaries; control-arm rollback witness; final architecture/authority audit; `READY_FOR_ACTIVATION_DECISION` receipt.
