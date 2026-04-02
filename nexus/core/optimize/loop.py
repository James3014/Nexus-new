from pathlib import Path
import json
import yaml

def optimize_loop(project_root: str = "."):
    """
    🔄 Nexus WP4 Optimization Loop
    Synchronizes skill weights between policy_updates.json and skills_router.yaml.
    """
    root = Path(project_root).resolve()
    policy_updates_path = root / "policy_updates.json"
    skills_router_path = root / "configs" / "skills_router.yaml"

    if not policy_updates_path.exists():
        print(f"Skipping optimization: {policy_updates_path} not found.")
        return

    if not skills_router_path.exists():
        print(f"Skipping optimization: {skills_router_path} not found.")
        return

    # 1. Read policy_updates.json
    try:
        with open(policy_updates_path, 'r', encoding='utf-8') as f:
            updates = json.load(f)
    except Exception as e:
        print(f"Error reading {policy_updates_path}: {e}")
        return

    # 2. Read configs/skills_router.yaml
    try:
        with open(skills_router_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f) or {}
    except Exception as e:
        print(f"Error reading {skills_router_path}: {e}")
        return

    # 3. Apply skill_weights adjustments
    updated = False
    new_weights = updates.get("skill_weights", {})
    if new_weights:
        if "skill_weights" not in config:
            config["skill_weights"] = {}
        
        # In-place update
        config["skill_weights"].update(new_weights)
        updated = True
        print(f"Applied weights updates: {new_weights}")

    # 4. Write back to configs/skills_router.yaml
    if updated:
        try:
            with open(skills_router_path, 'w', encoding='utf-8') as f:
                yaml.dump(config, f, default_flow_style=False, sort_keys=False)
            print(f"Successfully updated {skills_router_path}.")
        except Exception as e:
            print(f"Error writing to {skills_router_path}: {e}")

if __name__ == "__main__":
    # If executed as a script, find project root
    import os
    current = Path.cwd()
    project_root = current
    while project_root != project_root.parent:
        if (project_root / "pyproject.toml").exists():
            break
        project_root = project_root.parent
    
    optimize_loop(str(project_root))
