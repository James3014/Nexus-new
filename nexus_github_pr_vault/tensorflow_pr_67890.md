# GitHub PR: [TF Debugger] Mitigate NaN accumulation in Sparse Gradient Instrumentation

## PR Details
- **Repo**: tensorflow/tensorflow
- **Branch**: `nexus-nan-debugger-67890`
- **Status**: PR_READY

## Commit Message
```text
python/debug: Fix NaN drift in Sparse Gradient Instrumentation

Clip extreme gradients and use compat v1 where-clause to ensure 
numerical stability during Debugger V2 instrumentation of 
nested sparse tensors.
```

## PR Description
Previously, Debugger V2 could introduce `NaN` values into the `GradientTape` 
when instrumenting sparse tensors with high epsilon values. 
This PR adds clipping and ensures zero-fill for NaN detections.

## Implementation
```bash
git checkout -b nexus-nan-debugger-67890
git apply <<PATCH
--- a/tensorflow/python/debug/util/instrumentation.py
+++ b/tensorflow/python/debug/util/instrumentation.py
@@ -102,1 +102,3 @@
-    return tf.where(tf.is_nan(grad), 0.0, grad)
+    if tf.executing_eagerly():
+        grad = tf.clip_by_value(grad, -1e30, 1e30)
+    return tf.compat.v1.where(tf.is_nan(grad), tf.zeros_like(grad), grad)
PATCH
git commit -m \"python/debug: Fix NaN drift in Sparse Gradient Instrumentation\"
```
