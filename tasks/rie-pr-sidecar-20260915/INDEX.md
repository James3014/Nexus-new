# Repository Intelligence PR Sidecar Integration

- **Campaign ID:** `CAMPAIGN-RIE-PR-SIDECAR-20260915`
- **Status:** `READY_FOR_OWNER_REVIEW`
- **Source mode:** `APPROVED_NON_SPEC`
- **Source spec ID:** `none`
- **Source spec SHA-256:** `none`
- **Source basis snapshot:** `James3014/Nexus-new#969 @ 2026-09-15T07:02:30Z`; `nexus.project_entry` binding `8f9f1b4e6563f8aabb5c0a2397af0daa78b95bf10070adfda11a13cce6453206`; GitHub `main` `68d8b5408f3d4fe60a701d9c79ccd6a2129549c5`; PR #968 original head `32bc3b6844c24fc4ed9be691ce55674a27aab6ae`
- **Auto-chain:** `false`
- **Parallel execution:** `false`
- **Current frontier:** `TASK-001`
- **Maximum campaign claim:** `NEXUS_NEW_RIE_READ_ONLY_PR_SIDECAR_INTEGRATED`

## 1. Source handoff import

| Source group | Requirements | Acceptance | Observable outcome | Dependency seam | Verification seam | Maximum claim | Scope class | Minimum MCP profile | Known blocker | Compiled tasks |
|---|---|---|---|---|---|---|---|---|---|---|
| `ISSUE-969-RIE-SIDECAR` | `REQ-969-1` | `AC-969-1`–`AC-969-8` | Nexus-new PRs automatically emit read-only RIE advisory evidence from the accepted workflow | immutable `repository-intelligence-engine@v0.1.1`; existing Nexus-new CI remains authoritative for CI | exact PR head/base/main; changed paths; exact-head CI; RIE artifact; independent acceptance; protected merge/readback | `NEXUS_NEW_RIE_READ_ONLY_PR_SIDECAR_INTEGRATED` | `small` | `CANDIDATE` | final protected merge requires fresh canonical completion-host source and a valid current `GITHUB_MERGE` standing grant | `TASK-001` |

## 2. Requirement coverage

| Requirement | Acceptance | Implementing task | Witness task | Coverage status |
|---|---|---|---|---|
| `REQ-969-1` | `AC-969-1` | `TASK-001` | `TASK-001` | `FULL` |
| `REQ-969-1` | `AC-969-2` | `TASK-001` | `TASK-001` | `FULL` |
| `REQ-969-1` | `AC-969-3` | `TASK-001` | `TASK-001` | `FULL` |
| `REQ-969-1` | `AC-969-4` | `TASK-001` | `TASK-001` | `FULL` |
| `REQ-969-1` | `AC-969-5` | `TASK-001` | `TASK-001` | `FULL` |
| `REQ-969-1` | `AC-969-6` | `TASK-001` | `TASK-001` | `FULL` |
| `REQ-969-1` | `AC-969-7` | `TASK-001` | `TASK-001` | `FULL` |
| `REQ-969-1` | `AC-969-8` | `TASK-001` | `TASK-001` | `FULL` |

## 3. Dependency graph

| Task ID | Status | Type | Slicing strategy | Blocked by | Edge type | Unlock evidence | Observable outcome | Verification seam | Maximum claim | Scope class | MCP profile | Transport status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `TASK-001` | `ACTIVE` | `INTEGRATION_VERIFY` | `TRACER_BULLET` | `none` | `none` | `none` | accepted workflow + inert governance artifacts are independently verified and eligible for the repository's protected-merge gate | exact-head diff/CI/RIE artifact + independent acceptance + fresh merge preflight | before merge: `NEXUS_NEW_RIE_READ_ONLY_PR_SIDECAR_CANDIDATE_VERIFIED`; after verified merge/readback: campaign maximum claim | `small` | `CANDIDATE` | candidate/acceptance transport available; merge transport must rebind current completion host before mutation |

## 4. Ready candidates and frontier selection

- **Dependency-ready candidates:** `TASK-001`
- **Selected frontier:** `TASK-001`
- **Selection rationale:** the implementation already exists in PR #968 and has prior canary evidence; the smallest remaining work is exact-head re-verification, independent acceptance, and protected integration without reopening implementation design.
- **Exact unblock condition:** `none` for candidate/acceptance work. Protected merge separately requires fresh `NEXUS_CANONICAL_SOURCE_ROOT == GitHub main`, a valid current `GITHUB_MERGE` standing grant, exact accepted head/base, and terminal required checks.

## 5. Campaign authority and non-goals

- Issue #969 is the bounded product/work owner for this integration; #912 remains the parent repository-split/consumer-integration tracker.
- `repository-intelligence-engine` remains the canonical implementation owner.
- This campaign does not create Planner, Router, workforce, CI, verifier, acceptance, merge, release, deployment, or runtime authority.
- RIE evidence remains `ADVISORY_EVIDENCE_ONLY` and never substitutes for terminal CI or independent Candidate acceptance.
- No direct push, force-push, branch-protection weakening, required-check change, runtime activation, or release is authorized.
- Candidate verification, independent acceptance, protected merge, and post-merge readback are separate gates. `AUTO_CHAIN=false`.

## 6. Supersession and change history

- 2026-09-15: compiled from approved non-spec Issue #969 after fleet G1/Wave 1 evidence and before governed continuation of PR #968.
- This campaign does not supersede #912 or any Repository Intelligence owner contract.
