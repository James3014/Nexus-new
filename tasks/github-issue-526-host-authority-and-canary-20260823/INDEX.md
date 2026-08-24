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
| 9 | `TASK-526-R1-DURABLE-DEPLOYMENT-RECONCILIATION` | ACTIVE (B semantic-identity clarification) | `c8882d47df5375091808a0d6e5340d6a80e9af6976ea4a8a4eed1d1983809487` | prior `689c6883059adc5ebdf112ebedee3f8d3ca2000c56193edc9c29068a8f2a50a4` superseded to clarify bundle-import/evidence ordering; Candidate `3a97e2f493152e48b66eb2efe18125cbeb1d6f26` = REVISE |
| 10 | `TASK-526-HOST-1` | BLOCKED_BY_R1 | `f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514` | R1 source acceptance + fresh redesigned host receipt |

## Execution frontier

`TASK-526-R1-DURABLE-DEPLOYMENT-RECONCILIATION` is the active source-only
frontier. It may produce one four-file source Candidate and must stop. The
R1 Card/INDEX update is coordinator-owned setup and is outside the worker's
four-file ceiling. `TASK-526-HOST-1` cannot mutate repository or host state
until R1 is independently source-accepted/merged and a fresh redesigned host
authority receipt is issued/read back.

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
