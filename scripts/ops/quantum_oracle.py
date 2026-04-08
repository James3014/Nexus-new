import json
from pathlib import Path

class QuantumOracle:
    def rank_and_decide(self, simulations: list):
        """Stage 3 & 4: RANK & DECIDE - 計算 EV 並決策"""
        # EV = SuccessRate * (1 / Latency)
        ranked = []
        for s in simulations:
            ev = (s["mcts_metrics"]["success_rate"] * 1000) / s["mcts_metrics"]["latency_ms"]
            ranked.append({**s, "ev": round(ev, 4)})
        
        # 按 EV 排序
        ranked.sort(key=lambda x: x["ev"], reverse=True)
        winner = ranked[0]
        hedge = ranked[1] if len(ranked) > 1 else None
        
        print(f"⚖️ [Oracle] Winner: {winner['universe']} (EV: {winner['ev']})")
        if hedge:
            print(f"🛡️ [Oracle] Hedge Option: {hedge['universe']} (EV: {hedge['ev']})")
            
        return winner, hedge

if __name__ == "__main__":
    print("✅ Quantum Oracle Engine Initialized.")
