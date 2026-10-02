# TASK-398-DEVSPACE-CURRENT-BASE-COMPOSITION

```yaml
task_id: TASK-398-DEVSPACE-CURRENT-BASE-COMPOSITION
issue: 398
contract_repository: James3014/Nexus-new
contract_base: 6fe26c9a998d79f5f3b2484ff7236ab517318e57
contract_base_tree: f77a784b55fb9d9e427e7bdb02347ccd1aedfeae
source_repository: James3014/devspace
status: ACTIVE
execution_realm: SOURCE_ONLY_ISOLATED_WORKTREE
auto_chain: false
claim_mode: MANUAL_DISPATCH
claim_ceiling: DEVSPACE_CURRENT_BASE_COMPOSITION_CANDIDATE_ONLY
allowed_file_count: 15
host_effect_authority: NOT_GRANTED
runtime_effect_authority: NOT_GRANTED
```

## Purpose and authority

Compose the independently accepted Issue #398 fifteen-path source behavior onto
the clean current local DevSpace source while retaining every later local
behavior. Produce one immutable source Candidate in a new isolated worktree.

The Ready Issue #398 Goal is unchanged. The prior Card under
`tasks/github-issue-398-devspace-composite-rebind-20260826/` is consumed source
evidence: it accepted the exact input below, pinned source parent `13a8eb5`, and
stopped before canonical integration. This successor is a current-base contract
delta under the active Owner standing coordinator grant and the Owner's exact
2026-08-26 action-time authorization.

This Card does not mutate the canonical DevSpace checkout, move its branch,
push DevSpace refs, install a build, reload a service, call a provider, prove
runtime behavior, merge this Card PR, or close Issue #398.

The accepted-source Issue writeback is GitHub comment `5423768340`. It records
source acceptance only and grants no integration or runtime effect.

## Exact contract-plane identity

- Nexus-new main: `6fe26c9a998d79f5f3b2484ff7236ab517318e57`
- Nexus-new main tree: `f77a784b55fb9d9e427e7bdb02347ccd1aedfeae`
- standing grant: `OWNER_STANDING_COORDINATOR_20260818_DURABLE_GITHUB_WORKFLOW`
- grant receipt hash:
  `3b8895f093692257d6225fbb8150b34f520e667d250c7817ad120cefd42751d5`
- grant file SHA-256:
  `d173f8c99ba72af21522691ac8bb646effea0acbdd7886405bc24e35fd167a92`

Any contract-base, Issue, Card, INDEX, grant expiry/revocation, or main movement
requires a fresh contract-plane rebind before dispatch.

## Exact DevSpace identities

Clean current local source base:

- root: `/Users/jameschen/Workspace/devspace-chatgpt-mcp`
- branch: `james/agy-durable-dispatch-v1`
- HEAD: `18f6ab363482dafe30f3dc5632a612fa73779db5`
- tree: `f15063defde193d55e4aee37456eb2bb45b8c2fc`
- status: clean
- remote `james/agy-durable-dispatch-v1`:
  `13a8eb50c756e69d60c9deb3007ba6d71ee0978e`

The local base is exactly three commits ahead of that remote:

1. `e8489a8421edcdad450f41789220af8d1f317ec8` - delayed Codex TUI readiness;
2. `70bc7e566630fb8014a2339b5f7878fad7a4bb6f` - frozen terminal lifecycle timing;
3. `18f6ab363482dafe30f3dc5632a612fa73779db5` - bounded Agy isolation from global MCP config.

Accepted source input:

- commit: `257dc24ac79e9a05a52966c5d7c940e753f31f71`
- tree: `e71730a229ef77eee3c2984190829e01bb687fe4`
- direct parent and merge base:
  `13a8eb50c756e69d60c9deb3007ba6d71ee0978e`
- binary diff SHA-256:
  `ad9b0ed0d44b9f8bd671ec95d166b2cf1cc978722b038c3d119edd9652f8bf0c`
