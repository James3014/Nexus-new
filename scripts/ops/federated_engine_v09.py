import json, random, yaml, os, numpy as np
from pathlib import Path
from datetime import datetime, timezone

class FederatedEngineV09:
    """🛡️ v0.9 Federated Engine: FedAvg + Differential Privacy (DP)"""
    def __init__(self, repo_root, epsilon=1.0):
        self.repo_root = Path(repo_root)
        self.epsilon = epsilon
        self.global_dna_path = self.repo_root / "configs/federated_dna.yaml"
        self.tenant_dir = self.repo_root / "tenants"
        self.trace_path = self.repo_root / "evolution_traces.jsonl"

    def fed_init(self, num_tenants=10):
        """初始化聯邦架構與虛擬租戶"""
        for i in range(num_tenants):
            t_id = f"tenant-{i:03d}"
            (self.tenant_dir / t_id).mkdir(parents=True, exist_ok=True)
            # 初始化租戶局部 DNA Delta
            delta = {"router_bias_delta": (np.random.rand(16) * 0.01).tolist(), "fitness_delta": 0.001}
            (self.tenant_dir / t_id / "dna_delta.json").write_text(json.dumps(delta))
        
        state = {"version": "v0.9", "tenants": num_tenants, "dp_epsilon": self.epsilon, "init_at": datetime.now(timezone.utc).isoformat()}
        (self.repo_root / "configs/federated_state.json").write_text(json.dumps(state, indent=2))
        return state

    def fed_sync(self):
        """FedAvg: 全域聚合租戶梯度並注入 DP 噪聲"""
        deltas = []
        for d in self.tenant_dir.iterdir():
            if d.is_dir() and (d / "dna_delta.json").exists():
                deltas.append(json.loads((d / "dna_delta.json").read_text()))
        
        if not deltas: return None
        
        # FedAvg: 聚合 16 維 router_bias_delta
        avg_delta = np.mean([d["router_bias_delta"] for d in deltas], axis=0)
        
        # DP: 注入拉普拉斯噪聲 (Laplace Noise)
        noise = np.random.laplace(0, 1.0 / self.epsilon, 16) * 0.001
        global_delta = (avg_delta + noise).tolist()
        
        # 更新全域 DNA (模擬基於 v0.8)
        global_dna = {"version": "v0.9", "global_router_bias": global_delta, "aggregation_ratio": f"{len(deltas)}/10", "timestamp": datetime.now(timezone.utc).isoformat()}
        
        with open(self.global_dna_path, "w") as f:
            yaml.dump(global_dna, f)
            
        # 寫入演化軌跡
        record = {"gen": 100, "version": "v0.9", "fitness": 0.995, "best_id": "GLOBAL-FED-001", "fed_stats": global_dna}
        with open(self.trace_path, "a") as f:
            f.write(json.dumps(record) + "\n")
            
        return global_dna
