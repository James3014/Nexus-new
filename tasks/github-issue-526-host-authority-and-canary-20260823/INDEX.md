# Issue #526 host authority and local canary index

```yaml
campaign_id: github-issue-526-host-authority-and-canary-20260823
repository: James3014/Nexus-new
base_main: ac4a9ab1e0180170ca062cdc81f2142bca8bd80f
base_tree: db329f4931b55b74f1e1f9fe61f7edf4ca8422bc
auto_chain: false
```

| Order | Task | Status | SHA-256 | Dependency |
|---|---|---|---|---|
| 1 | `TASK-526-B-AUTHORITY` | ACTIVE | `477317e723493ad1f1a12035199c2aa55c39973564f71c918fb818c5fa9da366` | merged Slice A `ac4a9ab1` |
| 2 | `TASK-526-HOST-1` | BLOCKED | `fcd22da4ef92b7cde004523fe900c06bc1b9e67715049c95383c581e640f631f` | exact accepted/merged authority contract + acceptance receipt + Git-tracked/CAS-merged host receipt |

## Execution frontier

Only `TASK-526-B-AUTHORITY` is dispatchable. It may produce one four-file
source/test Candidate and must stop. The host Card cannot mutate repository or
host state until the authority Candidate is independently accepted and merged.

The Gateway-only local canary performs zero DevSpace effects. The future
DevSpace/ChatGPT-facing action integration remains `SERIALIZE_AFTER:#398`.

No task may self-approve, merge, activate its successor, install/reload the
Gateway, or claim production readiness. Controller continuation does not change
worker `AUTO_CHAIN=false`.
