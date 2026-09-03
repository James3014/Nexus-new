# TASK-G20-R1-SOURCE-CONTRACT-DELTA

```yaml
task_id: TASK-G20-R1-SOURCE-CONTRACT-DELTA
issue: 526
repository: James3014/Nexus-new
status: ACTIVE
source_spec: docs/specs/g20-r1-complete-deployment-source-contract-delta-20260903.md
source_spec_sha256: 5b88f83c2a6557e49348200bf9224fee20ccc2f06b4e84132aa0897517d367af
source_requirements:
  - REQ-001
  - REQ-002
  - REQ-003
  - REQ-004
source_acceptance:
  - AC-001
  - AC-002
  - AC-003
  - AC-004
base_main: 1583a729cf611df0dc807a1f1b2458c8edff0359
base_tree: ae49701e33da46fdfd1dab9b031331f2f80e6ac9
execution_realm: SOURCE_ONLY
execution_lane: GOVERNED
execution_transport: EXTERNAL_BOOTSTRAP_RECOVERY
slicing_strategy: TRACER_BULLET
auto_chain: false
claim_mode: MANUAL_DISPATCH
claim_ceiling: R1_SOURCE_CANDIDATE_ONLY
commit_required: true
candidate_required: true
independent_acceptance_required: true
allowed_file_count: 4
allowed_files:
  - nexus/contracts/gateway_deployment.py
  - scripts/ops/mcp_gateway_durable.py
  - tests/contracts/test_gateway_deployment_contract.py
  - tests/ops/test_mcp_gateway_durable.py
```

## Objective

Implement the smallest source-only R1 successor contract that removes two deterministic false blockers without weakening the existing fixed-manager/fail-closed authority boundary:

1. exact-tree-bound Gitlinks are accepted only as inert superproject metadata and are never recursively fetched/materialized/trusted/executed;
2. the exact rollback predecessor may be outside fresh-main ancestry only when reconstructed from a fixed manager-owned, successor-authority-bound, self-contained immutable Git artifact;
3. the changed Card/manager/artifact binding requires successor recovery authority/request/fence/op and cannot repurpose the failed R2 operation.

This card authorizes one committed source Candidate only. The loaded ChatGPT-facing Gateway remains bound to the stale `0045673...` source realm and cannot prove current-card/current-main mutation identity for this self-hosting repair. Under the current `docs/governance/rollback_runbook.md` External bootstrap recovery boundary, implementation may therefore use this exact clean isolated worktree through DevSpace as recovery transport only: exact base, bounded files, frozen Candidate, affected positive/negative/tamper/regression checks, and independent review. This creates no second Planner, lifecycle, approval, integration, or runtime authority. It authorizes no Gateway/LaunchAgent/process/OAuth/DevSpace recovery effect, no successor receipt issuance, no merge/integration, no cleanup of old recovery evidence, and no G21 work.

### Coordinator authority correction

A prior implementer attempt timed out after editing this Card itself. That self-edit is non-authoritative and is superseded by these coordinator-written bytes. The external-bootstrap transport decision above is independently re-derived from the current root `AGENTS.md` and `docs/governance/rollback_runbook.md`; the implementer is not allowed to modify this Card again.

## Governing baseline and supersession

The existing `TASK-526-R1-DURABLE-DEPLOYMENT-RECONCILIATION` remains historical/current baseline evidence. This card supersedes only:

- blanket mode-`160000` rejection;
- the requirement that the rollback predecessor itself be a fresh-main ancestor/source-mirror resident;
- any interpretation that changed Card/manager semantics may reuse the prior recovery authority/request/fence/op.

All other R1 constraints remain binding: fixed manager/process owner, fixed service/endpoint, caller cannot choose root/ref/path/label/PID/command/environment/network/follow-main, exact desired/rollback bytes before effect, strict ownership/mode/symlink/alternates/object verification, CAS/idempotency, zero-effect preflight failure, durable ledger/reconciliation, and independent acceptance.

