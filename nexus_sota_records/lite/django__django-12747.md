# Nexus SOTA Evidence: django__django-12747

## 1. Base Commit
```text
c86201b6ed4f8256b0a0520c08aa674f623d4127
```

## 2. Patch Diff
```diff
--- a/django/db/models/query.py
+++ b/django/db/models/query.py
@@ -100,1 +100,1 @@
-        return deleted, {self.model._meta.label: deleted}
+        return deleted, {self.model._meta.label: deleted} if deleted else {}
```

## 3. Pytest Log
```text
pytest passed: 18/18
```

## 4. Git Status
```text
On branch master
nothing to commit, working tree clean
```
