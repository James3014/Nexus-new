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
allowed_file_count: 10
host_effect_authority: NOT_GRANTED
runtime_effect_authority: NOT_GRANTED
```

## Purpose

Create one clean, immutable DevSpace source Candidate that combines the already
accepted G3 durable-termination implementation and the already accepted Codex
Goal coherent-screen readiness implementation without importing unrelated Git
history or modifying the deployed dirty checkout.

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
- HEAD: `e3b446a7507491b653d932284a09dc0923652c3d`
- tree: `325f5e2de1d21381b083d0239011a9f869c772f1`
- dirty paths: `src/codex-goal-sessions.ts`,
  `src/codex-goal-sessions.test.ts`
- dirty binary diff SHA-256:
  `a34446d12345c92f2ca10a4464b9c3f83ca4dd62c45653d60940169eb6358944`
- dirty source SHA-256:
  `868d142e294c0decdf3ff3aa051d3cba5ccedc93c5db69988113ff8db2c9adc7`
- dirty test SHA-256:
  `9b3f8fc44380dd21cea13b98debb257c4d872144027a4227691606c9b650f72c`

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

## Exact content transplant

Create one clean isolated DevSpace worktree with parent exactly
`e3b446a7507491b653d932284a09dc0923652c3d`. Materialize only the ten exact
tracked blobs below. This is a content transplant, not a merge, cherry-pick,
rebase, or history import.

| Source | Path | Mode | Blob OID | SHA-256 |
|---|---|---|---|---|
| `d009c5c` | `src/local-agent-contract.ts` | `100644` | `f054d268055b06efc8a1756123b991ac56d81588` | `ebbd6b86ebeefac6a7eb3525c13ddf5adc9284ad5d1cc1dca36def8d0c56b982` |
| `d009c5c` | `src/local-agent-execution-contract.test.ts` | `100644` | `c1120e60d543bc0cc6c8539a8be03b84e795c54a` | `9f02039a5a07f65026ae8e232378fc9c1b9248290bd08f2af0b21a5e723c7f8b` |
| `d009c5c` | `src/local-agent-sessions.test.ts` | `100644` | `ae00c00964ae16e72591027eb461f3b7533693bf` | `8cd0c9986814c091332b4eea5ca9f3a0e71b6ac0ff9f1447651a6297d5af40b8` |
| `d009c5c` | `src/local-agent-sessions.ts` | `100644` | `af7b114e9def663ec969721435c42e12fd957fa0` | `8ff52ff2d30702097341ec0b26cdfcd8f06de1ee03842b3533aa2adabef979f7` |
| `d009c5c` | `src/local-agent-store.test.ts` | `100644` | `479e7baf01cb4a0d017f2b94ebfb704832579760` | `51927410a2e6f41412519b803c4bba9ea0a0b21074c237ead320a34bd90f2369` |
| `d009c5c` | `src/local-agent-store.ts` | `100644` | `2dadf32d2c1b5195ea821129fb5b8b4ae73dcec8` | `11dbd450483d84fd79d1fb0d1a4d6338b1b1f6bd8eb9c909f50b33eefa7c9534` |
| `d009c5c` | `src/server.test.ts` | `100644` | `56aa075772fc9121d59fbdd6cbc496b2f8bc7f8f` | `01b81514ca94446a6a06e131947f9a14673d4b786fed56ee2d91ac7cac86e7c8` |
| `d009c5c` | `src/server.ts` | `100644` | `765c01ad14a5c03183eaf46788498a2ca3f87c7c` | `e8f3c5ebe10cf927c3d35fc6fb47a23b7dcf35ea788c4f015e3fdb6de61989e4` |
| `147359a` | `src/codex-goal-sessions.test.ts` | `100644` | `b7adad626fdd5f9bcf4fb315417ac5e49ed69b6d` | `8f261ae6004f8f06e61b996b4ed4f83c5f094704d7e8566307b82ac0c570f982` |
| `147359a` | `src/codex-goal-sessions.ts` | `100644` | `7a028663b20de87c2cac3d9728de72364841bee4` | `33d20560627f22c15037e2a69ca0e672e89f4651ab5b3f3db3d4eb5e1cb5503f` |

Every other tree entry must remain byte-identical to `e3b446a`. Final scope is
exactly these ten paths, with no deletion or untracked file.

## Compatibility oracle

The exact `d314..d009` patch does not mechanically apply to `e3b446a`: six of
the eight G3 files conflict. Therefore this Card permits only the exact-blob
transplant as the first fail-closed oracle.

If the ten exact blobs do not compile and pass the required tests on the
`e3b446a` parent, stop with `ALLOWED_SCOPE_INSUFFICIENT / CONTRACT_GAP`.
Do not import `d314` ancestry, add compatibility edits, widen paths, or weaken
tests under this Card. A semantic port requires a separately frozen Card and a
new independent acceptance.

## Verification

Before commit:

1. Re-read deployed HEAD/tree/dirty paths and all three dirty hashes above.
2. Verify the isolated parent is exactly `e3b446a` and the worktree was clean
   before transplant.
3. Verify all ten modes/blob OIDs/SHA-256 values against the table.
4. Verify `git diff --name-only e3b446a` is exactly the ten allowed paths,
   with no deletion or untracked file.
5. Verify `skills/subagent-delegation/SKILL.md` and every other unrelated
   `e3b446a` blob remain unchanged.
6. Run:

```bash
TMPDIR=/private/tmp npx tsx src/local-agent-execution-contract.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-sessions.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-continuation.test.ts
TMPDIR=/private/tmp npx tsx src/local-agent-store.test.ts
TMPDIR=/private/tmp npx tsx src/server.test.ts
TMPDIR=/private/tmp npx tsx src/codex-goal-sessions.test.ts
TMPDIR=/private/tmp npm test
npm run build
npx tsc -p tsconfig.json --noEmit
npx tsc -p tsconfig.build.json --noEmit
git diff --check e3b446a7507491b653d932284a09dc0923652c3d
```

The expected historical counts (G3 execution 71, sessions 13, continuation 8,
server 24, Goal 44) are evidence references, not reasons to weaken current
assertions or to claim a command passed without execution.

## Candidate and review gate

Commit one immutable Candidate whose single parent is exactly `e3b446a`.
Record Candidate commit/tree, ten-path diff hash, command/cwd/exit evidence,
and final clean worktree state. Obtain a fresh independent SHA/tree-bound
acceptance. The prior `d009` and `147359` acceptances are input evidence only;
they do not accept the new composite tree.

Only after independent acceptance may the coordinator update Issue #398 once
to bind the exact composite parent/head/tree/diff/scope/acceptance. Canonical
DevSpace integration, dirty-file disposition, build/reload, MCP discovery, E2E,
and runtime claims remain separate authority/effect gates.

## Forbidden effects

- no mutation of `/Users/jameschen/Workspace/devspace-chatgpt-mcp`;
- no reset, stash, clean, overwrite, or deletion of dirty bytes;
- no 94-file history import, merge, rebase, or cherry-pick;
- no path outside the ten exact paths;
- no dependency install outside the isolated worktree;
- no push, PR, Issue writeback, branch integration, build installation, reload,
  listener, provider, OAuth, Gateway, DevSpace runtime, or port effect;
- no self-acceptance or production/readiness claim.

## Stop result

Success claim ceiling:

`DEVSPACE_COMPOSITE_SOURCE_CANDIDATE_VERIFIED_NOT_ACCEPTED_NOT_INTEGRATED`

Failure claim ceiling:

`DEVSPACE_COMPOSITE_EXACT_BLOBS_INCOMPATIBLE_WITH_E3B_SCOPE_INSUFFICIENT`
