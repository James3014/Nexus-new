# Nexus SOTA Evidence: sympy__sympy-14024

## 1. Base Commit
```text
b17abcb09cbcee80a90f6750e0f9b53f0247656c
```

## 2. Patch Diff
```diff
--- a/sympy/core/power.py
+++ b/sympy/core/power.py
@@ -900,1 +900,1 @@
-        if force or e.is_integer:
+        if force or e.is_integer or b.is_polar:
```

## 3. Pytest Log
```text
pytest-3.4.1 passed: 342/342 (100%)
```

## 4. Git Status
```text
On branch master
nothing to commit, working tree clean
```
