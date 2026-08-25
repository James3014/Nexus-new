# Issue #398 DevSpace composite source rebind

```yaml
campaign_id: github-issue-398-devspace-composite-rebind-20260826
repository: James3014/Nexus-new
source_repository: James3014/devspace
base_main: 3620db1947b6d9864eefe0555c4de9edbf6c7f6a
base_tree: deeed8206e201cdc94f0c7a6e09f11815a84739d
auto_chain: false
```

| Order | Task | Status | SHA-256 | Dependency |
|---|---|---|---|---|
| 1 | `TASK-398-DEVSPACE-COMPOSITE-SOURCE-REBIND` | ACTIVE | `eb49eb8192828c60dc49c470c3192dfdf9b5c7a2533e815da003b64d04176f18` | exact-blob and cumulative-snapshot attempts preserved as RED; bounded e3b delta-snapshot semantic port active |

## Frontier

The only authorized frontier is the source-only isolated ten-blob compatibility
oracle and, if green, one immutable composite Candidate. Canonical integration,
runtime reload, MCP discovery, E2E, Issue closure, and production claims are not
authorized by this Card. `AUTO_CHAIN=false` applies to the worker/Candidate;
controller continuation and independent verification remain separate.
