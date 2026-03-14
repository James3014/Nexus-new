# [FastAPI] Dependency Override Failure
- **ID**: FAST-001
- **Context**: Testing FastAPI endpoints with dependency overrides.

## 🛑 Problem (The Bug)
App is instantiated before overrides are applied in tests.

## ✅ Solution (The Fix)
Use app.dependency_overrides[dependency] = mock_dep inside test function or fixture.

---
#NexusKnowledge #v7 Mastered
