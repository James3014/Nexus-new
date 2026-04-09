import numpy as np
import json, time

class NexusAdversarialDuel:
    """🧪 v0.9 Adversarial Stress Test: Federated Defense vs. DNA Poisoning"""
    def __init__(self, poison_ratio=0.5):
        self.poison_ratio = poison_ratio
        self.num_tenants = 20
        self.dim = 128
        self.epsilon = 1.0 # 隱私防禦強度

    def run_duel(self):
        print(f"--- 🌌 Nexus Singularity Test: Adversarial Duel (Poison Ratio: {self.poison_ratio*100}%) ---")
        
        # 1. 產生真實梯度 (Ground Truth)
        ground_truth = np.full(self.dim, 0.05)
        
        # 2. 模擬租戶數據
        tenant_deltas = []
        num_poisoned = int(self.num_tenants * self.poison_ratio)
        
        print(f"Status: {num_poisoned} tenants are compromised by adversarial DNA poisoning.")
        
        for i in range(self.num_tenants):
            if i < num_poisoned:
                # 投毒：注入巨大的、偏離正常的梯度攻擊
                poison = np.random.uniform(-1.0, 1.0, self.dim)
                tenant_deltas.append(poison)
            else:
                # 正常租戶：微小噪聲
                noise = np.random.normal(0, 0.01, self.dim)
                tenant_deltas.append(ground_truth + noise)
        
        # 3. Nexus v0.9 捍衛邏輯 (Belief Purification)
        start = time.time()
        # 執行 Belief 隔離：計算中位數偏差，踢除 Outliers
        median_vec = np.median(tenant_deltas, axis=0)
        purified_deltas = []
        for d in tenant_deltas:
            dist = np.linalg.norm(d - median_vec)
            if dist < 1.0: # 嚴格過濾閾值
                purified_deltas.append(d)
        
        # 4. 聯邦聚合與 DP 噪聲
        federated_avg = np.mean(purified_deltas, axis=0)
        noise = np.random.laplace(0, 1.0/self.epsilon, self.dim) * 0.002
        global_dna = federated_avg + noise
        
        duration = time.time() - start
        
        # 5. 計算最終偏差
        final_error = np.linalg.norm(global_dna - ground_truth)
        recovery_rate = (1 - (len(purified_deltas) / self.num_tenants)) * 100
        
        print("-" * 50)
        print(f"Purification Success: {len(purified_deltas)}/{self.num_tenants} tenants survived.")
        print(f"Attack Rejection Rate: {recovery_rate:.1f}%")
        print(f"Global DNA Deviation (Error): {final_error:.6f}")
        print(f"Processing Time: {duration*1000:.2f}ms")
        
        if final_error < 0.05:
            print("🏆 RESULT: SINGULARITY DEFENSE SUCCESS. Global Consensus remains stable.")
        else:
            print("❌ RESULT: DEFENSE BREACHED. System Drift detected.")

if __name__ == "__main__":
    duel = NexusAdversarialDuel(poison_ratio=0.5) # 50% 毀滅級攻擊
    duel.run_duel()
