# Campaign Index: G7 Nexus-Governed Coexistence

artifact_authority: current
owner: James Chen
status: closure-recorded (all deferred gates executed 2026-09-07/08; see Live Gate Evidence)
AUTO_CHAIN: false

## Objective

G7-1 rebind: carry a fresh, verifiable, current GitHub `main`-bound `NEXUS_GOVERNED` read-only authority bundle (Task Card + execution grant + INDEX) as an isolated Candidate on a non-main branch, then STOP. Later independent gates close G7: current-main authority readback, positive governed admission, bad-grant single-variable rejection, `OWNER_DIRECT` coexistence witness, no silent fallback, and physical no-mutation reconciliation.

## Frontier

| Order | Milestone | Card | Status | Dependency |
|---:|---|---|---|---|
| 1 | `g7-1-fresh-canonical-authority-rebind-20260907` | `00-g7-nexus-governed-coexistence.md` | COMPLETE (PR #832 merged `31c5c1eb`) | Fresh canonical base `491660f2a...` |
| 2 | `g7-2-current-main-authority-readback-20260907` | (this INDEX, closure section) | COMPLETE | G7-1 candidate present |
| 3 | `g7-4-bad-grant-single-variable-rejection` | (this INDEX, closure section) | PASS | G7-2 readback |
| 4 | `g7-3-positive-nexus-governed-admission` | (this INDEX, closure section) | ADMISSION PASS / provider result: environmental timeout (Acceptance #7) | G7-4 negative first |
| 5 | `g7-5-owner-direct-coexistence-witness` | (this INDEX, closure section) | ADMITTED (coexistence witnessed) / provider result: environmental timeout | G7-3 |
| 6 | `g7-6-no-silent-fallback` | (this INDEX, closure section) | PASS | G7-3 + G7-5 |
| 7 | `g7-7-physical-no-mutation-reconciliation` | (this INDEX, closure section) | PASS | all attempts terminal |

## Bound authority artifacts (fresh rebind)

- Task Card SHA-256 (authoritySha256): `3118948639296773a8b60d5aca2f8db192af031184a2cf084ee5290c1934c350`
- DispatchIntent hash: `e10f08fc344823a6d77899d33d7ee215d8a580c5e614efb572be25fd66740d07`
- Execution grant: `g7-execution-grant-contract.json`
- Grant raw SHA-256: `67fae23dfc905c2a8b4a4e0ec9845c2fffa11d1b4a0bb245aca0a938a08b2d24`
- Grant semantic hash: `281e7d964d50282d3211896fbd93ae839aa8b43d7793a2f629b53dd8ebe4bd1e`
- Target DevSpace base (fresh execution-time GitHub `main`): `491660f2a95eb04e68683e1648c2f9a20744a52a`
- Target profile: `opencode-muse-high-review`
- Attempt: `g7-governed-live-attempt-20260907-01`

Authority admission PASS is separate from provider result PASS and from gate COMPLETE.

## Live gate evidence (2026-09-07/08, Owner-approved quota-recovery chain)

### G7-2B standing-grant reuse — PASS
Physical receipt at `~/.local/state/nexus/authority/standing-grant.json` verified hash-valid (`receipt_hash a780bec2...` recomputed MATCH), time-valid, not revoked, `[GITHUB_MERGE]`, covers PR protected merge for this Goal. Reused; no reissue/hand-edit.

### G7-2C PR #832 rebind + protected merge — COMPLETE
- Normal-drift rebind via `PUT /pulls/832/update-branch` with `expected_head_sha=9262043d...` (CAS): new head `50b0421b...` (merge commit, parents = accepted head `9262043d` + main `82cdc7ae`), delta = exact 3 G7 paths, card/grant bytes byte-identical (`31189486...`/`67fae23d...`), INDEX git blob `b13f4567...`.
- 12 required checks on new head: 11 SUCCESS + 1 SKIPPED (Tier 3 full regression); `mergeStateStatus=CLEAN`.
- Protected merge (standing grant): **MERGED 2026-09-07T22:58:21Z, merge SHA `31c5c1eb3f94645eec2da09cd310fb95df88161b`** = new main tip; 3 G7 files present on main with unchanged bytes.

### G7-2D current-main authority readback — COMPLETE
All bindings verified from main bytes: attemptId/task/base `491660f2a...`/profile `opencode-muse-high-review`/`writeScope=[]`/`effectCeiling=READ_ONLY`/`claimCeiling=RESULT_RETURNED`/time-valid to `2026-09-08T06:18:27Z`/`revocationState=NOT_REVOKED`/`authoritySha256=31189486...`/`grantHash=281e7d96...` (recomputed from main bytes via canonical-JSON sort algorithm). Re-verified byte-identical on `77f04b0b...` after drift.

### Normal-drift rebind #2 (recorded)
Main advanced `31c5c1eb -> 77f04b0b` (PR #839, issue-807 campaign, 6 unrelated runtime/test files). G7 grant/card bytes unchanged on new main (`67fae23d...`/`31189486...`). `nexusGrant.revision` pointer rebound to observed main `77f04b0b...` per resolver semantics (revision MUST equal observed current main); grant NOT reissued, bytes unchanged.

### G7-4 bad-grant single-variable rejection — PASS
Single-variable tamper of `nexusGrant.grantSha256` only (`67fae23d...` -> `fffae23d...`), all other bindings lawful. Result at pre-launch, before record creation: `NEXUS_GOVERNED authority rejected before worker launch: Tracked Nexus execution grant bytes do not match grantSha256.` — the exact bad-grant hash-validation branch. Zero provider launch, zero durable worker (agent_list empty; durable store contains NO row for the negative attempt), zero workspace mutation. Not faked via attempt mismatch / stale HEAD / expiry / profile / task.

### G7-3 positive NEXUS_GOVERNED admission — ADMISSION PASS (provider result separate)
Same attemptKey `g7-governed-live-attempt-20260907-01` lawfully reused (negative left no trace; no ATTEMPT_REPLAY_CONFLICT). DevSpace independently fetched raw grant/card at revision `77f04b0b...` and verified bytes + all bindings -> admission returned `NEXUS_VALIDATED`. Durable agent **`agt_277a51c7`** (workspace `ws_1b3a1d377f`, isolated worktree `Nexus-new-25f3b41e` HEAD `491660f2a...`, profile `opencode-muse-high-review`, model `opencode/muse-spark-1.2-contributor-free` effort high, dispatch intentHash `e10f08fc...`). Provider result: `PROVIDER_PROTOCOL_ERROR` ("OpenCode did not finish the session before the provider timeout") amid a DevSpace server cutover/restart storm; `error_retryable=false`. Per Task Card Acceptance #7 this preserves admission-PASS evidence and MUST NOT mint provider-leg COMPLETE — recorded here without acceptance-conflation.

### G7-5 OWNER_DIRECT coexistence witness — ADMITTED (coexistence witnessed)
Independent attempt `g7-owner-direct-witness-20260907-01` (**`agt_6d4d7f1b`**), `authorityMode=OWNER_DIRECT` (no nexusGrant; OWNER_DIRECT+grant is rejected by construction), same workspace `ws_1b3a1d377f`, **started successfully while the governed attempt was still running** -> `NEXUS_GOVERNED` admission failure did not globally lock DevSpace; both lanes coexist. Provider result: same environmental `PROVIDER_PROTOCOL_ERROR` (restart storm), zero mutation.

### G7-6 no silent fallback — PASS
The governed attempt's failure stayed on the governed record (no OWNER_DIRECT downgrade of the governed attempt); the direct witness was an independently authorized separate attempt, not a fallback of G7-3. No fallback markers in either durable `lifecycle_state`. Governance lane separation preserved end-to-end.

### G7-7 physical reconciliation / no unexpected mutation — PASS
- Worktree `Nexus-new-25f3b41e`: `git status --porcelain` EMPTY, HEAD unchanged `491660f2a95eb04e68683e1648c2f9a20744a52a`.
- Durable lifecycle for BOTH agents: `cumulativeChangedPaths=[]`, `turnEndBaseline={"changedPaths":[],"head":"491660f2a...","fingerprints":{}}`.
- Canonical root `/Users/jameschen/Workspace/Nexus-new`: dirty set identical to pre-mutation baseline (untouched), HEAD `afd61883...` (local, never pushed).
- Exactly 2 durable agent rows exist for the workspace (governed + witness); the negative control left zero rows.

### Grant state after gates
Execution grant single-use attempt `g7-governed-live-attempt-20260907-01` consumed (durable attempt terminal, `error_retryable=false`); grant expires 2026-09-08T06:18:27Z. Any provider-leg retry requires a fresh Owner reissue via `scripts/ops/standing_grant.py` on the then-current main — no silent retry, no self-reissue, no hand-edit. Standing grant protected merges performed under this closure: PR #832 (`31c5c1eb...`) and this closure PR; receipt `a780bec2...` remains the durable merge-authority identity.
