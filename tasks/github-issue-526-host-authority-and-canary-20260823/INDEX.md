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
| 4 | `TASK-526-D-HOST-CARD-SHA-REBIND r2` | ACTIVE | `c386446703e0b626b0c32a1cd58670c7561e5a209f1ccb25fc0c2251fddf5073` | same stable task; exact three-file Goal-preserving replan |
| 5 | `TASK-526-HOST-1` | BLOCKED | `f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514` | exact accepted/merged D r2 correction + acceptance receipt + Git-tracked/CAS-merged bundle |

## Execution frontier

Only `TASK-526-D-HOST-CARD-SHA-REBIND r2` is dispatchable. It may produce one
three-file source/test Candidate and must stop. The host Card cannot mutate
repository or host state until D is independently accepted/merged and the
separate exact bundle issuance PR is merged/read back.

The Gateway-only local canary performs zero DevSpace effects. The future
DevSpace/ChatGPT-facing action integration remains `SERIALIZE_AFTER:#398`.

No task may self-approve, merge, activate its successor, install/reload the
Gateway, or claim production readiness. Controller continuation does not change
worker `AUTO_CHAIN=false`.
