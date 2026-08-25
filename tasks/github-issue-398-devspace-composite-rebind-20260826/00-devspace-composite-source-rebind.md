# TASK-398-DEVSPACE-COMPOSITE-SOURCE-REBIND

```yaml
task_id: TASK-398-DEVSPACE-COMPOSITE-SOURCE-REBIND
issue: 398
contract_repository: James3014/Nexus-new
contract_base: 3620db1947b6d9864eefe0555c4de9edbf6c7f6a
contract_base_tree: deeed8206e201cdc94f0c7a6e09f11815a84739d
source_repository: James3014/devspace
status: ACTIVE
execution_realm: SOURCE_ONLY_ISOLATED_WORKTREE
auto_chain: false
claim_mode: MANUAL_DISPATCH
claim_ceiling: DEVSPACE_COMPOSITE_SOURCE_CANDIDATE_ONLY
allowed_file_count: 15
host_effect_authority: NOT_GRANTED
runtime_effect_authority: NOT_GRANTED
```

## Purpose

Create one clean, immutable DevSpace source Candidate that combines the already
accepted G3 durable-termination implementation, its production provider
readiness-to-execution boundary, and the accepted Codex Goal coherent-screen
readiness implementation without importing unrelated Git history or modifying
the deployed dirty checkout.

This Card is a source-contract rebind only. It does not accept a new Candidate,
integrate the deployed branch, rebuild or reload DevSpace, touch ports, call a
provider, or close Issue #398.

## Superseded Issue identities

Issue #398 remains the Goal contract, but its physical body is stale. Its
deployed `2e2139a80c675da06f06e0b7dc63bae4a7608f4f`, Candidate
`8fcf11fbafcbcfc7740e761c91b7e185e0d3bf10`, and dirty adapter-pair identities
are historical evidence only for this source slice.

`Nexus-new` main `3620db1947b6d9864eefe0555c4de9edbf6c7f6a` / tree
`deeed8206e201cdc94f0c7a6e09f11815a84739d` is the current Issue/Card contract
plane. It is not DevSpace source ancestry.

## Exact DevSpace identities

Deployed local source, which must remain untouched during this Card:

- root: `/Users/jameschen/Workspace/devspace-chatgpt-mcp`
- branch: `james/agy-durable-dispatch-v1`
- HEAD: `13a8eb50c756e69d60c9deb3007ba6d71ee0978e`
- tree: `3b0aeb02b45dea7bb071b2b295026f2c6255a7b8`
- remote branch: `refs/heads/james/agy-durable-dispatch-v1` at exact
  `13a8eb50c756e69d60c9deb3007ba6d71ee0978e`
- dirty paths: `src/codex-goal-sessions.ts`,
  `src/codex-goal-sessions.test.ts`
- dirty binary diff SHA-256:
  `a34446d12345c92f2ca10a4464b9c3f83ca4dd62c45653d60940169eb6358944`
- dirty source SHA-256:
  `868d142e294c0decdf3ff3aa051d3cba5ccedc93c5db69988113ff8db2c9adc7`
- dirty test SHA-256:
  `9b3f8fc44380dd21cea13b98debb257c4d872144027a4227691606c9b650f72c`

The `e3b446a..13a8eb5` base movement is accepted current source, not Candidate
scope. It changes only `src/local-agent-adapters.ts` and its test by the linked
worktree Git-metadata containment fix, 42 insertions and 11 deletions. The
replacement Candidate must preserve that base behavior.

Current DevSpace collaboration main observed before Card creation:

- `James3014/devspace` main:
  `fdbff75e07779bba1f2fdc785a2575e2b0d839bc`
- tree: `919d36945b70b5a746d48d1f05c2bb5306c0b487`

Accepted source inputs:

- G3 commit: `d009c5c0229a403a18b9e4a5846bc0c4476f1420`
- G3 tree: `48eda028145a92a365f914b2d24e04de4d8925c2`
- G3 base: `d3145f0fca3f806888884767e623482f5aa45ac6`
- G3 eight-file binary diff SHA-256:
  `cf925689e11dcaed88944767410a1efbfdb0d750e1f3f5613afa1cdc46b5b140`
- Goal commit: `147359ae75874446e33083696127dcc94eddef85`
- Goal tree: `faaf87b9e82e52dbb0673bbc15086add6945bc2b`
- Goal accepted base: `d009c5c0229a403a18b9e4a5846bc0c4476f1420`
- Goal two-file binary diff SHA-256:
  `5caa7e6f3be7f9cdb17fc709e146e859b609ce89719715b700e3a7aec99f7cfc`

Direct fast-forward or merge of `147359` is forbidden. The range
`e3b446a..147359` changes 94 files, adds 18,833 lines, removes 2,403 lines,
deletes `skills/subagent-delegation/SKILL.md`, and has binary diff SHA-256
`b90f359c724d04bddaba7ecbbc8c5ea7b743ffc2bcc4b06ecb02c384c8e66d6b`.
That range is outside this Card.

