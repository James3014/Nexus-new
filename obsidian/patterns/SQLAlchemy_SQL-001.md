# [SQLAlchemy] Detached Instance Error
- **ID**: SQL-001
- **Context**: Accessing attributes outside session scope.

## 🛑 Problem (The Bug)
Session closed before secondary attributes are accessed (lazy loading).

## ✅ Solution (The Fix)
Use selectinload or joinedload for eager loading, or keep session context open.

---
#NexusKnowledge #v7 Mastered