- independent acceptance: exact SHA/tree ACCEPT from Sol-B/XA1 and Sol-C/XA2;
- verification: Goal 61/61, full `npm test` rc0, both no-emit
  typechecks rc0, build rc0, diff-check PASS, clean worktree.

Do not merge, rebase, or cherry-pick the accepted branch history. The accepted
tree is semantic oracle input for a new direct-child composition Candidate.

## Exact mutation scope

Only these fifteen paths may change in the isolated composition:

1. `src/codex-goal-sessions.test.ts`
2. `src/codex-goal-sessions.ts`
3. `src/local-agent-adapters.test.ts`
4. `src/local-agent-adapters.ts`
5. `src/local-agent-contract.ts`
6. `src/local-agent-execution-contract.test.ts`
7. `src/local-agent-omp.ts`
8. `src/local-agent-runtime.test.ts`
9. `src/local-agent-runtime.ts`
10. `src/local-agent-sessions.test.ts`
11. `src/local-agent-sessions.ts`
12. `src/local-agent-store.test.ts`
13. `src/local-agent-store.ts`
14. `src/server.test.ts`
15. `src/server.ts`

No deletion or untracked source file is allowed. Every path outside this list
must remain byte-identical to local base `18f6ab3`.

Protected inherited sentinel:

- `src/local-agent-continuation.test.ts` remains exact local-base blob
  `086e4d80518b51c44e61b03c0be10aeadb3dff5b` and is executed as a verifier.

Other mandatory sentinels:

- `package.json` blob `cbf7ce9cbf2fcbd0c5b9c5b2602b28c2f623e51b`;
- `package-lock.json` blob `ab051a2b3ee3278a93bcb754761baecc711fb861`;
- `src/process-sessions.ts` blob
  `4424d24b4342e661b8f2253083cfd0062e66e79a`;
- `skills/subagent-delegation/SKILL.md` remains byte-identical to `18f6ab3`.

If correct composition requires a sixteenth path, package/dependency change,
ProcessSession change, or sentinel edit, stop with
`ALLOWED_SCOPE_INSUFFICIENT / CONTRACT_GAP`.

## Physical overlap

The accepted input and local base share merge base exact `13a8eb5`.
`git merge-tree` reports textual conflicts in exactly:

1. `src/codex-goal-sessions.ts`;
2. `src/codex-goal-sessions.test.ts`;
3. `src/local-agent-adapters.test.ts`.

These overlapping paths auto-merge textually but still require semantic review:

- `src/local-agent-adapters.ts`;
- `src/local-agent-execution-contract.test.ts`;
- `src/local-agent-sessions.ts`.

Merge-tree output is conflict evidence only. A clean textual merge is not
acceptance and cannot select semantics or authority.

## Composition invariants

### Goal source and test

- `DestructiveDeltaReadiness` is the sole readiness decision owner. Do not
  retain `e8489` readiness booleans or another parser as a parallel gate.
- Preserve current-base delayed-TUI behavior: no `/goal` while loading;
  requested model resolution, exact workspace directory, exact prompt,
  TTY/PWD/sentinel checks, and delayed readiness remain observable.
- Preserve accepted destructive-delta behavior: exact prompt, monotonic
  model/directory/prompt order, streaming raw ANSI carry, final clear epoch,
  every `ESC[2J`, `ESC[3J`, and `ESC c` split boundary, truncation/trust/
  loading/error/mismatch denial, duplicate real chunks, empty polls, cleanup,
  zero `/goal`, and no active-session leak.
- Every absorption remains workspace-root bound. No server or ProcessSession
  workaround is allowed.

### Agy adapter source and test

- Combine both harnesses. Preserve `readFileSync`, `existsSync`, spawn-count
  logging, owned scratch cleanup, ambient MCP sentinel, and linked-worktree
  controls.
