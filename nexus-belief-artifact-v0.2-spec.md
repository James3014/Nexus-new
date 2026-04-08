# 🛡️ Nexus Belief + Artifact + Dependency Graph v0.2

## 核心前提 (Beliefs)
- **Schema**: {id, version, type, content, status, supported_by_artifacts: [], invalidates_artifacts: []}
- **Status**: active, retracted, superseded

## 產出物鏈 (Artifacts)
- **Schema**: {id, version, type, path_ref, status, supersedes_id, linked_beliefs: []}
- **Status**: active, stale, needs_review

## 依賴邊 (Edges)
- **Types**: depends_on, derived_from, supports, conflicts_with, supersedes
