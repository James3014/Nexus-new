# TASK-526-E-PREISSUANCE-CONTRACT-RECONCILIATION — Close all remaining source blockers

    task_id: TASK-526-E-PREISSUANCE-CONTRACT-RECONCILIATION
    issue: 526
    repository: James3014/Nexus-new
    status: ACTIVE
    auto_chain: false
    claim_mode: MANUAL_DISPATCH
    base_main: ae8fddc1edc5fd3c39ae4e506292b127bc4d31de
    base_tree: f4dfdbbecd6d5cd4ce842aa5345b2a21634c8b5d
    work_branch: codex/issue-526-preissuance-reconcile
    host_card_sha256: f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514
    owner_activation_id: OWNER_ISSUE526_CONTINUE_20260823
    owner_activation_sha256: f0ed77ffe3872b083ef0b6d66526524a7091a8e3125322c84ba632f3c64ba322
    authority_mirror_root: /Users/jameschen/Workspace/Nexus-new-authority-main
    claim_ceiling: NEXUS_GATEWAY_PREISSUANCE_CONTRACT_SOURCE_CANDIDATE_ONLY

## Problem and authority

PRs #538 and #539 merged the three-receipt bundle contract and corrected Host
Card binding. A fresh source/physical audit then proved that the remaining
pre-issuance path still cannot pass:

- the fixed authority mirror is the user's dirty/divergent canonical checkout;
- the observed rollback-only current worktree is dirty while the contract
  requires every profile to be clean;
- the exact loaded .direct plist is a fixed /bin/zsh -c wrapper while rollback
  accepts only direct interpreter argv;
- the generated desired plist contains a literal token placeholder rather than
  using the physically proven fixed env-file wrapper;
- health and MCP initialize expose different snake/camel field shapes, while
  postflight compares raw dictionaries and misses physical aliases;
- bundle children are not required to equal the bundle shared provenance;
- current_main_sha lacks an ancestor-of-remote-main proof;
- the receipt final manager hash is not cross-bound to the install artifact.

This Card authorizes one source/test Candidate to close those exact blockers.
It authorizes no persistent mirror creation, bundle issuance, local store,
artifact installation, plist/launchctl/Gateway/DevSpace effect, approval,
merge, activation, release, or production claim.

The exact current wrapper and the split between accepted-main manager bytes and
the frozen desired Gateway runtime at 7ad264e1 are already required by the Host
Card. Encoding them fail-closed is a Goal-preserving correction, not a new
permission or security decision.

## Owner-bound semantic basis

No new Owner decision is inferred:

- Owner activation OWNER_ISSUE526_CONTINUE_20260823 binds the exact message
  都同意，繼續 and SHA-256 above.
- The current Owner directive says that while Nexus governance/control is
  defective, repair it through the non-Nexus external bootstrap before
  resuming that governance path.
- Host Card Frozen source and profiles separately require the accepted final
  manager source/hash and the exact desired Gateway runtime root/head/tree at
  7ad264e1. They are intentionally distinct identities and cannot substitute
  for one another.
- Host Card requires exact predecessor capture and reversible restoration. The
  physical predecessor is the byte-hashed fixed wrapper plist below. Accepting
  only that literal wrapper for capture/rollback preserves current authority;
  it does not grant generic shell execution.
- The desired wrapper is generated solely by the single manager from a complete
  frozen profile and fixed literals. The request cannot select or modify the
  shell, command, environment file, exports, root, interpreter, entrypoint,
  service, or plist path.

Any proposal beyond those exact bindings is an Owner blocker. This Card does
not contain such a proposal.

## Exact worker mutation scope

Modify only:

- nexus/contracts/gateway_deployment.py
- scripts/ops/mcp_gateway_durable.py
- tests/contracts/test_gateway_deployment_contract.py
- tests/ops/test_mcp_gateway_durable.py

Create/delete none. Do not edit Cards/INDEX, Host Card, Gateway HTTP/stdio,
DevSpace, Planner/route/Workforce policy, runtime/generated state, or unrelated
formatting.

