from pathlib import Path
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore

def seed_real_lesson():
    root = Path(__file__).resolve().parents[2]
    store = FindingsMemoryStore(root)
    
    card = FindingsCard(
        id="lh-12481",
        kind="episodes",
        title="LocalHeal lesson: C_12481 test repair",
        scope="task",
        tags=["local_heal", "test", "repair"],
        stage="learning_closure",
        confidence="medium",
        evidence_paths=["receipt:C_12481"],
        retrieval_hints=["C_12481", "test", "repair"],
        body="Local-heal outcome: test repair success\nTask: C_12481\nSummary: test repair\nReceipt: receipt:C_12481",
        task_id="C_12481",
        extra={
            "lesson_id": "lh-12481",
            "classification": "test_repair",
            "receipt_id": "receipt:C_12481",
            "memory_trace_status": "TRACE_AVAILABLE",
            "retrieved_memory_ids": [],
            "training_export_allowed": False,
            "internal_only": True,
        }
    )
    
    path = store.write(card)
    print(f"Successfully seeded real memory card to: {path}")

if __name__ == "__main__":
    seed_real_lesson()
