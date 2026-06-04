import os
import sys
import re

def check_dependency_direction():
    """
    🏗️ Architecture Fitness Function: Dependency Rule
    核心原則: 內層 (domain, policy) 絕對禁止依賴外層 (api, lanes, release)。
    """
    inner_layers = ["nexus/domain", "nexus/policy"]
    outer_layers = ["nexus/api", "nexus/lanes", "nexus/release", "nexus/ingress"]
    
    violations = []
    
    for root, dirs, files in os.walk("."):
        if any(inner in root for inner in inner_layers):
            for file in files:
                if file.endswith(".py"):
                    path = os.path.join(root, file)
                    with open(path, "r") as f:
                        content = f.read()
                        for outer in outer_layers:
                            # 偵測如 import nexus.api or from nexus.api
                            pattern = rf"(import|from)\s+{outer.replace('/', '.')}"
                            if re.search(pattern, content):
                                violations.append(f"VIOLATION: {path} depends on outer layer {outer}")
    
    return violations

def check_module_size(limit_lines=200):
    """
    🏗️ Architecture Fitness Function: Module Size
    保持模組「小而美」，超過行數限制則發出警告。
    """
    oversized = []
    for root, dirs, files in os.walk("nexus"):
        for file in files:
            if file.endswith(".py") and "__init__" not in file:
                path = os.path.join(root, file)
                with open(path, "r") as f:
                    lines = f.readlines()
                    if len(lines) > limit_lines:
                        oversized.append(f"OVERSIZED: {path} ({len(lines)} lines) exceeds limit {limit_lines}")
    return oversized

if __name__ == "__main__":
    print("--- 🏗️ Nexus Architecture Fitness Audit ---")
    
    dep_violations = check_dependency_direction()
    size_warnings = check_module_size()
    
    if not dep_violations:
        print("✅ Dependency Direction: PASS (Inner layers remain pure)")
    else:
        for v in dep_violations: print(v)
        
    if not size_warnings:
        print("✅ Module Size Check: PASS (All modules are lean)")
    else:
        for w in size_warnings: print(w)
        
    print("------------------------------------------")
    if dep_violations:
        sys.exit(1)
    sys.exit(0)