The coordinator-created Card/INDEX commit is authority setup and is not worker
implementation scope.

## Required contract corrections

### 1. Rollback-only current profile

- Set only CURRENT_PROFILE.git.clean=false.
- Keep DESIRED_PROFILE.git.clean=true.
- validate_profile may accept clean=false only for the complete frozen
  CURRENT_PROFILE whose trust class is ROLLBACK_ONLY_OBSERVED_CURRENT; no
  arbitrary dirty profile is accepted.
- gateway_profile_matches compares physical cleanliness to the profile exact
  git.clean value rather than hardcoding true.
- A dirty current profile can be rollback/predecessor evidence only. It cannot
  be a desired target, authority mirror, or stable-artifact source.

### 2. Exact current wrapper rollback and generated reload wrapper

The physical predecessor plist SHA-256 is
082c7786f9b7254949a6fdb38d905414a78c1b1979aabf7f434dd7019c09e100.
Accept it only when serialized bytes and every parsed value match:

- label com.nexus.mcp.gateway.direct;
- RunAtLoad=true and KeepAlive=true;
- fixed current working directory, stdout, and stderr paths;
- ProgramArguments exactly /bin/zsh, -c, and the literal current command that
  changes to the frozen current root, sources only the fixed mcp-gateway.env,
  exports only PYTHONDONTWRITEBYTECODE=1, the exact current
  NEXUS_CANONICAL_SOURCE_ROOT, and the fixed self-hosted state directory, then
  execs the fixed interpreter and current Gateway entrypoint;
- no plist EnvironmentVariables field for this wrapper form.

Any byte, shell, argument, env-file, export, root, interpreter, entrypoint,
label, log, boolean, or extra-field mutation rejects. This is one exact legacy
allowlist, never generic shell authority.

The normal desired plist builder must generate the same fixed wrapper shape
from only the validated frozen profile. The desired command may vary only by
the frozen desired root/entrypoint. No caller supplies a command, executable,
env file, export, label, plist path, PID, or root. Preserve exact direct-form
validation only for compatibility; never emit an unresolved token placeholder
into the active desired plist.

### 3. Shared bundle/child provenance equality

For every child, require exact equality with the bundle for repository, Host
Card path/ID/SHA, source base merge/tree, correction merge/tree, independent
acceptance receipt hash, final manager SHA-256, and current-main SHA.

Mismatch tests must recompute the mutated child receipt hash and outer bundle
hash so rejection occurs at the intended semantic equality gate.

### 4. Manager artifact triple binding

For install requests require:

host_authority.final_manager_sha256
equals stable_artifact.source_blob_sha256
equals stable_artifact.artifact_sha256.

The artifact remains separately bound to request/receipt/fence, accepted source
root/head/tree/path, UID/mode, predecessor, and rollback receipt. A mismatch
rejects before destination creation/write.

## Required manager corrections

### 5. Persistent clean authority mirror

Set the sole fixed authority source root to:

/Users/jameschen/Workspace/Nexus-new-authority-main

The worker must not create this path. After source merge/acceptance and before
issuance, only the coordinator may create/update it as a detached, non-DevSpace
Git worktree from verified remote main.

Before authority observation/effect the manager requires exact path, safe
non-symlink ancestry, expected UID and safe modes, fixed public origin, clean
status including no untracked files, local HEAD equal to ls-remote main, and
fixed bundle path/local byte equality.

The mirror is source/cache only. GitHub main remains sole authority; it creates
no process manager, receipt issuer, route, or approval authority. The dirty
canonical checkout is never consulted by the host-authority verifier.

### 6. Current-main ancestry

After reading remote main, run only the manager-owned fixed command:

git -C fixed-mirror merge-base --is-ancestor
bundle.current_main_sha remote-main-sha

Require exit 0. Exit 1, malformed/unrelated/descendant SHA, wrong command,
rewind/divergence, dirty mirror, or local HEAD drift rejects before host
observation/effect.

