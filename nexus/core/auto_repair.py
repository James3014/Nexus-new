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
        # In a real implementation, this would trigger subprocesses
        # For prototype, we just log them
        for action in actions:
            print(f"🔧 [Auto-Repair] Suggested Action: {action['type']} -> {action['action']}")
