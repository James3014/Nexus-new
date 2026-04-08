import time
import random
from typing import Dict

def run_scale_simulation(count: int = 15, accelerated: bool = True) -> Dict[str, float]:
    """🛡️ [v0.5] 模擬跨租戶規模化共識與共享指標"""
    # 模擬高壓處理時間
    if not accelerated:
        time.sleep(2) # 正常模式較慢
    
    # 模擬 15 個 Swarm 的實際產出指標
    # L4 的核心價值：越多 Swarm 參與，Hit Rate 越高
    hit_rate = random.uniform(65.0, 78.0) 
    p95_time = random.uniform(12.0, 45.0) # p95 延遲 (秒)
    revocation_rate = random.uniform(0.1, 0.4) # 撤銷率
    quarantine_rate = random.uniform(1.2, 3.5) # 隔離率
    
    return {
        "hit_rate": hit_rate,
        "p95_time": p95_time,
        "revocation_rate": revocation_rate,
        "quarantine_rate": quarantine_rate
    }

if __name__ == "__main__":
    res = run_scale_simulation(count=15)
    print(res)