This is ancestry, not equality: the bundle binds the accepted correction main
that must be an ancestor of the later self-containing issuance merge.

### 7. Physical health/MCP normalization

Normalize the actual Gateway surfaces into one typed identity:

- health server_instance_id and initialize serverInfo.serverInstanceId map to
  server_instance;
- health tool_manifest_revision and initialize serverInfo.toolManifestRevision
  map to tool_manifest_sha256;
- health full_tool_schema_hash and initialize serverInfo.fullToolSchemaHash map
  to schema_sha256;
- health permission_policy_hash and initialize serverInfo.permissionPolicyHash
  map to permission_sha256;
- health lifecycle_revision and initialize serverInfo.lifecycleRevision map to
  lifecycle;
- health repo_root/git_head plus fixed local Git observation of the frozen
  profile provide root/head/tree/clean;
- successful bearer-authenticated initialize and tools/list prove
  client_bound=true and token_bound=true;
- action/task remain fixed gateway-rebind / TASK-526-A, never caller-selected.

Do not compare raw health and initialize dictionaries. Compare all overlapping
canonical fields and reject missing, empty, wrong-type, malformed-hash, or
conflicting aliases. Recompute sorted-name manifest and full tool-schema hash
from tools/list; both must equal declared canonical hashes. Required actions
must be a non-empty subset of observed tool names.

Use the same normalizer for current authenticated preflight and postflight.
The physical lifecycle identity is nexus.lifecycle.gateway.v2; durable
quiescence state remains separate and cannot substitute for the lifecycle
revision.

## Acceptance and negative controls

- exact dirty current rollback profile passes; any other dirty profile rejects;
- dirty/moved desired profile rejects;
- exact captured wrapper passes only as rollback evidence; every mutation
  rejects;
- desired plist builder emits only the fixed wrapper and fixed env/state paths;
- no arbitrary shell or caller-selected command reaches an effect seam;
- every shared bundle/child mismatch with recomputed hashes rejects;
- manager/artifact triple mismatch rejects before write;
- mirror missing/symlink/unsafe/dirty/wrong-origin/wrong-HEAD rejects;
- non-ancestor/rewind/current-main substitution rejects using exact argv;
- actual health + initialize + tools/list shapes normalize and pass;
- every missing/conflicting health alias rejects;
- successful authenticated calls cannot bypass profile, manifest, permission,
  lifecycle, action/task, quiescence, bundle, or artifact gates;
- existing bundle ordering, uniqueness, revocation, freshness, selected-child
  equality, ledger/fence, rollback, source/store, and zero-DevSpace tests remain
  green;
- no existing test is renamed, skipped, xfailed, deselected, or weakened.

## Verification

    uv run pytest -q tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
    uv run ruff check nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
    uv run ruff format --check --preview nexus/contracts/gateway_deployment.py tests/contracts/test_gateway_deployment_contract.py
    python3 -m py_compile nexus/contracts/gateway_deployment.py scripts/ops/mcp_gateway_durable.py tests/contracts/test_gateway_deployment_contract.py tests/ops/test_mcp_gateway_durable.py
    git diff --check

Independent review must bind exact base/head/tree/Card hashes, inspect the full
four-file diff, challenge generalized shell authority, fake health aliases,
bundle broadening, mirror caller selection, ancestry TOCTOU, artifact mismatch,
test-node loss, and false-green injected runners.

## Dependencies and exit

- Git-tracked authority bundle issuance remains blocked until this Candidate is
  independently accepted, merged, and read back.
- Coordinator mirror creation is a later external-bootstrap preparation step,
  not part of this worker Candidate.
- Host activation remains blocked until the separate issuance PR and all
  physical Host Card gates pass.
- PASS means only
  NEXUS_GATEWAY_PREISSUANCE_CONTRACT_SOURCE_CANDIDATE_ONLY.
- AUTO_CHAIN=false; worker stops after one four-file Candidate.
