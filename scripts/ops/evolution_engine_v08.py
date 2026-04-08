import json, random, yaml, os, numpy as np
from pathlib import Path
from datetime import datetime, timezone

class MetaOptimizerV08:
    """🛡️ v0.8 Meta-Optimizer: HyperNEAT Evolution Policy"""
    def __init__(self, dna_dim=128):
        self.dna_dim = dna_dim
        self.mutation_rate = 0.05
        self.selection_pressure = 0.7

    def calculate_fitness(self, dna_vec):
        """多目標 Fitness: 0.4*latency + 0.3*hit_rate + 0.2*cost + 0.1*stability"""
        # 模擬從 128 維 DNA 映射到效能指標
        # 假設前 32 維影響 latency, 次 32 維影響 hit_rate...
        latency = np.mean(dna_vec[:32]) * 0.95
        hit_rate = np.mean(dna_vec[32:64]) * 0.98
        cost = np.mean(dna_vec[64:96]) * 0.90
        stability = np.mean(dna_vec[96:]) * 0.99
        
        score = (latency * 0.4) + (hit_rate * 0.3) + (cost * 0.2) + (stability * 0.1)
        return round(float(score), 4)

    def mutate_policy(self, success_rate):
        """Meta-Mutation: 進化『進化策略』"""
        if success_rate < 0.5:
            self.mutation_rate *= 1.1  # 增加探索
        else:
            self.mutation_rate *= 0.9  # 增加開發
        return self.mutation_rate

class EvolutionEngineV08:
    """🧬 v0.8 Evolution Engine: Meta-Learning Production Implementation"""
    def __init__(self, repo_root):
        self.repo_root = Path(repo_root)
        self.trace_path = self.repo_root / "evolution_traces.jsonl"
        self.config_path = self.repo_root / "configs/swarm_topology.yaml"
        self.meta_opt = MetaOptimizerV08()

    def meta_evolve(self, count=128):
        """執行 v0.8 Meta-Evolution"""
        gen = 0
        if self.trace_path.exists():
            with open(self.trace_path, "r") as f:
                lines = f.readlines()
                if lines: gen = json.loads(lines[-1]).get("gen", 0) + 1
        
        pop = []
        for i in range(count):
            # 生成 128 維 DNA
            dna_vec = np.random.rand(128).tolist()
            fitness = self.meta_opt.calculate_fitness(dna_vec)
            pop.append({"id": f"v0.8-G{gen}-{i}", "dna_vec": dna_vec, "fitness": fitness})
        
        # 篩選優秀基因
        best = sorted(pop, key=lambda x: x["fitness"], reverse=True)[0]
        
        # Meta-Update: 根據本代最高 Fitness 更新進化策略
        self.meta_opt.mutate_policy(best["fitness"])
        
        record = {
            "gen": gen,
            "version": "v0.8",
            "fitness": best["fitness"],
            "best_id": best["id"],
            "meta_params": {
                "mutation_rate": self.meta_opt.mutation_rate,
                "dna_dim": 128
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        with open(self.trace_path, "a") as f:
            f.write(json.dumps(record) + "\n")
        
        return record

    def deploy_v08(self, best_record):
        """部署 v0.8 生產拓撲"""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump({"active_topology": best_record}, f)
        return True
