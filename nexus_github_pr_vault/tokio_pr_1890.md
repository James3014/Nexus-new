# GitHub PR: [runtime] Prevent panic in worker steal logic during shutdown

## PR Details
- **Repo**: tokio-rs/tokio
- **Branch**: `nexus-runtime-panic-1890`
- **Status**: PR_READY

## Commit Message
```text
runtime: Check shutdown state in worker steal logic

Ensure that the worker does not attempt to steal from the 
injection queue if the runtime core is in a shutdown state, 
preventing a race condition panic.
```

## PR Description
Addresses [#1890] where a high contention scenario during worker shutdown 
could trigger an out-of-bounds access in the injection queue.
