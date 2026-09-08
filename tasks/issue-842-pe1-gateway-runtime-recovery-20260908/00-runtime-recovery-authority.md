# Task Card 00 — Issue #842 PE1 Gateway runtime recovery authority

```yaml
task_id: ISSUE-842-PE1-GATEWAY-RUNTIME-RECOVERY
campaign_id: issue-842-pe1-gateway-runtime-recovery-20260908
issue: 842
repository: James3014/Nexus-new
status: ACTIVE
execution_lane: GOVERNED
auto_chain: false
commit_required: true
candidate_required: true
independent_acceptance_required: true
allowed_file_count: 1
allowed_files:
  - tasks/github-issue-526-g20-r1-source-contract-delta-20260903/02-r1-complete-deployment-recovery-authority-receipt.json
allow_deletions: false
claim_ceiling: CHATGPT_FACING_GATEWAY_PE1_RUNTIME_RECOVERY_ONLY
```

## Owner authorization

The Owner response `繼續解除` (UTF-8 SHA-256
`bcb5fd10da6653b177ee744faa495f4be9a1f66bbdaed1680b7cac138659a13f`)
authorizes the exact one-shot scope stated immediately before it in Codex thread
`01a07ec9-ef56-73e0-943f-eb95269fcf82`:

- issue one current-target `RUNTIME_RECOVERY` authority;
- publish and protected-merge the exact tracked typed receipt;
- replace the dirty/stale fixed authority mirror only after preserving it;
- materialize the byte-identical receipt, request, and predecessor bundle in
  the fixed Gateway store;
- execute exactly one manager-local Gateway-only `gateway-recover` effect;
- verify authenticated action discovery and one bounded
  `nexus_execution_readiness` call;
- preserve DevSpace and Open SWE unchanged;
- make no release or production claim.

This current Owner decision is not reusable for another target, request,
service, repository, effect, or retry.

## Frozen physical binding

- source base / PR base: `c05005088564afc1bba5111f9c4036c82e175f30`
- source base tree: `748d0970dac1aa3d92775ed65d35bfa44f9f354a`
- accepted stable manager source: `8bf586e3db31972e7ac7535226b313094dda20c7`
- accepted stable manager tree: `a8e2df968cdac6deac1a50c5cc168f0b0a66cc0a`
- installed stable manager SHA-256:
  `7af3760bd2b6729654a89d7b07fa4c43bb9b323e8e0006a08aa5e485d78562ac`
- independent manager acceptance receipt hash:
  `e485192ff54122dbde114ffcf02b9f58942140fc3ac31fc3bc1315f51fcb7e0b`
- desired Gateway commit/tree:
  `c05005088564afc1bba5111f9c4036c82e175f30` /
  `748d0970dac1aa3d92775ed65d35bfa44f9f354a`
- predecessor Gateway commit/tree:
  `bea9ae7a6742929785d40840da79cff4faefa485` /
  `94128d1c2934e1060c34cfaf1fad9fe48dd02f6b`
- predecessor artifact format: `git-bundle-self-contained-v1`
- predecessor artifact SHA-256:
  `bc4c58fee3bbb5c2bca3180f25e4fd4f1e7a4817a964c88cec625fdefd81a4e7`
- predecessor artifact size: `38189434`
- predecessor artifact ref: `refs/nexus-r1/predecessor-artifact`
- fixed service: `com.nexus.mcp.gateway.direct`
- fixed endpoint: `http://127.0.0.1:8766`
- fixed receipt id: `receipt-issue842-pe1-runtime-recovery-20260908`
- fixed request id: `req-issue842-pe1-runtime-recovery-20260908`
- fixed idempotency fence: `fence-issue842-pe1-runtime-recovery-20260908`
- issuer: `owner-james`
- typed coordinator / authorized actor: `coordinator-codex`
- repository: `James3014/Nexus-new`
- source thread: `01a07ec9-ef56-73e0-943f-eb95269fcf82`

The legacy R1 source-contract Card remains the receipt's fixed
`host_card_path` and `card_sha256`. This Card authorizes the later issuance and
host-effect gate that the legacy source-only Card explicitly excluded; it does
not alter the R1 schema or manager implementation.

## Phase A — bounded Luna Candidate

Luna may update exactly the one allowed tracked receipt file. It must:

1. preserve schema `nexus.gateway.durable_recovery_authority.v2` and all fixed
   R1 constants;
2. use a future tracked provenance activation identity unique to this Card;
3. keep accepted-manager identity and its independent acceptance hash exact;
4. bind desired and predecessor source plus the exact self-contained bundle;
5. derive `RecoverySourceSet`, desired/predecessor manifests, and all canonical
   hashes using current repository code, never handwave or copy stale hashes;
6. issue for no more than 24 hours, `NOT_REVOKED`;
7. stop after a committed Candidate and verifier evidence.

The worker may not push, merge, update the authority mirror or host stores,
invoke the manager, touch launchd, approve itself, or claim PE1 complete.

## Verification

From the exact Candidate worktree:

```sh
git diff --check
python -m pytest -q tests/contracts/test_gateway_deployment_contract.py -k 'recovery_authority or recovery_request or source_set or manifest'
python -m pytest -q tests/ops/test_mcp_gateway_durable.py -k 'r1 or recovery or predecessor or bundle'
git diff --name-only c05005088564afc1bba5111f9c4036c82e175f30...HEAD
git diff --stat c05005088564afc1bba5111f9c4036c82e175f30...HEAD
```

The coordinator must additionally parse the exact receipt with current source,
recompute every hash/manifest, compare the full diff, verify no deletion,
obtain independent acceptance, and require terminal required GitHub checks
before expected-head/CAS merge.

## Phase B — coordinator-only effect

Only after the exact receipt Candidate is accepted and merged:

1. re-read remote `main`, receipt bytes, live Gateway identity, service PID,
   predecessor identity, and ledger;
2. preserve the dirty/stale fixed authority mirror without deleting or
   overwriting unique bytes, then create a clean fixed mirror at current main;
3. copy byte-identical tracked receipt, typed request, and exact predecessor
   bundle to their fixed mode-`0600` stores;
4. invoke the installed stable manager exactly once through its private live
   recovery sink;
5. on timeout or lost acknowledgement, reconcile only the same request/fence;
6. prove new source/tree/deployment/server/action/schema/permission identity,
   authenticated `tools/list`, and one actual `nexus_execution_readiness`
   result;
7. if verification fails and rollback is required, use only the receipt-bound
   predecessor; preserve all evidence.

## Exit

PASS only when the one-file receipt Candidate is independently accepted and
merged, the single runtime effect is terminal `VERIFIED` or exact rollback is
terminally proven, authenticated action discovery succeeds, and the readiness
call is physically recorded. This permits #842 PE1 evidence only.

BLOCK on any base/head/tree drift, stale/substituted receipt, bundle mismatch,
extra path/deletion, unknown external effect, failed required check, authority
mirror ambiguity, or observed DevSpace/Open SWE effect.

`AUTO_CHAIN=false`.
