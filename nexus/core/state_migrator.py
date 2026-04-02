from typing import Any, Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

class StateMigrator:
    """
    🔄 Nexus State Migrator
    負責將舊版的狀態字典映射為新版結構 (v2.0.0+)。
    """
    
    @staticmethod
    def migrate(data: Any) -> Any:
        if not isinstance(data, dict):
            return data
            
        # 1. Mapping Token Fields
        tokens = data.get('tokens', {})
        if not isinstance(tokens, dict):
            tokens = tokens.model_dump() if hasattr(tokens, 'model_dump') else {}
            
        token_map = [
            ('total_token_usage', 'total_usage'),
            ('token_raw_model', 'raw_model'),
            ('token_fallback_est', 'fallback_est'),
            ('token_system_overhead', 'system_overhead'),
            ('token_capture_status', 'capture_status'),
            ('phase_tokens', 'phase_tokens'),
        ]
        for legacy_key, new_key in token_map:
            if legacy_key in data:
                tokens[new_key] = data.pop(legacy_key)
        if tokens:
            data['tokens'] = tokens

        # 2. Mapping Observability
        observability = data.get('observability', {})
        if not isinstance(observability, dict):
            observability = observability.model_dump() if hasattr(observability, 'model_dump') else {}
            
        obs_map = [
            ('trace_id', 'trace_id'),
            ('span_id', 'span_id'),
            ('auto_actions', 'auto_actions'),
        ]
        for legacy_key, new_key in obs_map:
            if legacy_key in data:
                observability[new_key] = data.pop(legacy_key)
        if observability:
            data['observability'] = observability

        # 3. Mapping Audit
        audit = data.get('audit', {})
        if not isinstance(audit, dict):
            audit = audit.model_dump() if hasattr(audit, 'model_dump') else {}
            
        audit_map = [
            ('audit_pass_count', 'audit_pass_count'),
            ('retry_count', 'retry_count'),
            ('turn_count', 'turn_count'),
            ('clarification_count', 'clarification_count'),
            ('correction_count', 'correction_count'),
            ('unresolved_count', 'unresolved_count'),
        ]
        for legacy_key, new_key in audit_map:
            if legacy_key in data:
                audit[new_key] = data.pop(legacy_key)
        if audit:
            data['audit'] = audit

        # 4. Mapping Phase Health
        phase_health = data.get('phase_health', {})
        if not isinstance(phase_health, dict):
            phase_health = phase_health.model_dump() if hasattr(phase_health, 'model_dump') else {}
            
        health_map = [
            ('health_score', 'health_score'),
            ('health_metrics', 'health_metrics'),
            ('pipeline_health', 'pipeline_health'),
            ('learning_velocity', 'learning_velocity'),
            ('phase_metrics', 'phase_metrics'),
        ]
        for legacy_key, new_key in health_map:
            if legacy_key in data:
                phase_health[new_key] = data.pop(legacy_key)
        if phase_health:
            data['phase_health'] = phase_health

        return data
