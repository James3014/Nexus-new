import os
import json

# [SOTA 10/10] Nexus Federation Manager
# Implementation based on Sir's expert "Multi-Repo Federation" principles (Phase 5).

FEDERATION_CONFIG = str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/federation_config.json")

def get_tenant_repos(tenant_id):
    if not os.path.exists(FEDERATION_CONFIG):
        return []
    with open(FEDERATION_CONFIG, "r") as f:
        config = json.load(f)
        return config.get(tenant_id, [])

def add_repo_to_federation(tenant_id, repo_path):
    config = {}
    if os.path.exists(FEDERATION_CONFIG):
        with open(FEDERATION_CONFIG, "r") as f:
            config = json.load(f)
            
    if tenant_id not in config:
        config[tenant_id] = []
        
    if repo_path not in config[tenant_id]:
        config[tenant_id].append(repo_path)
        
    with open(FEDERATION_CONFIG, "w") as f:
        json.dump(config, f, indent=2)
    
    print(f"// Nexus-Federation: Repo [{repo_path}] added to Tenant [{tenant_id}].")

if __name__ == "__main__":
    # Test Federation Setup
    add_repo_to_federation("A", str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/A/repo1"))
    add_repo_to_federation("A", str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/A/repo2"))
    add_repo_to_federation("B", str(__import__("pathlib").Path(__file__).resolve().parents[1] / "workspaces/B/monorepo"))
    
    print(f"// Tenant A Repos: {get_tenant_repos('A')}")
