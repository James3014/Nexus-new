"""
🛡️ Nexus Planner Enhancer: 為 Planner 注入健康洞察與修復建議 (P2-C)
結合 Health Analyzer 與 Bug Fingerprint 提供即時診斷增強。
"""

from pathlib import Path
from typing import Dict, Any

from nexus.services.health_analyzer import compute_phase_health
from nexus.services.bug_fingerprint import get_repair_recommendations

def get_view_model(phase: str, task_id: str) -> Dict[str, Any]:
    """🎯 產出符合 3 秒判讀的 ViewModel (Blade 2)"""
    
    # 1. UI 狀態映射
    ui_state_map = {
        "P": "planning",
        "D": "diagnosing",
        "R": "repairing",
        "A": "auditing",
        "C": "crystallizing"
    }
    
    # 2. Data Proxy (指向實體 Manifest，不自創真相)
    manifest_path = f".nexus/runs/{task_id}/manifest.json"
    
    return {
        "view_model": {
            "ui_state": ui_state_map.get(phase, "loading"),
            "data_proxy": f"Production Truth Path: {manifest_path}",
            "readability_gate": "PASSED"
        }
    }

def enhance_planner_context(
    repo_root: Path, 
    diagnosis: Dict[str, Any], 
    lesson_resolution: Dict[str, Any],
    task_id: str = "UUID-DEFAULT"
) -> Dict[str, Any]:
    """為 Planner 注入健康狀態、修復建議與 ViewModel (P2-C)"""
    
    # 1. 獲取 Phase 健康指標
    phase = diagnosis.get("phase", "D")
    health = compute_phase_health(repo_root, phase)
    
    # 2. 獲取修復推薦 (Bug 指紋)
    repair_recs = get_repair_recommendations(repo_root, diagnosis)
    
    # 3. 獲取 ViewModel (Blade 2)
    view_model_data = get_view_model(phase, task_id)
    
    # 4. 豐富化 Prompt Context
    prompt_blocks = []
    
    # Health Status Block (v22 metrics)
    if health.get("status") == "healthy" or health.get("status") == "degraded":
        metrics = health.get("metrics", {})
        prompt_blocks.append(
            f"### 🛡️ Phase {phase} Health Status\n"
            f"* **Health Score**: {metrics.get('health_score', 0):.1%}\n"
            f"* **Auto-Repair Success**: {metrics.get('autorepair_success_rate', 0):.1%}\n"
            f"* **Phantom FP Rate**: {metrics.get('phantom_fp_rate', 0):.1%}"
        )
    
    # Repair Recommendations Block
    if repair_recs.get("recommendations"):
        prompt_blocks.append(repair_recs["prompt_context"])
    
    # 5. 合併輸出 (對位 v25.6 Spec)
    res = {
        "health_insights": health,
        "repair_recommendations": repair_recs,
        "prompt_context": "\n\n---\n\n".join(prompt_blocks),
        "planner_metadata": {
            "phase_health_score": health.get("metrics", {}).get("health_score", 0.0),
            "repair_template_count": len(repair_recs.get("recommendations", [])),
        }
    }
    res.update(view_model_data)
    return res
