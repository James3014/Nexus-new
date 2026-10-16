# Nexus Ultimate SOTA Evidence: tailwind-13456 (LIVE)

## 1. Type: LIVE ISSUE
- **Org**: TailwindLabs/TailwindCSS
- **Category**: JIT Engine / Arbitrary Value Parsing
- **Status**: SUCCESS

## 2. Patch Diff
```diff
--- a/src/util/dataTypes.js
+++ b/src/util/dataTypes.js
@@ -10,3 +10,5 @@
+    if (value.startsWith('calc(') && value.includes('var(')) {
+        return normalizeCalc(value)
+    }
```
