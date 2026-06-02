import json
from pathlib import Path

EVAL_SET = Path("training/frozen_eval_set.jsonl")

def validate_schema():
    print(f"🔍 Validating Schema for {EVAL_SET}...")
    if not EVAL_SET.exists():
        print("❌ File not found.")
        return False
        
    valid_count = 0
    errors = 0
    with open(EVAL_SET, "r") as f:
        for i, line in enumerate(f):
            try:
                record = json.loads(line)
                assert "task_id" in record, "Missing task_id"
                assert "expected_stop_layer" in record, "Missing expected_stop_layer"
                assert "messages" in record, "Missing messages"
                assert len(record["messages"]) >= 3, "Messages should contain system, user, and assistant"
                
                # Verify assistant payload
                assistant_msg = record["messages"][-1]["content"]
                assert "<thought>" in assistant_msg, "Missing <thought> tag"
                assert "next_step" in assistant_msg, "Missing JSON payload for next_step"
                
                valid_count += 1
            except Exception as e:
                print(f"❌ Error at line {i+1}: {e}")
                errors += 1
                
    print(f"✅ Schema validation complete. Valid: {valid_count}, Errors: {errors}")
    return errors == 0

if __name__ == "__main__":
    validate_schema()
