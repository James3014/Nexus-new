# Nexus GitHub Hardwar PR: Circuit Transpiler >4hr Timeout Fix

## 1. Issue Context
- **Repo**: [Qiskit/qiskit](https://github.com/Qiskit/qiskit)
- **Issue**: [#2345](https://github.com/Qiskit/qiskit/issues/2345)
- **Status**: PR_READY

## 2. Analysis
Exponential complexity in the `ConsolidateBlocks` pass when encountering large multi-control gate clusters in Trotterized Hamiltonian circuits.

## 3. Physical Patch
```diff
--- a/qiskit/transpiler/passes/optimization/consolidate_blocks.py
+++ b/qiskit/transpiler/passes/optimization/consolidate_blocks.py
@@ -102,1 +102,3 @@
-    for nodes in find_blocks(dag):
+    for nodes in find_blocks(dag, max_size=MAX_PEEPHOLE_SIZE):
+        consolidate(dag, nodes)
```
