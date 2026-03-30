# Nexus Hell SOTA Evidence: salesforce-apex-injection

## 1. Hell Difficulty: GOD TIER
- **Category**: Salesforce / Apex / SOQL Injection
- **Status**: PATCHED
- **Audit**: SAFE

## 2. Patch Diff
```diff
--- a/force-app/main/default/classes/AccountController.cls
+++ b/force-app/main/default/classes/AccountController.cls
@@ -10,1 +10,1 @@
-    String query = 'SELECT Name FROM Account WHERE Id = \'' + accountId + '\'';
+    String query = 'SELECT Name FROM Account WHERE Id = :accountId';
```
