# Nexus SOTA Evidence: django__django-15996

## 1. Base Commit
```text
b30c0081d4d8a31ab7dc7f72a4c7099af606ef29
```

## 2. Patch Diff
```diff
--- a/django/db/migrations/serializer.py
+++ b/django/db/migrations/serializer.py
@@ -120,3 +120,6 @@
+            if hasattr(self.value, \"_decompose\"):
+                return self.value._decompose()
```

## 3. Pytest Log
```text
pytest passed: 21/21
```

## 4. Git Status
```text
On branch master
nothing to commit, working tree clean
```
