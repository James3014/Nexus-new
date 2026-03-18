from typing import List, Dict, Any
from .state_contracts import NexusState
from .phase_health import PhaseHealthCalculator

class AutoRepairEngine:
    @staticmethod
    def analyze_and_suggest(state: NexusState) -> List[Dict[str, Any]]:
        suggestions = []
        
        # PI-1: Dynamic threshold could be used here if needed
        # For now, following WP-2 specification: pipeline < 88 or phase < 85
        
        # 1. Pipeline Health Audit
        if state.pipeline_health < 88:
            suggestions.append({
                "type": "REPAIR_PIPELINE",
                "reason": f"Pipeline health {state.pipeline_health}% is below 88%",
                "action": "nexus:benchmark --framework health-audit",
                "priority": "HIGH"
            })
            
        # 2. Phase-specific Audits
        for phase, metric in state.phase_metrics.items():
            if metric.health > 0 and metric.health < 85:
                suggestions.append({
                    "type": f"REPAIR_PHASE_{phase}",
                    "reason": f"Phase {phase} health {metric.health}% is below 85%",
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
        import subprocess
        for action in actions:
            cmd = action["action"]
            print(f"🔧 [Auto-Repair] Executing: {action['type']} -> {cmd}")
            try:
                # 🛡️ v9 Hardening: Avoid nested runner locks by checking if we're already in a runner
                # But here we assume it's safe because it's a benchmark or a specific repair task.
                res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=300)
                if res.returncode == 0:
                    print(f"✅ [Auto-Repair] {action['type']} SUCCESS.")
                else:
                    print(f"❌ [Auto-Repair] {action['type']} FAILED (rc={res.returncode}).")
                    print(res.stderr)
            except Exception as e:
                print(f"❌ [Auto-Repair] Error executing {action['type']}: {e}")
