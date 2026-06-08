from typing import Dict, Any

class BranchPromptBuilder:
    """
    🛡️ BranchPromptBuilder: 分支指令生成器
    根據分支角色 (branch_role) 生成差異化指令，確保並行探索的多樣性。
    """
    
    ROLES = {
        "branch_a": {
            "name": "conservative_patch",
            "instruction": "GOAL: Minimalist repair. Change only what is strictly necessary. Priority: Maintain existing invariants and API stability."
        },
        "branch_b": {
            "name": "semantic_patch",
            "instruction": "GOAL: Deep semantic repair. Focus on recursive logic, operator overloading (&/|), and complex dependency propagation."
        },
        "branch_c": {
            "name": "plan_first_patch",
            "instruction": "GOAL: Structural repair. You MUST output a complete RepairPlan JSON before the code diff. Focus on high-level architectural alignment."
        }
    }

    def build_branch_prompt(self, base_prompt: str, role_id: str) -> str:
        role_data = self.ROLES.get(role_id)
        if not role_data:
            return base_prompt
            
        return (
            f"{base_prompt}\n\n"
            f"--- [BRANCH ROLE: {role_data['name']}] ---\n"
            f"{role_data['instruction']}\n"
        )
