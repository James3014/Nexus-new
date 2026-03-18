#!/usr/bin/env python3
import json
import argparse
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--window", type=int, default=3)
    parser.add_argument("--input", default="ci_benchmark.csv")
    args = parser.parse_args()
    
    project_root = Path.cwd()
    
    # Try to read current health from input CSV
    current_health = 0.0
    try:
        import csv
        with open(args.input, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            healths = [float(r["health"]) for r in reader if r.get("health")]
            if healths:
                current_health = sum(healths) / len(healths)
    except Exception as e:
        print(f"⚠️ Could not read health from {args.input}: {e}")
        current_health = 0.0

    out = project_root / ".nexus" / "learning_velocity.json"
    
    # Load history
    history = []
    if out.exists():
        try:
            old_data = json.loads(out.read_text(encoding="utf-8"))
            history = old_data.get("history", [])
        except:
            pass
            
    if history and history[-1] == current_health:
        # Avoid duplicate entries if running multiple times on same data
        pass
    else:
        history.append(current_health)
        
    window_size = min(len(history), args.window)
    if window_size > 1:
        last_n = history[-window_size:]
        velocity = (last_n[-1] - last_n[0]) / (len(last_n) - 1)
    else:
        velocity = 0.0
        
    # 🧪 [WP-3] Auto-Optimize Injection Logic
    stagnant_rounds = 0
    stagnant_threshold = 3
    
    # Calculate velocity for the last 3 rounds individually to check for stagnation
    if len(history) >= stagnant_threshold:
        # Check if the last 3 entries show no improvement
        recent = history[-stagnant_threshold:]
        # Velocity is stagnant if it's <= 0 for 3 rounds
        # Here we just check if health didn't increase in the last 3 samples
        is_stagnant = True
        for i in range(1, len(recent)):
            if recent[i] > recent[i-1]:
                is_stagnant = False
                break
        
        if is_stagnant:
            print(f"📉 [Auto-Optimize] Stagnation detected ({len(recent)} rounds without improvement).")
            # Inject optimize task into manifest if not already present
            manifest_path = project_root / "task_manifest.yaml"
            if manifest_path.exists():
                import yaml
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                tasks = manifest.get("tasks", [])
                
                # Check if auto.optimize.on_low_learning is already at the end
                if not any(t["id"] == "auto.optimize.injected" for t in tasks):
                    optimize_task = {
                        "id": "auto.optimize.injected",
                        "depends_on": [tasks[-1]["id"]] if tasks else [],
                        "run": "uv run scripts/engine/nexus_cli.py nexus:crystal",
                        "done_when": {"type": "command_rc_zero"},
                        "on_fail": "continue",
                        "max_retry": 1,
                        "ask_policy": "no_ask"
                    }
                    tasks.append(optimize_task)
                    manifest["tasks"] = tasks
                    manifest_path.write_text(yaml.dump(manifest, sort_keys=False), encoding="utf-8")
                    print(f"🚀 [Auto-Optimize] Injected 'auto.optimize.injected' into task_manifest.yaml")

    out.write_text(json.dumps({"current": velocity, "history": history, "last_updated": str(Path(args.input))}, indent=2), encoding="utf-8")
    print(f"✅ Learning Velocity: {velocity:+.2f} (Health: {current_health:.1f})")

if __name__ == "__main__":
    main()
