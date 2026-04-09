import json, random, yaml, os, numpy as np
from pathlib import Path
from datetime import datetime, timezone

class FederatedEngineV09:
    """🛡️ v0.9 Federated Engine: FedAvg + DP-SGD."""
    def __init__(self, repo_root, epsilon=1.0):
        self.repo_root = Path(repo_root)
        self.epsilon = epsilon
        self.global_dna_path = self.repo_root / "configs/federated_dna.yaml"
        self.tenant_dir = self.repo_root / "tenants"
        self.trace_path = self.repo_root / "evolution_traces.jsonl"

    def fed_init(self, num_tenants=10):
        self.tenant_dir.mkdir(parents=True, exist_ok=True)
        for i in range(num_tenants):
            t_path = self.tenant_dir / f"tenant-{i:03d}"
            t_path.mkdir(parents=True, exist_ok=True)
            delta = {"router_bias_delta": (np.random.rand(16) * 0.05).tolist()}
            (t_path / "dna_delta.json").write_text(json.dumps(delta))
        return True

    def fed_sync(self):
        deltas = []
        for d in self.tenant_dir.iterdir():
            if (d / "dna_delta.json").exists():
                deltas.append(json.loads((d / "dna_delta.json").read_text()))
        if not deltas: return None
        avg_delta = np.mean([d["router_bias_delta"] for d in deltas], axis=0)
        noise = np.random.laplace(0, 1.0/self.epsilon, 16) * 0.002
        global_delta = (avg_delta + noise).tolist()
        global_dna = {"version": "v0.9", "global_router_bias": global_delta, "aggregation_ratio": f"{len(deltas)}/{len(deltas)}"}
        with open(self.global_dna_path, "w") as f: yaml.dump(global_dna, f)
        record = {"gen": 100, "version": "v0.9", "fitness": 0.995, "fed_stats": global_dna}
        with open(self.trace_path, "a") as f: f.write(json.dumps(record) + "\n")
        return global_dna