The earlier semantic-port Candidates `23d66c9a58ba367fc31cf2509471a5faf66d5667`
and `6ba60417791c096298cea58a878457d6d0134395` are `REVISE` oracle evidence.
They are not accepted, not eligible for integration, and must not be
cherry-picked. The latter also violates the direct-parent contract because its
direct parent is `23d66c9`, not the current deployment base.

## Bounded semantic port

Create one clean isolated DevSpace worktree with parent exactly
`13a8eb50c756e69d60c9deb3007ba6d71ee0978e`. Port the already accepted G3
behavior to the APIs physically present at `13a8eb5`; do not transplant G3 Git
history or require byte equality with the `d009` blobs.

The durable lifecycle port remains limited to these eight G3 paths:

- `src/local-agent-contract.ts`
- `src/local-agent-execution-contract.test.ts`
- `src/local-agent-sessions.test.ts`
- `src/local-agent-sessions.ts`
- `src/local-agent-store.test.ts`
- `src/local-agent-store.ts`
- `src/server.test.ts`
- `src/server.ts`

The production readiness-to-execution seam adds exactly these five paths:

- `src/local-agent-runtime.ts`
- `src/local-agent-runtime.test.ts`
- `src/local-agent-adapters.ts`
- `src/local-agent-adapters.test.ts`
- `src/local-agent-omp.ts`

It must preserve the accepted G3 invariants: one detached-worker lifecycle
owner; an opaque generation and launch state; durable `terminationPending`;
PID/token identity retained until verified physical absence and end evidence;
generation/token/PID-bound compare-and-swap mutations; first-fence-wins;
pending and corrupt states remain nonterminal and capacity-occupying; legacy
runtime-pool compatibility; reopen, launch-gap, stale-callback, retry/backoff,
post-kill baseline, truthful pending-versus-blocked status, and atomic legacy
generic updates under `IMMEDIATE` plus exact row compare-and-swap.

`LocalAgentRunCallbacks` must cross the production runtime/adapter boundary.
Execution start is generation-fenced and invoked exactly once:

- Driver/Codex: after runtime creation/readiness and immediately before the
  semantic provider run;
- OMP: after initialize plus session creation/resume and immediately before
  `session.prompt`;
- Agy: after executable/environment/workspace and linked-worktree metadata
  containment have been resolved into the complete argument vector, and
  immediately before the single child spawn.

Callback/CAS rejection emits zero provider prompt/run and zero Agy child. Slow
runtime or OMP readiness consumes startup budget, not execution budget.

The accepted `13a8eb5` linked-worktree containment must remain effective while
adding callbacks: `resolveAgyGitMetadataDirs` uses the worktree-scoped
`git rev-parse --git-dir`; any external add-dir is the canonical
`<common>/.git/worktrees/<name>` for a verified member worktree; repo-common
`.git` is never exported; main-worktree in-root Git metadata adds no external
directory; canonicalization, membership validation, environment scrubbing,
cwd, workspace add-dir, mode/model/effort/output/timeout, and prompt arguments
remain unchanged.

The two Goal paths port the accepted `147359` coherent-screen behavior to the
destructive-delta `ProcessSnapshot` contract physically present at `13a8eb5`:

- each non-truncated snapshot is ordered novel output bytes, not a cumulative
  prefix and not a replay deduplication key;
- an incomplete ANSI-stripped line tail is retained across snapshots;
- model, directory, and input-ready prompt must form one current coherent
  screen in order;
- loading/error/unavailable/unknown/none/empty, trust prompts, later identity
  regressions, and explicit requested-model/workspace mismatches fail closed;
- truncation or sequence uncertainty permanently blocks readiness;
- empty polls do not replay history, while identical text received twice as
  two real output chunks must be consumed twice;
- no prefix heuristic, global process-manager change, or server monkeypatch is
  permitted.

The accepted `147359` commit/tree and tests remain behavioral oracle evidence,
not a byte requirement for this transport port. The new Goal bytes require
fresh SHA/tree-bound acceptance.

Every other tree entry must remain byte-identical to `13a8eb5`. In particular:

- `package.json` remains blob `cbf7ce9cbf2fcbd0c5b9c5b2602b28c2f623e51b`;
- `package-lock.json` remains blob `ab051a2b3ee3278a93bcb754761baecc711fb861`;
- no new bare-package import is allowed;
- every relative import from changed production files must resolve within the
  unchanged `13a8eb5` source tree;
- final scope is exactly the fifteen paths above, with no deletion or untracked
  file.

The initial exact-blob oracle is preserved as failure evidence: exact `d009`
`local-agent-store.ts` imports absent `better-result`, and the recursive `d009`
closure also requires source modules not present at `13a8eb5`. Copying all
`d009` package/source prerequisites would recreate the forbidden broad history
import. Do not add `better-result`, change package metadata, add dependency
files, use network materialization, or alter tool/product surfaces.

