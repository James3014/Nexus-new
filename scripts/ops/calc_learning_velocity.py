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

    # 🧪 [v24.0] Bayesian Velocity Integration
    opt_curve = project_root / "optimization_curve.csv"
    bayesian_score = 0.0
    if opt_curve.exists():
        try:
            import csv
            with open(opt_curve, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                scores = [float(r["score"]) for r in reader if r.get("score")]
                if scores:
                    bayesian_score = sum(scores[-3:]) / min(3, len(scores)) # Moving average
        except Exception:
            pass

    out = project_root / ".nexus" / "learning_velocity.json"
    
    # Load history
    history = []
    if out.exists():
        try:
            old_data = json.loads(out.read_text(encoding="utf-8"))
            history = old_data.get("history", [])
        except:
            pass
            
    # Combine health and bayesian score for a true 3D velocity
    blended_metric = (current_health * 0.4) + (bayesian_score * 0.6 * 100) if bayesian_score > 0 else current_health

    if history and history[-1] == blended_metric:
        pass
    else:
        history.append(blended_metric)
        
    window_size = min(len(history), args.window)
    if window_size > 1:
        last_n = history[-window_size:]
        velocity = (last_n[-1] - last_n[0]) / (len(last_n) - 1)
    else:
        velocity = 0.0
        
    # 🧪 [WP-3] Auto-Optimize Injection Logic (v24.0 Bayesian Aware)
    stagnant_rounds = 0
    stagnant_threshold = 3
    
    if len(history) >= stagnant_threshold:
        recent = history[-stagnant_threshold:]
        is_stagnant = True
        for i in range(1, len(recent)):
            if recent[i] > recent[i-1]:
                is_stagnant = False
                break
        
        if is_stagnant:
            print(f"📉 [Auto-Optimize] Bayesian Stagnation detected ({len(recent)} rounds without improvement).")
            manifest_path = project_root / "task_manifest.yaml"
            if manifest_path.exists():
                import yaml
                manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
                tasks = manifest.get("tasks", [])
                
                if not any(t["id"] == "auto.optimize.nightshift" for t in tasks):
                    optimize_task = {
                        "id": "auto.optimize.nightshift",
                        "depends_on": [tasks[-1]["id"]] if tasks else [],
                        "run": "uv run python scripts/nightshift.py --task 'auto-evolve' --target_file 'nexus/core/policy_loader.py'",
                        "done_when": {"type": "command_rc_zero"},
                        "on_fail": "continue",
                        "max_retry": 1,
                        "ask_policy": "no_ask"
                    }
                    tasks.append(optimize_task)
                    manifest["tasks"] = tasks
                    manifest_path.write_text(yaml.dump(manifest, sort_keys=False), encoding="utf-8")
                    print(f"🚀 [Auto-Optimize] Injected 'NightShift Breakwall' into task_manifest.yaml")

    out.write_text(json.dumps({"current": velocity, "history": history, "last_updated": str(Path(args.input))}, indent=2), encoding="utf-8")
    print(f"✅ Learning Velocity (Blended): {velocity:+.2f} (Health: {current_health:.1f}, Bayes: {bayesian_score:.2f})")

if __name__ == "__main__":
    main()
