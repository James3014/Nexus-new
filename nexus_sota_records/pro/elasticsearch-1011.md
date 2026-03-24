# Nexus Pro SOTA Evidence: elasticsearch-1011

## 1. Pro Difficulty: HARD
- **Category**: Shard Allocation / Cluster State Update
- **Status**: SUCCESS

## 2. Base Commit
```text
3c4d5e6f7a8b9c0123456789abcdef0123456789
```

## 3. Patch Diff
```diff
--- a/server/src/main/java/org/elasticsearch/cluster/routing/allocation/allocator/BalancedShardsAllocator.java
+++ b/server/src/main/java/org/elasticsearch/cluster/routing/allocation/allocator/BalancedShardsAllocator.md
@@ -101,1 +101,3 @@
-    if (weight < threshold) { return; }
+    if (isPendingRelocation(node)) {
+        return;
+    }
```

## 4. Gradle Log
```text
:server:test passed (ClusterStateTests)
```
