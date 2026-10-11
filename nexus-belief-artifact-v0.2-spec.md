# 🛡️ Nexus Belief + Artifact + Dependency Graph v0.2

## 核心前提 (Beliefs)
- **Schema**: {id, version, type, content, status, supported_by_artifacts: [], invalidates_artifacts: []}
- **Status**: active, retracted, superseded

## 產出物鏈 (Artifacts)
- **Schema**: {id, version, type, path_ref, status, supersedes_id, linked_beliefs: []}
- **Status**: active, stale, needs_review

## 依賴邊 (Edges)
- **Types**: depends_on, derived_from, supports, conflicts_with, supersedes
- **方向**：邊以 `from_id → to_id` 儲存。belief 與 artifact 之間的邊一律是 `belief → artifact`；belief 被撤回（retracted）或取代（superseded）時，它的 `depends_on` 邊所指向的 artifact 會被標成 stale。實作見 `nexus/core/belief_v02.py`，與既有讀取端 `scripts/ops/brain_loop_closure.py`、predictive healing 一致。
