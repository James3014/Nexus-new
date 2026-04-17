"""
msa_quarantine.py
Writeback Quarantine & Promotion Gate
"""
import json
import os
from typing import Dict, Any

class MSAQuarantine:
    def __init__(self, quarantine_dir: str = "nexus/experiments/msa_routing/quarantine"):
        self.quarantine_dir = quarantine_dir
        os.makedirs(self.quarantine_dir, exist_ok=True)
        
    def add_to_quarantine(self, item_id: str, data: Dict[str, Any]):
        filepath = os.path.join(self.quarantine_dir, f"{item_id.replace('/', '_')}.json")
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
            
    def evaluate_gate(self, acceptance_check_status: str, hallucination_index_status: str) -> bool:
        if acceptance_check_status == "PASS" and hallucination_index_status == "VERIFIED":
            return True
        return False
        
    def promote(self, item_id: str, acceptance_check_status: str, hallucination_index_status: str) -> bool:
        if self.evaluate_gate(acceptance_check_status, hallucination_index_status):
            filepath = os.path.join(self.quarantine_dir, f"{item_id.replace('/', '_')}.json")
            if os.path.exists(filepath):
                with open(filepath, 'r') as f:
                    data = json.load(f)
                print(f"✅ Promoted {item_id} to Main Index.")
                os.remove(filepath)
                return True
        print(f"❌ Rejected {item_id}. acceptance: {acceptance_check_status}, hallucination: {hallucination_index_status}")
        return False