The first semantic-port oracle is also preserved: exact `147359` Goal blobs
require cumulative process snapshots, while `13a8eb5` emits destructive deltas.
Do not add `src/process-sessions.ts` or its test. The later process blob also
introduces replay, status, timeout, retention, TTL, and cleanup behavior beyond
this Goal adapter and is not authorized by this Card.

If the accepted G3 invariants and the production callback boundary cannot be
implemented inside these thirteen G3/provider paths against `13a8eb5`, stop
with `ALLOWED_SCOPE_INSUFFICIENT / CONTRACT_GAP`.
Compatibility edits inside the fifteen paths are a new composite Candidate and
must receive fresh independent acceptance; `d009` acceptance is oracle input,
not acceptance of the ported bytes.

## Verification

Before commit:

1. Re-read deployed/remote HEAD/tree, dirty paths, and all three dirty hashes
   above.
2. Verify the isolated parent is exactly `13a8eb5` and the worktree was clean
   before implementation.
3. Verify package/package-lock blob identities remain exact `13a8eb5` and
   verify `src/process-sessions.ts` remains blob
   `4424d24b4342e661b8f2253083cfd0062e66e79a`.
4. Run a dependency-denial check proving every relative production import
   resolves and no changed production file adds a bare-package import.
5. Verify `git diff --name-only 13a8eb5` is exactly the fifteen allowed paths,
   with no deletion or untracked file.
6. Verify `skills/subagent-delegation/SKILL.md` and every other unrelated
   `13a8eb5` blob remain unchanged.
7. Run:

```bash
TMPDIR=/private/tmp npx tsx src/local-agent-execution-contract.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-sessions.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-continuation.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-store.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-runtime.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-adapters.test.ts
TMPDIR=/private/tmp npx tsx src/server.test.ts
TMPDIR=/private/tmp npx tsx src/codex-goal-sessions.test.ts
TMPDIR=/private/tmp npm test
npm run build
npx tsc -p tsconfig.json --noEmit
npx tsc -p tsconfig.build.json --noEmit
git diff --check 13a8eb50c756e69d60c9deb3007ba6d71ee0978e
```

The expected historical counts (G3 execution 71, sessions 13, continuation 8,
server 24, Goal 44) are evidence references, not reasons to weaken current
assertions or to claim a command passed without execution.

The Goal suite must retain all prior `147359` positive and negative controls
and add destructive-snapshot cases for multi-snapshot readiness, arbitrary
label fragmentation, empty polls, identical real chunks, historical ready rows
followed by loading/error, trust after readiness, truncation fail-closed, no
`/goal` bytes on every negative, and zero active-session leak.

Production-boundary tests must exercise real adapter/OMP seams rather than
only injected runners or manual store transitions:

- Driver/Codex runtime readiness precedes execution start, which precedes run;
- OMP initialize and session new/resume precede execution start, which precedes
  prompt;
- callback rejection and stale-generation rejection produce zero semantic
  prompt/run/child;
- slow readiness consumes startup rather than execution budget;
- linked-worktree Agy containment remains exact on callback success, while a
  rejected callback spawns no child and never exports repo-common `.git`;
- main-worktree, forged/unowned/out-of-tree, and symlink/canonical path
  controls remain fail-closed.

## Candidate and review gate

Commit one immutable Candidate whose single direct parent is exactly
`13a8eb50c756e69d60c9deb3007ba6d71ee0978e`.
Record Candidate commit/tree, fifteen-path diff hash, command/cwd/exit evidence,
dependency-denial evidence, and final clean worktree state. Obtain a fresh
independent SHA/tree-bound acceptance. The prior `d009` and `147359`
acceptances are input evidence only; they do not accept the new composite tree.

Only after independent acceptance may the coordinator update Issue #398 once
to bind the exact composite parent/head/tree/diff/scope/acceptance. Canonical
DevSpace integration, dirty-file disposition, build/reload, MCP discovery, E2E,
and runtime claims remain separate authority/effect gates.

## Forbidden effects

- no mutation of `/Users/jameschen/Workspace/devspace-chatgpt-mcp`;
- no reset, stash, clean, overwrite, or deletion of dirty bytes;
- no 94-file history import, merge, rebase, or cherry-pick;
- no path outside the fifteen allowed paths;
- no package/lock/dependency addition and no network dependency materialization;
- no dependency install outside the isolated worktree;
- no push, PR, Issue writeback, branch integration, build installation, reload,
  listener, provider, OAuth, Gateway, DevSpace runtime, or port effect;
- no self-acceptance or production/readiness claim.

## Stop result

Success claim ceiling:

`DEVSPACE_COMPOSITE_SOURCE_CANDIDATE_VERIFIED_NOT_ACCEPTED_NOT_INTEGRATED`

Failure claim ceiling:

`DEVSPACE_COMPOSITE_SEMANTIC_PORT_SCOPE_INSUFFICIENT`
