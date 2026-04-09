import json, random, yaml, os, numpy as np
from pathlib import Path
from datetime import datetime, timezone

class MetaOptimizerV08:
    def __init__(self, dna_dim=128):
        self.mutation_rate = 0.05
    def calculate_fitness(self, dna):
        return round(float(np.mean(dna)), 4)

class EvolutionEngineV08:
    """🛡️ v0.8 Meta-Learning Engine."""
    def __init__(self, repo_root):
        self.repo_root = Path(repo_root)
        self.trace_path = self.repo_root / "evolution_traces.jsonl"
        self.meta_opt = MetaOptimizerV08()

    def meta_evolve(self, count=128, hybrid_ratio=0.6):
        pop = []
        for i in range(count):
            dna = np.random.rand(128).tolist()
            pop.append({"dna": dna, "fitness": self.meta_opt.calculate_fitness(dna)})
        best = sorted(pop, key=lambda x: x["fitness"], reverse=True)[0]
        gen = len(self.trace_path.read_text().splitlines()) if self.trace_path.exists() else 0
        record = {"gen": gen, "version": "v0.8", "fitness": best["fitness"]}
        with open(self.trace_path, "a") as f: f.write(json.dumps(record) + "\n")
        return record
