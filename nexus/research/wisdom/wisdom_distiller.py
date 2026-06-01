import json
import os
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import List, Dict, Any

@dataclass
class WisdomEpisode:
    task_id: str
    best_score: float
    best_params: Dict[str, Any]
    lesson_type: str # 'success' or 'failure'
    context_tags: List[str]

class WisdomDistiller:
    def __init__(self, memory_root: str = "/tmp/nexus_mirror/"):
        self.memory_root = Path(memory_root)
        self.wisdom_pool: List[WisdomEpisode] = []

    def scan_and_distill(self) -> str:
        if not self.memory_root.exists():
            return "❌ [Wisdom] Memory root not found."

        # 🛡️ Hardened: Wait for OS I/O flush during mass concurrency
        import time
        time.sleep(10)
        
        found_files = list(self.memory_root.glob("swarm_unit_*.json"))
        # 如果沒找到 swarm_unit，嘗試掃描全部
        if not found_files:
            found_files = list(self.memory_root.glob("*.json"))
            
        print(f"🔍 [Wisdom] Final Harvest: Scanning {len(found_files)} episodes...")

        for file in found_files:
            try:
                with open(file, 'r') as f:
                    data = json.load(f)
                    # 邏輯：如果得分 > 7.0 視為 Success，否則為 Failure
                    extra = data.get("extra", {})
                    score = data.get("audit_score", extra.get("audit_score", 0))
                    params = (
                        extra.get("optimization_trace", {}).get("suggested_params", {})
                        or extra.get("suggested_params", {})
                    )
                    
                    episode = WisdomEpisode(
                        task_id=data.get('task_id', 'unknown'),
                        best_score=score,
                        best_params=params,
                        lesson_type='success' if score > 7.0 else 'failure',
                        context_tags=data.get('tags', [])
                    )
                    self.wisdom_pool.append(episode)
            except Exception as e:
                print(f"⚠️ [Wisdom] Skip corrupted episode {file.name}: {e}")

        return self.summarize_findings()

    def summarize_findings(self) -> str:
        successes = [e for e in self.wisdom_pool if e.lesson_type == 'success']
        avg_success_score = sum([e.best_score for e in successes]) / len(successes) if successes else 0
        
        report = f"🧪 [Wisdom: Harvest Report]\n"
        report += f"📊 Analyzed: {len(self.wisdom_pool)} episodes\n"
        report += f"✅ Valid Successes: {len(successes)}\n"
        report += f"📈 Average Success Score: {avg_success_score:.2f}\n"
        
        if successes:
            # 簡單智慧：推薦參數平均值
            avg_temp = sum([e.best_params.get("temp", e.best_params.get("temperature", 0)) for e in successes]) / len(successes)
            report += f"🧠 Wisdom Suggestion: For similar tasks, use mean temp={avg_temp:.2f}\n"
            
        return report

if __name__ == "__main__":
    distiller = WisdomDistiller()
    print(distiller.scan_and_distill())
