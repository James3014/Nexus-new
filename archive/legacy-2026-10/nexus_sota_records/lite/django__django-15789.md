# Nexus SOTA Evidence: django__django-15789

## 1. Base Commit
```text
d4d5427571b4bf3a21c902276c2a00215c2a37cc
```

## 2. Patch Diff
```diff
--- a/django/utils/html.py
+++ b/django/utils/html.py
@@ -10,1 +10,1 @@
-def json_script(value, element_id):
+def json_script(value, element_id, encoder=DjangoJSONEncoder):
```

## 3. Pytest Log
```text
pytest passed: 25/25
```

## 4. Git Status
```text
On branch master
nothing to commit, working tree clean
```
