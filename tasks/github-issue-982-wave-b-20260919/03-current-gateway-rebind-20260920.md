# Task Card: issue-982-wave3-current-gateway-rebind-20260920

artifact_authority: current
task_id: `issue-982-wave3-current-gateway-rebind-20260920`
owner: James Chen
status: ACTIVE
commit_required: true
candidate_required: true
worker_may_commit: true
worker_may_approve: false
worker_may_integrate: false
worker_may_push: false
AUTO_CHAIN: false

## Objective

Track one fresh #526 v2 recovery authority that physically rebinds the live Nexus Gateway from the currently observed predecessor `de493e2e90e3ad9eb5fd401ad51496fd5ffd6455 / 88669953a52467af36375fafa08b40fffcc9c7c8` to `2f2b75dd46ad3b03564c385a954d11565b8377ed / 5cb03074a53f12fe6d94f81fe57db810a87591d7`.

The desired source already contains the merged #1032 MiMo route and merged #1042 B3 contract. This card does not change production source semantics.

## Owner activation

- #982 comment: `5749521394`
- exact Owner instruction: `目標到wave3完成`
- UTF-8 SHA-256: `71e218a72ae7c10102bf89db268d73799c729cf7a1c25688f0e7cc39e55eea82`
- keyed Task Card grant: `issue982-wave3-gateway-authority-card-20260920`
- grant receipt hash: `14ed7a30f3bd772e6deac1fc8c62d4aaa081246c882a01824dfde95f831b5f21`

## Recovery identity

- fixed #526 manager SHA-256: `3f0c34204bef175fcfad7150c5919d96f6b3735813cea5258bdcd51e37d4baeb`
- manager independent-acceptance lineage: `3e1ed6a7c05d2951ab343e4b249425bfdbd0203dcdd4e11b0f7cdbe5342b2bd1`
- desired manifest: `r1-63711c4677ab7f5315b3ca12f4f4189d88132618 / c354dd9f880d5c4f3bd500c0f3f590d5927a9d25a5aabbc549679bd364d3afb1`
- predecessor manifest: `r1-1bc81ea3baff3ce74490f8c2498ae0b828946d0a / dba5be014a3f43e0689283e0fd018b6ec6f77edeb631b85eda7310774b7a6bf4`
- self-contained predecessor bundle: `1c729ddc2299782999e5211e1b3198977edf9f62b75f284d09389c4cfd4aea40`, 39198548 bytes
- receipt: `receipt-issue982-wave3-gateway-2f2b-20260920-a1 / 12d7d8e1a1ecbbaf2c68492f550ca69907149efa20deaa6c4e752055cd662444`
- request: `req-issue982-wave3-gateway-2f2b-20260920-a1 / 5ae8f3e905ab5908954d6fe3dac82a208faaa2179e5ff05595b91d46edef0322`
- fence: `fence-issue982-wave3-gateway-2f2b-20260920-a1`

## Allowed files

- `tasks/github-issue-982-wave-b-20260919/03-current-gateway-rebind-20260920.md`
- `tasks/github-issue-982-wave-b-20260919/INDEX.md`
- `tasks/github-issue-526-g20-r1-source-contract-delta-20260903/02-r1-complete-deployment-recovery-authority-receipt.json`

No production/runtime source file is authorized.

## Verification

Before integration:

- validate the fresh receipt with `validate_recovery_authority()`;
- validate the request with `validate_recovery_request()`;
- exact diff scope must remain the three allowed governance paths;
- no deletion;
- exact-head CI must be terminal success;
- independent acceptance is required.

After integration:

1. materialize the exact tracked receipt to the fixed #526 local authority store;
2. materialize only the exact predecessor bundle bound above;
3. zero-effect typed preflight must return `effect_started=false` with `TARGET_READY` and `ROLLBACK_READY`;
4. execute at most one exact durable recovery attempt;
5. timeout/unknown outcome must reconcile the same operation; never issue a replacement request/fence;
6. prove loaded Gateway source/tree and current runtime identity.

## Stop boundary

This card authorizes only Gateway convergence prerequisite work. It does not authorize MiMo provider effect before convergence, provider/model override, OWNER_DIRECT B3 fallback, Wave 4, release, or production/public claims.

After Gateway convergence, control returns to the existing B3 card for fresh Workforce Admission and the positive + same-grant widening/tamper witnesses.

`AUTO_CHAIN=false`.
