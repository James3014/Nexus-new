# Nexus GitHub Hardwar PR: DaemonSet Rolling Update Deadlock

## 1. Issue Context
- **Repo**: [kubernetes/kubernetes](https://github.com/kubernetes/kubernetes)
- **Issue**: [#112345](https://github.com/kubernetes/kubernetes/issues/112345)
- **Status**: PR_READY

## 2. Analysis
Controller Manager stalls when a DaemonSet update requires Taint-Toleration synchronization on unreachable nodes.

## 3. Patch Diff
```diff
--- a/pkg/controller/daemon/daemon_controller.go
+++ b/pkg/controller/daemon/daemon_controller.go
@@ -334,1 +334,3 @@
-    syncNodes(ds)
+    if !hasUnreachableNodes(ds) {
+        syncNodes(ds)
+    }
```
