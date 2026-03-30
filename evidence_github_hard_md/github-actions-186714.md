# Nexus GitHub Hardwar PR: Workflow Unsolved Convo Bug

## 1. Issue Context
- **Repo**: [github/docs](https://github.com/github/docs)
- **Issue**: [#186714](https://github.com/github/docs/issues/186714)
- **Status**: PR_READY

## 2. Analysis
API regression in Actions Workflow parser failing to resolve nested reusable workflows when comment-based metadata is malformed.

## 3. Physical Patch
```diff
--- a/src/actions/workflow_parser.js
+++ b/src/actions/workflow_parser.js
@@ -56,1 +56,3 @@
-    return resolveWorkflow(entry.path);
+    const sanitizedPath = entry.path.replace(/#.*$/, '');
+    return resolveWorkflow(sanitizedPath);
```
