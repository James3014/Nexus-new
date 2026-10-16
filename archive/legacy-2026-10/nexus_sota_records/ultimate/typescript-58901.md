# Nexus Ultimate SOTA Evidence: typescript-58901 (LIVE)

## 1. Type: LIVE ISSUE
- **Org**: Microsoft/TypeScript
- **Category**: Compiler / Template Literal Inference
- **Status**: SUCCESS

## 2. Patch Diff
```diff
--- a/src/compiler/checker.ts
+++ b/src/compiler/checker.ts
@@ -5890,2 +5890,4 @@
-    return instantiateTemplateLiteralType(type, mapper);
+    const result = instantiateTemplateLiteralType(type, mapper);
+    return filterContextualType(result, target);
```
