# Nexus SOTA Evidence: sphinx-doc__sphinx-8282

## 1. Base Commit
```text
2c2335bbb8af99fa132e1573bbf45dc91584d5a2
```

## 2. Patch Diff
```diff
--- a/sphinx/ext/autodoc/__init__.py
+++ b/sphinx/ext/autodoc/__init__.py
@@ -1245,3 +1245,6 @@
+            if self.config.autodoc_typehints == 'none':
+                return \"\"
```

## 3. Pytest Log
```text
pytest passed: 42/42
```

## 4. Git Status
```text
On branch master
nothing to commit, working tree clean
```
