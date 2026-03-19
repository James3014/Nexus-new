from typing import List, Dict, Any
from .state_contracts import NexusState

class AutoRepairEngine:
    @staticmethod
    def analyze_and_suggest(state: NexusState) -> List[Dict[str, Any]]:
        suggestions = []
        
        # 1. Pipeline Health Audit
        if state.pipeline_health < 80:
            suggestions.append({
                "type": "REPAIR_PIPELINE",
                "reason": f"Pipeline health {state.pipeline_health}% is below 80%",
                "action": "nexus:benchmark --framework health-audit",
                "priority": "HIGH"
            })
            
        # 2. Phase-specific Audits
        for phase, metric in state.phase_metrics.items():
            if metric.health > 0 and metric.health < 70:
                suggestions.append({
                    "type": f"REPAIR_PHASE_{phase}",
                    "reason": f"Phase {phase} health {metric.health}% is critical",
                    "action": f"nexus:runner --task repair_phase_{phase}",
                    "priority": "MEDIUM"
                })
                
        # 3. Drift detection
        if state.health_metrics.drift_index > 0.4:
            suggestions.append({
                "type": "RECALIBRATE_EXPECTATIONS",
                "reason": f"Drift index {state.health_metrics.drift_index} exceeded 0.4",
                "action": "nexus:crystal --recalibrate",
                "priority": "HIGH"
            })
            
        state.auto_actions = suggestions
        return suggestions

    @classmethod
    def execute_repairs(cls, state: NexusState):
        actions = cls.analyze_and_suggest(state)
        if not actions:
            return

        import yaml
        from pathlib import Path
        manifest_path = Path.cwd() / "task_manifest.yaml"
        
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f) or {"tasks": []}
            
            existing_ids = {t["id"] for t in manifest.get("tasks", [])}
            added = False

            for action in actions:
                task_id = f"auto.repair.{action['type'].lower()}"
                if task_id not in existing_ids:
                    print(f"🔧 [Auto-Repair] Injecting task: {task_id}")
                    manifest["tasks"].append({
                        "id": task_id,
                        "description": f"AUTO-REPAIR: {action['reason']}",
                        "run": action["action"],
                        "priority": action["priority"],
                        "depends_on": []
                    })
                    added = True
            
            if added:
                with open(manifest_path, "w", encoding="utf-8") as f:
                    yaml.dump(manifest, f, allow_unicode=True, sort_keys=False)
        except Exception as e:
            print(f"⚠️ [Auto-Repair] Failed to inject tasks: {e}")
