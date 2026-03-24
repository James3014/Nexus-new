# Nexus GitHub Hardwar PR: Runtime Panic Under High Contention

## 1. Issue Context
- **Repo**: [tokio-rs/tokio](https://github.com/tokio-rs/tokio)
- **Issue**: [#1890](https://github.com/tokio-rs/tokio/issues/1890)
- **Status**: PR_READY

## 2. Analysis
Panic in `Steal` logic when multiple workers attempt to access a near-empty injection queue during a global runtime shutdown.

## 3. Physical Patch
```diff
--- a/tokio/src/runtime/scheduler/multi_thread/worker.rs
+++ b/tokio/src/runtime/scheduler/multi_thread/worker.rs
@@ -145,3 +145,5 @@
+    if self.core.is_shutdown() {
+        return None;
+    }
```
