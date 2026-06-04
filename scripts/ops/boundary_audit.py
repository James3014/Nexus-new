import os
import re
import sys

# [NEXUS v2.4] Future Lane Boundary Audit
# Goal: Physically block unauthorized imports from experimental to core.

def run_boundary_audit():
    print("--- [NEXUS AUDIT] Future Lane Boundary Check ---")
    core_path = "src/governance/"
    experimental_path = "src/experimental/"
    
    violations = 0
    
    # 規則：experimental 模組不得使用 core 的私有實現
    # 只能通過 public types 或 adapter 溝通
    for root, dirs, files in os.walk(experimental_path):
        for file in files:
            if file.endswith(".rs"):
                path = os.path.join(root, file)
                with open(path, "r") as f:
                    content = f.read()
                    # 搜尋非法引用模式 (例如直接引用 core 內部的 transition_engine)
                    if "crate::governance::transition_engine" in content:
                        print(f"❌ VIOLATION: {path} leaks into private TransitionEngine!")
                        violations += 1
    
    if violations == 0:
        print("✅ BOUNDARY_OK: Future lane is properly isolated.")
        return True
    else:
        print(f"💥 TOTAL_VIOLATIONS: {violations}")
        return False

if __name__ == "__main__":
    if not run_boundary_audit():
        sys.exit(1)
