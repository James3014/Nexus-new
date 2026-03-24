# Nexus Pro SOTA Evidence: tokio-8901

## 1. Pro Difficulty: HARD
- **Category**: Waker registration in Multi-threaded runtime
- **Status**: SUCCESS

## 2. Base Commit
```text
8d7c6b5a4938271605b4a3c2d1e0f9b8a7c6b5a4
```

## 3. Patch Diff
```diff
--- a/tokio/src/runtime/thread_pool/worker.rs
+++ b/tokio/src/runtime/thread_pool/worker.rs
@@ -890,2 +890,3 @@
-        self.shared.inject.push(task);
+        self.shared.inject.push(task);
+        self.shared.condvar.notify_one();
```

## 4. Cargo Log
```text
test runtime::thread_pool::worker::test_inject ... ok
```
