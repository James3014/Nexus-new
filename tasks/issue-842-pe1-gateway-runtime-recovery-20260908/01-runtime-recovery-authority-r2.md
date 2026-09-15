# Task Card 01 — Issue #842 PE1 Gateway runtime recovery authority r2

```yaml
task_id: ISSUE-842-PE1-GATEWAY-RUNTIME-RECOVERY
attempt_id: ISSUE-842-PE1-GATEWAY-RUNTIME-RECOVERY-R2
campaign_id: issue-842-pe1-gateway-runtime-recovery-20260908
issue: 842
repository: James3014/Nexus-new
status: SUPERSEDED_BY_PREFLIGHT_BLOCK
superseded_by: 02-runtime-recovery-manager-r3.md
supersedes: 00-runtime-recovery-authority.md
supersession_reason: MATERIAL_CURRENT_MAIN_DRIFT_BEFORE_ACCEPTANCE
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

## Preserved Owner authorization at r2 entry

At r2 entry, the one-shot Owner response `繼續解除` had not yet produced a
merged/materialized receipt or recovery effect. Its UTF-8 SHA-256 is
`bcb5fd10da6653b177ee744faa495f4be9a1f66bbdaed1680b7cac138659a13f`;
source thread is `01a07ec9-ef56-73e0-943f-eb95269fcf82`.

This r2 Card preserves Card 00's exact Gateway-only authority and changes only
the source target and receipt/request/fence identities after independent review
returned `ACCEPTANCE_BLOCKED` for main drift. It grants no Open SWE, DevSpace,
release, production, retry-after-effect, or follow-main authority.

The later supersession record is controlling: r2 subsequently consumed only
receipt issuance/materialization. Its manager call failed before any ledger or
Gateway effect, so the one-shot replacement effect remained unused.

## Fresh physical binding

- current main / PR base: `62f4b019e7bcde78b78e143d973ff0dbbdca1173`
- current main tree: `b24bb2c12d0c0c9ac783bd6d7406d05a7c513f70`
- accepted stable manager source/tree:
  `8bf586e3db31972e7ac7535226b313094dda20c7` /
  `a8e2df968cdac6deac1a50c5cc168f0b0a66cc0a`
- installed stable manager SHA-256:
  `7af3760bd2b6729654a89d7b07fa4c43bb9b323e8e0006a08aa5e485d78562ac`
- independent manager acceptance receipt hash:
  `e485192ff54122dbde114ffcf02b9f58942140fc3ac31fc3bc1315f51fcb7e0b`
- desired Gateway commit/tree:
  `62f4b019e7bcde78b78e143d973ff0dbbdca1173` /
  `b24bb2c12d0c0c9ac783bd6d7406d05a7c513f70`
- predecessor Gateway commit/tree:
  `bea9ae7a6742929785d40840da79cff4faefa485` /
  `94128d1c2934e1060c34cfaf1fad9fe48dd02f6b`
- predecessor bundle: `git-bundle-self-contained-v1`, ref
  `refs/nexus-r1/predecessor-artifact`, SHA-256
  `bc4c58fee3bbb5c2bca3180f25e4fd4f1e7a4817a964c88cec625fdefd81a4e7`,
  size `38189434`
- fixed service/endpoint: `com.nexus.mcp.gateway.direct` /
  `http://127.0.0.1:8766`
- receipt id: `receipt-issue842-pe1-runtime-recovery-r2-20260908`
- request id: `req-issue842-pe1-runtime-recovery-r2-20260908`
- idempotency fence: `fence-issue842-pe1-runtime-recovery-r2-20260908`
- issuer: `owner-james`
- coordinator / actor: `coordinator-codex`
- repository: `James3014/Nexus-new`

The receipt retains the fixed legacy R1 `host_card_path`, card hash, source-base
commit/tree, standing-grant identity, and accepted-manager lineage required by
the existing schema.

## Phase A — bounded Luna Candidate

Luna may update exactly the one allowed receipt file. It must derive the new
source set, desired/predecessor manifests, and canonical receipt hash with
current repository code. It must issue the receipt for at most 24 hours with
`NOT_REVOKED`, commit only that file, run the verifiers below, and stop.

The worker may not push, merge, approve, alter either Card/INDEX, update the
authority mirror or host stores, invoke the manager, or touch launchd/runtime.

## Verification

```sh
git diff --check
uv run pytest -q tests/contracts/test_gateway_deployment_contract.py -k 'recovery_authority or recovery_request or source_set or manifest'
uv run pytest -q tests/ops/test_mcp_gateway_durable.py -k 'r1 or recovery or predecessor or bundle'
git diff --name-only HEAD^...HEAD
git diff --stat HEAD^...HEAD
```

The coordinator independently recomputes receipt/request/manifests, verifies
the exact predecessor bundle, checks no deletion or out-of-scope path, reruns
the focused suites, and obtains a distinct exact-Candidate verdict.

## Target-branch advancement

The immutable Candidate remains reviewable relative to this exact source
target. A later `main` advancement is integration-context drift and blocks the
effect when it changes any Gateway/recovery/readiness/task-continuity/
authority/permission source or contract, when the desired commit is no longer
an ancestor, or when its materiality cannot be proven. A proven disjoint
advancement may be recorded without rewriting the receipt, but latest target,
diff, checks, branch protection and expected-head/CAS must still be reacquired
before merge. This precision does not permit arbitrary stale targets.

## Phase B — coordinator-only effect

Only after exact-Candidate acceptance and protected merge:

1. re-read remote main, merged receipt bytes, live Gateway and predecessor,
   service PID, and ledger;
2. preserve the dirty/stale fixed authority mirror without deleting unique
   bytes, then create a clean fixed mirror at merged main;
3. materialize byte-identical receipt, derived typed request, and exact bundle
   to fixed mode-`0600` stores;
4. invoke installed manager `7af3760b...` exactly once through its private live
   recovery sink;
5. reconcile only the same request/fence after timeout or lost acknowledgement;
6. prove desired source/tree/deployment/server/action/schema/permission,
   authenticated action discovery, and one actual
   `nexus_execution_readiness` result;
7. use only the receipt-bound predecessor for rollback and preserve evidence.

## Exit

PASS requires accepted and merged receipt, one terminal `VERIFIED` recovery or
exact terminal rollback, authenticated discovery, and a physically recorded
readiness call. BLOCK on material source drift, any typed/hash/bundle mismatch,
extra path/deletion, unknown effect, failed required check, unsafe mirror,
or any DevSpace/Open SWE effect.

`AUTO_CHAIN=false`.

## Supersession record

Receipt r2 was independently accepted, merged by PR #876, and materialized.
The single manager call failed before any ledger append or launchd effect because
the accepted installed manager's 65,536-byte store bound rejected the existing
79,028-byte terminal ledger. Request/fence r2 has no ledger row and no external
effect. Card `02-runtime-recovery-manager-r3.md` is the sole active successor;
ledger truncation, archival substitution, and retrying manager `7af3760b...`
are forbidden.
