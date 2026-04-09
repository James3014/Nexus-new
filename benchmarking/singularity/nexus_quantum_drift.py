import numpy as np
import time

class QuantumDriftTest:
    def __init__(self, dim=128, nodes=5000):
        self.dim = dim
        self.nodes = nodes

    def run(self):
        print("--- 🌌 Nexus Singularity Test: Quantum Drift (5000 Nodes vs Extreme Noise) ---")
        base_signal = np.ones(self.dim) * 0.5
        
        # 模擬量子級隨機波動 (高頻、高振幅的柯西分佈噪聲，傳統平均法會直接崩潰)
        print("Status: Injecting Extreme Cauchy Noise into 5000 observation nodes...")
        quantum_noise = np.random.standard_cauchy((self.nodes, self.dim)) * 2.0
        observations = base_signal + quantum_noise
        
        # --- 傳統平均法 (Pre-Belief) ---
        pre_belief_signal = np.mean(observations, axis=0)
        pre_error = np.linalg.norm(pre_belief_signal - base_signal)
        
        # --- Nexus v0.9 Belief-driven Quantum Filtering ---
        start = time.time()
        
        # 1. 透過多維度四分位距 (IQR) 抵抗極端值
        q75, q25 = np.percentile(observations, [75 ,25], axis=0)
        iqr = q75 - q25
        
        # 2. 動態閾值隔離 (Belief Boundary)
        lower_bound = q25 - (1.5 * iqr)
        upper_bound = q75 + (1.5 * iqr)
        
        # 3. 提取有效信號並聚合 (Winsorizing 模擬 Belief 的防禦邊界)
        clipped_obs = np.clip(observations, lower_bound, upper_bound)
        consensus_signal = np.mean(clipped_obs, axis=0)
        
        duration = time.time() - start
        v09_error = np.linalg.norm(consensus_signal - base_signal)
        
        print("-" * 50)
        print(f"Pre-Belief Error (Blind Average): {pre_error:.2f} (Catastrophic Failure)")
        print(f"Nexus v0.9 Error (Belief Filter): {v09_error:.6f}")
        print(f"Consensus Processing Time: {duration*1000:.2f}ms")
        
        if v09_error < 1.0:
            print("🏆 RESULT: QUANTUM DRIFT NULLIFIED. Signal extracted from chaos.")
        else:
            print("❌ RESULT: CONSENSUS SHATTERED.")

if __name__ == '__main__':
    QuantumDriftTest().run()
