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
| 3 | `TASK-526-D-HOST-CARD-SHA-REBIND` | ACTIVE | `a5f0fc128e18e12a0524f49aa463b2fe4b5e3f0766f3ff1d3be41564373e07cc` | merged C `7c2e7970`; stale contract hash contradicts actual Host Card |
| 4 | `TASK-526-HOST-1` | BLOCKED | `f4c581f0062c6b3d65c9ca8f7029a96caa76b2e35d95cc6bccae874c0945f514` | exact accepted/merged D correction + acceptance receipt + Git-tracked/CAS-merged bundle |

## Execution frontier

Only `TASK-526-D-HOST-CARD-SHA-REBIND` is dispatchable. It may produce one
two-file source/test Candidate and must stop. The host Card cannot mutate
repository or host state until D is independently accepted/merged and the
separate exact bundle issuance PR is merged/read back.

The Gateway-only local canary performs zero DevSpace effects. The future
DevSpace/ChatGPT-facing action integration remains `SERIALIZE_AFTER:#398`.

No task may self-approve, merge, activate its successor, install/reload the
Gateway, or claim production readiness. Controller continuation does not change
worker `AUTO_CHAIN=false`.