The worker must read the root `AGENTS.md`, `docs/agents/TASK_EXECUTION_CONTRACT.md`, this card, the source spec, the old Task 09 sections relevant to R1-B source staging, and only the four allowed implementation/test files needed for the task.

## Required implementation contract

### A. Gitlink semantics

Replace `_r1_reject_gitlinks()` as a blanket admission rule with exact-tree-bound inert Gitlink verification.

- Do not create a path allowlist for the currently observed six Gitlinks.
- Exact superproject commit/tree identity already binds Gitlink path and OID.
- No R1 path may invoke `git submodule init`, `git submodule update`, recursive clone/fetch, or resolve Gitlink target content as recovery source authority.
- After detached worktree materialization, enumerate mode `160000` entries from the exact commit in the manager-owned bare store and verify each corresponding deployment path is either absent or an empty ordinary directory.
- Reject symlink, file, non-empty directory, nested `.git`, or any populated/substituted content at a Gitlink path before the deployment can be considered verified.
- Do not inspect or execute the Gitlink target repository.

### B. Predecessor reconstruction artifact

Preserve accepted/desired source authority in the fixed fresh-main mirror. Only the predecessor gets the new source path.

Introduce the minimum strict recovery-authority fields needed to bind the predecessor artifact. Preferred semantic shape:

- successor recovery authority schema/version distinct from the prior executable R2 authority;
- artifact format fixed to self-contained Git bundle;
- exact `predecessor_artifact_sha256`;
- exact positive `predecessor_artifact_size`;
- exact predecessor commit/tree remain the existing semantic authority;
- manager-derived artifact path under a fixed Gateway state subdirectory; no caller path/ref field;
- artifact retention is fail-closed: the manager never deletes it in this task and missing artifact blocks recovery; cleanup remains separately authorized later.

The artifact hash/size are recovery-authority/provenance bindings but SHALL NOT enter `RecoverySourceSet`, `DeploymentManifest`, or deployment ID semantic identity. Different valid transport encodings of the same exact predecessor may therefore have different artifact hashes while the semantic deployment identity stays stable.

Before deriving the predecessor source identity or promoting any worktree, the manager must:

1. lstat the fixed artifact path and require regular non-symlink file, expected owner/gid, mode `0600`, exact byte size and SHA-256 from the successor receipt;
2. verify it as a self-contained Git bundle against an empty temporary bare repository so prerequisite-dependent/incremental bundles fail closed;
3. require exactly one fixed predecessor role/ref and exact receipt predecessor commit;
4. import/fetch it only into a manager-owned temporary/bare source store, then run strict object verification/fsck;
5. recompute exact predecessor tree and fixed entrypoint blob/hash/mode from those imported bytes and compare them to the receipt/source-set values;
6. combine only that verified predecessor object source with accepted/desired objects obtained from the fixed authority mirror when building the existing combined recovery bundle/bare store.

No network fallback, arbitrary preservation ref, canonical dirty checkout, disposable worktree, caller path, or follow-main source may satisfy a missing/tampered predecessor artifact.

### C. Recovery authority supersession

The implementation must make the changed contract cryptographically non-interchangeable with the old R2 authority.

- Bind this new Task Card SHA through `RECOVERY_CARD_PATH` / `RECOVERY_CARD_SHA256` or the equivalent canonical contract seam.
- New executable recovery authority must carry the artifact binding above and a new schema/version or otherwise an unambiguous incompatible contract identity.
- Existing v1/R2 bytes may remain parseable as historical evidence if useful, but `validate_recovery_authority()` for the changed recovery path must reject them as execution authority.
- Do not edit the old tracked receipt, old ledger, request/fence, or `op_617dd8acf9f031b2`.
- Do not create the successor receipt/request/fence/op in this Candidate; that belongs to the post-acceptance recovery Gate.

## TDD and required witnesses

Use RED-first for the new behaviors and record the actual RED commands/results in the implementer report before implementation. Do not manufacture RED history.

At minimum add tests proving:

