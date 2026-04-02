from pathlib import Path
import json
from nexus.core.policy.learning import PolicyLearner


def test_policy_learning(tmp_path):
    # Setup mock episodic_memory.jsonl
    memory_file = tmp_path / "episodic_memory.jsonl"
    output_file = tmp_path / "policy_updates.json"
    
    data = [
        {"selected_skill": "skill_excellent", "success": True, "health": 95.0},
        {"selected_skill": "skill_excellent", "success": True, "health": 98.0},
        {"selected_skill": "skill_low_health", "success": True, "health": 70.0},
        {"selected_skill": "skill_low_health", "success": True, "health": 75.0},
        {"selected_skill": "skill_low_success", "success": False, "health": 85.0},
        {"selected_skill": "skill_low_success", "success": True, "health": 85.0},
    ]
    
    with open(memory_file, "w", encoding="utf-8") as f:
        for entry in data:
            f.write(json.dumps(entry) + "\n")
            
    # Run learning.py
    learner = PolicyLearner(memory_path=str(memory_file), output_path=str(output_file))
    updates = learner.learn()
    
    # Verify results
    assert output_file.exists()
    
    with open(output_file, "r", encoding="utf-8") as f:
        results = json.load(f)
        
    weights = results.get("skill_weights", {})
    
    # skill_excellent: health > 90 and success > 0.95 -> adjustment +0.5
    assert weights.get("skill_excellent") == 0.5
    
    # skill_low_health: avg health = (70+75)/2 = 72.5. Adjustment = -(80 - 72.5)/20 = -7.5/20 = -0.375 -> rounded to -0.38
    assert weights.get("skill_low_health") == -0.38
    
    # skill_low_success: success_rate = 0.5 < 0.8. Adjustment = -1.0
    # Also health = 85.0 (no adjustment for health)
    assert weights.get("skill_low_success") == -1.0
