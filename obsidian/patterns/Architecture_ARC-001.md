# [Architecture] Circular Dependency in Decoupled Systems
- **ID**: ARC-001
- **Context**: Commander vs ContextHub inter-dependency.

## 🛑 Problem (The Bug)
Importing module A in B and vice-versa during initialization.

## ✅ Solution (The Fix)
Use local imports inside methods or move common types to a dedicated constants/types module.

---
#NexusKnowledge #v7 Mastered
