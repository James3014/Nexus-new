# [pytest] Async Fixture Scope Mismatch
- **ID**: PYT-001
- **Context**: Using async fixtures with different scopes.

## 🛑 Problem (The Bug)
Scope mismatch when async fixture depends on a module-scoped fixture.

## ✅ Solution (The Fix)
Ensure all dependent async fixtures share compatible scopes or use pytest-asyncio strict mode.

---
#NexusKnowledge #v7 Mastered
