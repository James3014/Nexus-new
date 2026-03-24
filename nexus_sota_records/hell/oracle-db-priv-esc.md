# Nexus Hell SOTA Evidence: oracle-db-priv-esc

## 1. Hell Difficulty: GOD TIER
- **Category**: Oracle DB / PL/SQL / Privilege Escalation
- **Status**: PATCHED
- **Audit**: SAFE

## 2. Patch Diff
```diff
--- a/db/sys/oracle_core.sql
+++ b/db/sys/oracle_core.sql
@@ -10,1 +10,4 @@
-    EXECUTE IMMEDIATE 'GRANT DBA TO ' || :user;
+    IF NOT is_sys_admin() THEN
+        RAISE_APPLICATION_ERROR(-20001, 'Unauthorized');
+    END IF;
+    EXECUTE IMMEDIATE 'GRANT DBA TO ' || :user;
```
