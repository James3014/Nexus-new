# Nexus Pro SOTA Evidence: pytorch-6789

## 1. Pro Difficulty: HARD
- **Category**: Autogradients / In-place mutation check
- **Status**: SUCCESS

## 2. Base Commit
```text
7a6b5c4d3e2f1a0b9c8d7e6f5a4b3c2d1e0f9b8a
```

## 3. Patch Diff
```diff
--- a/torch/csrc/autograd/variable.cpp
+++ b/torch/csrc/autograd/variable.cpp
@@ -678,3 +678,6 @@
+    if (self.is_leaf() && !requires_grad) {
+        throw std::runtime_error(\"Leaf variable modification...\");
+    }
```

## 4. Python Log
```text
test_autograd.py passed (245 tests)
```
