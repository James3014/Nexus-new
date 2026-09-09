# Task Card 02 — Issue #842 PE1 capacity-safe Gateway recovery r3

```yaml
task_id: ISSUE-842-PE1-GATEWAY-RUNTIME-RECOVERY
attempt_id: ISSUE-842-PE1-GATEWAY-RUNTIME-RECOVERY-R3
campaign_id: issue-842-pe1-gateway-runtime-recovery-20260908
issue: 842
repository: James3014/Nexus-new
status: ACTIVE
supersedes: 01-runtime-recovery-authority-r2.md
supersession_reason: PRE_EFFECT_MANAGER_LEDGER_CAPACITY_INCOMPATIBILITY
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

## Preserved Owner authorization and retry safety

Owner response `繼續解除`, UTF-8 SHA-256
`bcb5fd10da6653b177ee744faa495f4be9a1f66bbdaed1680b7cac138659a13f`,
source thread `01a07ec9-ef56-73e0-943f-eb95269fcf82`, authorizes the
one-shot Gateway-only recovery outcome. The r2 call did not consume the effect:

- installed manager: `7af3760bd2b6729654a89d7b07fa4c43bb9b323e8e0006a08aa5e485d78562ac`;
- ledger: 41 rows / 79,028 bytes before and after;
- exact failure: `GatewayContractError: gateway store exceeds size bound`;
- failure site: ledger `_safe_store_path` before request append, source staging,
  launchd, or Gateway replacement;
- r2 request/fence are absent from the append-only ledger;
- live predecessor PID/server/source remained unchanged.

Therefore r3 is a proven zero-effect preflight successor, not a retry of an
unknown effect. It must use new receipt/request/fence identities and may perform
at most the still-unused single Gateway replacement effect.

## Fresh physical binding

- current main / PR base / desired Gateway commit:
  `f0b89a62326cc99183c7d3af5ac4a93fd3b43cc6`
- current main / desired tree:
  `87859d0b22ce66ab77bd71789ce1aadec7926f98`
- accepted capacity-safe manager source merge/tree:
  `4306e223f4fc1a092f7a0a21ff4aa5da4455f97e` /
  `13e0db8e4238afa899679f56b13addb6e9888681`
- accepted manager SHA-256:
  `6873dde17e08d4020620c2408e414327b176be723f5f23f01bee754b2627502c`
- exact independent source verification payload SHA-256:
  `df0f8db214e508bb49a1128411f7ecd98d593951e1dfee9aed255a0bdfe082e3`
- verification source: Issue #806 comment `5556900337`, exact Candidate
  `b0ec2fc4993bb2c2d49d5c66e510e2a13f89a940`, tree
  `13e0db8e4238afa899679f56b13addb6e9888681`, merged by PR #823 as
  `4306e223f4fc1a092f7a0a21ff4aa5da4455f97e`
- predecessor Gateway commit/tree:
  `bea9ae7a6742929785d40840da79cff4faefa485` /
  `94128d1c2934e1060c34cfaf1fad9fe48dd02f6b`
- predecessor bundle: `git-bundle-self-contained-v1`, sole ref
  `refs/nexus-r1/predecessor-artifact`, SHA-256
  `bc4c58fee3bbb5c2bca3180f25e4fd4f1e7a4817a964c88cec625fdefd81a4e7`,
  size `38189434`
- fixed service/endpoint: `com.nexus.mcp.gateway.direct` /
  `http://127.0.0.1:8766`
- receipt id: `receipt-issue842-pe1-runtime-recovery-r3-20260908`
- request id: `req-issue842-pe1-runtime-recovery-r3-20260908`
- idempotency fence: `fence-issue842-pe1-runtime-recovery-r3-20260908`
- issuer: `owner-james`
- coordinator / actor: `coordinator-codex`
- repository: `James3014/Nexus-new`

The receipt retains the fixed R1 host-card path/hash, source-base tuple,
standing-grant provenance, strict source-set/manifests, and future tracked-main
byte-equality gate.

## Phase A — bounded Luna receipt Candidate

Luna may update exactly the one allowed receipt JSON. It must bind accepted
manager merge/tree/hash/verification above, desired and predecessor identities,
new r3 IDs, a maximum 24-hour `NOT_REVOKED` window, and manager-derived source
set/manifests/canonical hashes. It must commit only that file and stop.

No production code, Card/INDEX, push, merge, mirror, fixed store, manager,
ledger, launchd, Gateway, DevSpace, or Open SWE mutation is allowed to Luna.

## Verification

```sh
git diff --check
uv run pytest -q tests/contracts/test_gateway_deployment_contract.py -k 'recovery_authority or recovery_request or source_set or manifest'
uv run pytest -q tests/ops/test_mcp_gateway_durable.py -k 'r1 or recovery or predecessor or bundle'
git diff --name-only HEAD^...HEAD
git diff --stat HEAD^...HEAD
```

The coordinator and a distinct reviewer must independently bind Card/Candidate,
recompute receipt/request/source-set/manifests, verify manager and predecessor
artifacts, rerun exact verifiers, and confirm zero deletion/scope widening.

## Phase B — coordinator-only manager and runtime effect

Only after accepted receipt merge:

1. fresh-read merged main/receipt, clean fixed mirror, live predecessor, ledger,
   fixed manager and backups;
2. preserve r2 receipt/request and manager `7af3760b...` evidence;
3. materialize byte-exact manager `6873dde1...` from accepted commit/tree to
   fixed `gateway-direct/manager.py`, owner/gid and mode `0600`, then import and
   revalidate its own hash plus the new receipt/request without effect;
4. materialize byte-identical r3 receipt/request and reuse only the exact
   receipt-bound predecessor bundle;
5. call `_gateway_recover_live` exactly once;
6. on timeout/lost acknowledgement, reconcile only r3 request/fence;
7. prove terminal ledger outcome, desired source/tree/deployment, new PID/server,
   manifest/full-schema/permission identities, authenticated action discovery,
   and one actual `nexus_execution_readiness` result;
8. if required, restore only the receipt-bound predecessor and preserved manager;
   never erase evidence.

## Target advancement

Later main movement blocks the effect if it changes Gateway/recovery/readiness/
task-continuity/authority/permission source or contract, breaks desired ancestry,
or cannot be proven disjoint. Proven disjoint integration-context drift may be
recorded, but exact PR checks, expected-head/CAS and merged receipt readback
remain mandatory.

## Exit

PASS requires an accepted/merged r3 receipt, byte-exact capacity-safe manager,
one terminal `VERIFIED` recovery or exact terminal rollback, authenticated
discovery, and a recorded readiness call. BLOCK on any authority/hash/artifact
mismatch, material source drift, extra path/deletion, unknown effect, unsafe
ledger/mirror, failed required check, or DevSpace/Open SWE effect.

`AUTO_CHAIN=false`.
