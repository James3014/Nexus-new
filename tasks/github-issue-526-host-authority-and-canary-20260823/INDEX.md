# Issue #526 host authority and local canary index

```yaml
campaign_id: github-issue-526-host-authority-and-canary-20260823
repository: James3014/Nexus-new
base_main: a5f6de006637c61e8073cbdc4dd6d43e96307787
base_tree: 57184a06f0bae4d86fca101f236e485e4c8b121d
auto_chain: false
```

| Order | Task | Status | SHA-256 | Dependency |
|---|---|---|---|---|
| 1 | `TASK-526-B-AUTHORITY` | MERGED | `477317e723493ad1f1a12035199c2aa55c39973564f71c918fb818c5fa9da366` | main `a5f6de00` |
| 2 | `TASK-526-C-RECEIPT-BUNDLE` | MERGED | `42a9df063963c3b9e7b8ad99128fc0bc13ae40b5511a4cdd66ce73a1bf40c9e3` | main `7c2e7970` |
| 3 | `TASK-526-D-HOST-CARD-SHA-REBIND r1` | SUPERSEDED | `f1c8df0cd66349a3c185e3fe12f074ee5d5e31e56c413a57453da5afed9cf350` | historical attempt Card SHA `a5f0fc12`; superseded by r2 after operations-fixture evidence |
| 4 | `TASK-526-D-HOST-CARD-SHA-REBIND r2` | MERGED | `c386446703e0b626b0c32a1cd58670c7561e5a209f1ccb25fc0c2251fddf5073` | main `ae8fddc1` |
| 5 | `TASK-526-E-PREISSUANCE-CONTRACT-RECONCILIATION` | MERGED | `e131e0b251e1d053ea9daddda218becc52b0e2b9e73f67ab0e82c661e810c047` | main `6e261f22` |
| 6 | `TASK-526-F-BUNDLE-PROFILE-HASH-BINDING` | MERGED | `608d22db9d3235c12a9f034561e179776be9aa8275b5c48f6dc2ff04f1fcf242` | main `526d45f0` |
| 7 | `TASK-526-G-AUTHORITY-JSON-IMPACT-MAP` | MERGED | `7f3dabcc4d7277b96a96b4cb02189f800080e5fc21dd5f1ae69826c11b67e577` | main `95fd37d7` |
| 8 | `TASK-526-H-HERMETIC-ROLLBACK-OBSERVATION-TIME` | MERGED (PR #545) | `d2c2b1a1871f3049788ecca73966b73dd06a337198dcfb918f0d4876c5f07052` | merge `16acce53704969fc9093c1c7d90d7fcfa46e51e6c` |
| 9 | `TASK-526-R1-DURABLE-DEPLOYMENT-RECONCILIATION` | ACTIVE (B semantic-identity clarification) | `b316a07965b070d1b76fa11fa20105d40bd2be1de325576e719a127bdc1d8609` | prior `c8882d47df5375091808a0d6e5340d6a80e9af6976ea4a8a4eed1d1983809487` superseded to bind rollback-unavailable/already-desired/uncertain replay edges; Candidate `3a97e2f493152e48b66eb2efe18125cbeb1d6f26` = REVISE |
| 10 | `TASK-526-HOST-1` | HISTORICAL_TARGET_SUPERSEDED | `f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514` | frozen `7ad264e1...` target; must not be reused for TASK-002 rebind |
| 11 | `TASK-526-I-TASK002-RECOVERY-ACTIVATION-REBIND` | MERGED (PR #594) | `4c0826c7d8c0e8c9d3bfd66c208222f5add4f9d011aabbdf563464626d611657` | merge `1f94c1402b189fec975799b5b0c13bcb9f66833f`; fresh receipt issued/merged by PR #595 |
| 12 | `TASK-526-J-R1-LIVE-HOST-ADAPTER` | ACTIVE | `acff953ad543309d54bbe8df791b03276723e5316993d21448d20dd5b80fb2cf` | main `4bfdae78`; live-host adapter/postflight/plist source closure, no host effect |

## Execution frontier

R1 source implementation has been independently accepted and merged; its durable acceptance evidence remains in `10-r1-source-acceptance-evidence.json`. Owner authorization comment `5418927784` changed the exact recovery target to `b2a9cca...` with predecessor `3d28fa7...`. Task I closed the activation-lineage reuse hole and merged as PR #594; the fresh recovery authority receipt then merged as PR #595 at main `4bfdae78...`.

Fresh pre-effect falsification after PR #595 proved that the R1 crash/reconcile state machine is not yet production-host-reachable: concrete `_RecoveryAdapters` exist only in tests, recovery postflight expects synthetic hashes rather than desired-source Gateway identities, and the recovery plist uses a literal token placeholder instead of the accepted fixed secret-env wrapper. The current source-only frontier is therefore `TASK-526-J-R1-LIVE-HOST-ADAPTER`. Task J is limited to the manager and manager tests, preserves public `gateway-recover` as effect-free, reuses the existing R1 ledger/state machine and fixed Gateway wrapper/postflight primitives, and performs no host or DevSpace effect.

The historical `TASK-526-HOST-1` is not rewritten: its frozen `7ad264e1...` target and old activation remain historical evidence and cannot authorize the TASK-002 rebind. After Task J independent acceptance/merge, the coordinator must re-issue the recovery authority receipt because the accepted manager hash changes. Actual manager materialization/Gateway effect remains separate, and the future DevSpace/ChatGPT-facing typed action is still `SERIALIZE_AFTER:#398` and outside Task J.

The Gateway-only local canary performs zero DevSpace effects. The future
DevSpace/ChatGPT-facing action integration remains `SERIALIZE_AFTER:#398`.

R1-B uses the fixed authority mirror, verified Git bundle, manager-owned bare
repository, and two full detached deployments described in the Card amendment.
Its semantic source set defines deployment identity; raw bundle SHA-256 is
post-receipt ledger evidence and is not receipt or deployment authority.
Recovery consumes only the new `RecoveryAuthorityReceipt` reference, never the
legacy host-effect bundle. `AUTO_CHAIN=false` remains authoritative; receipt
issuance, mirror/bundle provisioning, checkout materialization, LaunchAgent
adoption, physical reconcile, and canary remain deferred until independent
source acceptance and a fresh host receipt.

No task may self-approve, merge, activate its successor, install/reload the
Gateway, or claim production readiness. Controller continuation does not change
worker `AUTO_CHAIN=false`.
