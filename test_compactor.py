from pathlib import Path
from nexus.core.context_compactor import ContextCompactor

compactor = ContextCompactor(Path("."))
summary = compactor.compact({
    "tasks": {
        "task1": {"id": "task1", "status": "done", "note": "fact1"},
        "task2": {"id": "task2", "status": "failed", "note": "risk1"},
        "task3": {"id": "task3", "status": "pending"}
    }
})
print("COMPACTOR SUMMARY:", summary)