1. a real temporary superproject commit/tree containing a mode-`160000` Gitlink can pass source preparation/staging when the Gitlink path stays absent/empty;
2. no tested manager Git command invokes `submodule` or a recursive Gitlink fetch/materialization path;
3. after staging, a populated Gitlink path, nested `.git`, file, or symlink substitution causes `_r1_verify_worktree`/equivalent to fail closed;
4. accepted+desired remain sourced from the fresh-main mirror while predecessor is deliberately created on a side branch not reachable from mirror `main`;
5. a self-contained fixed predecessor artifact reconstructs that side-branch predecessor and yields exact commit/tree/entrypoint identity;
6. missing artifact, wrong owner/mode, wrong size, wrong SHA, wrong role/head, prerequisite-dependent bundle, incomplete/missing objects, or tree/entrypoint mismatch fails before promotion/effect;
7. caller cannot pass predecessor path/ref/artifact selector;
8. old recovery authority schema/Card binding cannot authorize the changed manager; new authority fixture includes artifact binding and validates;
9. all existing R1 caller-surface, symlink/ownership/mode, CAS/idempotency, lost-ack/reconcile, zero-effect, semantic-identity and physical-evidence tests remain green.

## Allowed files and forbidden scope

Only these four files may change after this card is committed:

- `nexus/contracts/gateway_deployment.py`
- `scripts/ops/mcp_gateway_durable.py`
- `tests/contracts/test_gateway_deployment_contract.py`
- `tests/ops/test_mcp_gateway_durable.py`

Do not modify Task Cards/specs/INDEX from the worker. Do not touch Gateway host state, recovery receipt JSON, DevSpace state, LaunchAgents, user Library recovery directories, GitHub main, PR merge state, or unrelated tests/source.

## Verification commands

The implementer must run, from repository root on the exact Candidate worktree:

```sh
git diff --check
python -m pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
python -m pytest -q tests/contracts/test_gateway_deployment_contract.py -k 'recovery or source_bundle or artifact or manifest'
python -m pytest -q tests/ops/test_mcp_gateway_durable.py -k 'r1 or gitlink or predecessor or bundle or recover or rollback'
rg -n '160000|gitlink|predecessor_artifact|durable_recovery_authority|semantic commit outside fresh main|submodule' nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
git diff --name-only
git diff --stat
git status --short
```

`git diff --name-only` after the authority-setup commit must contain no path outside the four implementation/test files. No deletion is authorized. The worker must inspect the complete diff before committing.

## Candidate and evidence requirements

The worker must produce exactly one scoped implementation commit on top of the coordinator-owned authority-setup commit. Report:

- exact base commit;
- exact Candidate commit and tree;
- changed paths;
- RED commands and observed failures;
- GREEN verifier commands and exit status;
- complete `git diff --check` result;
- any residual concern or unproven host behavior;
- maximum claim `R1_SOURCE_CANDIDATE_ONLY`.

The worker cannot accept, merge, push protected refs, issue successor recovery authority, start recovery, clean historical evidence, or claim G20 runtime closure.

## Independent acceptance gate

After the worker stops, the primary coordinator must independently bind the exact Candidate base/head/tree/diff, rerun the affected tests, inspect the full physical diff and scope, and use an independent reviewer/acceptance workflow. At least one falsification must specifically target:

- a populated/substituted Gitlink path that should fail;
- a tampered or prerequisite-dependent predecessor artifact that should fail;
- an old R2 authority attempting to authorize the new manager that should fail.

Only after independent acceptance may the batch claim `R1_SOURCE_CANDIDATE_ACCEPTED`. GitHub integration/main/runtime remain unproven.

## Exit and stop conditions

PASS only when a committed exact Candidate exists, all required tests/negative controls pass, no out-of-scope path changed, and independent acceptance is ready to consume it.

Return a bounded block rather than weakening the contract if:

- the exact predecessor artifact cannot be represented without caller-selected source/path/network authority;
- legitimate Gitlinks cannot be kept inert under the supported Git worktree behavior;
- existing R1 safety invariants require a broader security decision than the settled spec;
- source/test changes exceed the four-file scope;
- the base/main/Task Card/spec identity drifts before mutation.

`AUTO_CHAIN=false`.
