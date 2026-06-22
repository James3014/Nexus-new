from pathlib import Path
from nexus.research.findings_memory import FindingsCard, FindingsMemoryStore

def seed_real_lessons():
    root = Path(__file__).resolve().parents[2]
    store = FindingsMemoryStore(root)
    
    # 1. C_12481 card
    card_12481 = FindingsCard(
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
    path_12481 = store.write(card_12481)
    print(f"Successfully seeded real memory card 12481 to: {path_12481}")

    # 2. C_13453 card
    card_13453 = FindingsCard(
        id="lh-13453",
        kind="episodes",
        title="LocalHeal lesson: C_13453 test repair",
        scope="task",
        tags=["local_heal", "test", "repair"],
        stage="learning_closure",
        confidence="medium",
        evidence_paths=["receipt:C_13453"],
        retrieval_hints=["C_13453", "test", "repair"],
        body="Local-heal outcome: test repair success\nTask: C_13453\nSummary: test repair\nReceipt: receipt:C_13453",
        task_id="C_13453",
        extra={
            "lesson_id": "lh-13453",
            "classification": "test_repair",
            "receipt_id": "receipt:C_13453",
            "memory_trace_status": "TRACE_AVAILABLE",
            "retrieved_memory_ids": [],
            "training_export_allowed": False,
            "internal_only": True,
        }
    )
    path_13453 = store.write(card_13453)
    print(f"Successfully seeded real memory card 13453 to: {path_13453}")

if __name__ == "__main__":
    seed_real_lessons()
