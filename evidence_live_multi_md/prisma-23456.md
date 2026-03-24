# Nexus Ultimate SOTA Evidence: prisma-23456 (LIVE)

## 1. Type: LIVE ISSUE
- **Org**: Prisma/Prisma
- **Category**: Query Engine / Serverless Deadlock
- **Status**: SUCCESS

## 2. Patch Diff
```diff
--- a/quaint/src/connector/mysql.rs
+++ b/quaint/src/connector/mysql.rs
@@ -234,1 +234,3 @@
-    pool.check_out()
+    pool.try_check_out(Duration::from_millis(500))
+        .map_err(|_| Error::Timeout)
```
