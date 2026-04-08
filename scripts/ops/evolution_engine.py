import json, random, yaml, os
from pathlib import Path
from datetime import datetime, timezone

class EvolutionEngine:
    def __init__(self, repo_root=None):
        self.repo_root = repo_root or Path(__import__("pathlib").Path(__file__).resolve().parents[2])
        self.trace_path = self.repo_root / "evolution_traces.jsonl"
        self.config_path = self.repo_root / "configs/swarm_topology.yaml"

    def evolve_generation(self, count=50):
        # 讀取當前世代
        gen = 0
        if self.trace_path.exists():
            with open(self.trace_path, "r") as f:
                lines = f.readlines()
                if lines: gen = json.loads(lines[-1])["gen"] + 1
        
        # 模擬 DNA 優化：專業化越高、密度越低則 Fitness 越高
        pop = []
        for i in range(count):
            dna = {"density": round(random.uniform(0.2, 0.8), 2), "spec": round(random.uniform(0.5, 0.9), 2)}
            fitness = round((dna["spec"] * 0.7 + (1 - dna["density"]) * 0.3), 4)
            pop.append({"id": f"G{gen}-{i}", "dna": dna, "fitness": fitness})
        
        best = sorted(pop, key=lambda x: x["fitness"], reverse=True)[0]
        with open(self.trace_path, "a") as f:
            f.write(json.dumps({"gen": gen, "fitness": best["fitness"], "best_id": best["id"], "dna": best["dna"]}) + "\n")
        return best

    def deploy_best(self):
        with open(self.trace_path, "r") as f:
            best = json.loads(f.readlines()[-1])
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump({"active_topology": best}, f)
        return best