- Preserve current-base isolated `HOME`, `USERPROFILE`, XDG roots, owned
  provider scratch, narrow token/conversation links, and zero ambient global
  MCP config mutation or exposure.
- Preserve exact `13a` linked-worktree Git metadata containment: worktree-scoped
  git-dir only, verified membership, never repo-common `.git`.
- Preserve accepted callback placement after executable/env/workspace/git/argv
  resolution and immediately before the single semantic child spawn.
- `--version` preflight is not a semantic spawn. Callback rejection causes zero
  semantic spawn and no ambient config mutation.

### Session, lifecycle, and execution tests

- Preserve current-base terminal presentation-time freeze: terminal wall time
  uses persisted `updatedAt`, terminal `idleMs` is zero, and only active rows
  use `Date.now()`.
- Presentation timing is not a second lifecycle, termination, or budget owner.
- Preserve accepted generation/PID/token/launch/termination CAS, provider
  session binding, callback-before-semantic-effect denial, startup/execution/
  wall budgets, pending/corrupt/blocked capacity, cleanup, settlement, retry,
  and cross-process generic-update CAS behavior.
- Retain both current-base timing/restart witnesses and accepted callback,
  lifecycle, and budget tests. Do not delete or weaken assertions.

### Remaining paths

Port accepted `257dc24` behavior against the `18f6ab3` APIs. Do not add a
second manager, callback owner, readiness gate, lifecycle state, provider/model
selector, route, receipt, or process authority.

## Procedure and verification

1. Re-read exact local base HEAD/tree/status and accepted input commit/tree.
2. Create a clean isolated worktree whose parent is exact `18f6ab3`.
3. Apply only the accepted semantic delta under the invariants above. Never
   mutate the canonical checkout.
4. Verify exact scope, sentinels, relative imports, no new bare-package import,
   no deletion, and no untracked file.
5. Run all checks below.
6. Commit exactly one immutable Candidate whose single direct parent is exact
   `18f6ab3`; record commit/tree/binary diff hash and clean state.
7. Obtain fresh independent SHA/tree/base/diff acceptance. Accepted `257dc24`
   is oracle evidence only and does not accept the new tree.
8. Stop before canonical integration or runtime effects.

```bash
TMPDIR=/private/tmp npx tsx src/codex-goal-sessions.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-execution-contract.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-sessions.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-continuation.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-store.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-runtime.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-adapters.test.ts
TMPDIR=/private/tmp npx tsx src/server.test.ts
TMPDIR=/private/tmp npm test
npm run build
npx tsc -p tsconfig.json --noEmit
npx tsc -p tsconfig.build.json --noEmit
git diff --check 18f6ab363482dafe30f3dc5632a612fa73779db5
```

Also prove exact path/deletion/untracked/sentinel/import closure and explicitly
execute delayed readiness, terminal timing, Agy isolation, ambient MCP denial,
linked-worktree containment, callback, Goal, lifecycle, and continuation
controls. Tooling transport failure is not PASS.

Any Candidate-attributable failure is `REVISE`. Any path or semantic widening
is `CONTRACT_GAP`.

## Forbidden effects

- no mutation of `/Users/jameschen/Workspace/devspace-chatgpt-mcp`;
- no reset, stash, clean, overwrite, branch movement, or conflict state there;
- no merge, rebase, cherry-pick, or broad history import;
- no path outside the exact fifteen-path maximum;
- no edit to the protected continuation test or other sentinels;
- no package/dependency/ProcessSession/route/provider/model/tool expansion;
- no DevSpace push, canonical integration, installation, reload, listener,
  OAuth, provider call, E2E, runtime, production, or Issue closure;
- no worker self-acceptance or automatic downstream chain.

## Exit result

Success claim ceiling:

`DEVSPACE_CURRENT_BASE_COMPOSITION_CANDIDATE_VERIFIED_NOT_ACCEPTED_NOT_INTEGRATED`

`AUTO_CHAIN=false`.
