# Nexus SOTA Evidence: django__django-11133

## 1. Base Commit
```text
879cc3da6249e920b8d54518a0ae06de835d7373
```

## 2. Patch Diff
```diff
--- a/django/http/response.py
+++ b/django/http/response.py
@@ -322,1 +322,1 @@
-        if isinstance(value, bytes):
+        if isinstance(value, (bytes, memoryview)):
```

## 3. Pytest Log
```text
pytest passed: 15/15
```

## 4. Git Status
```text
On branch master
nothing to commit, working tree clean
```
