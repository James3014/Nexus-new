from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime

class NexusStateLegacyMixin:
    """🛠️ NexusState Legacy Mixin: 提供向後相容的屬性訪問層 (PHA-022)"""
    
    # Proxy attributes for backward compatibility
    # Do not add type hints here as Pydantic may interpret them as field definitions.
    # Uses getattr/setattr to avoid Pyright attribute access errors.
    
    # TokenAccounting
    @property
    def total_token_usage(self) -> int:
        return getattr(self, "tokens").total_usage

    @total_token_usage.setter
    def total_token_usage(self, v: int):
        getattr(self, "tokens").total_usage = v

    @property
    def token_raw_model(self) -> int:
        return getattr(self, "tokens").raw_model

    @token_raw_model.setter
    def token_raw_model(self, v: int):
        getattr(self, "tokens").raw_model = v

    @property
    def token_fallback_est(self) -> int:
        return getattr(self, "tokens").fallback_est

    @token_fallback_est.setter
    def token_fallback_est(self, v: int):
        getattr(self, "tokens").fallback_est = v

    @property
    def token_system_overhead(self) -> int:
        return getattr(self, "tokens").system_overhead

    @token_system_overhead.setter
    def token_system_overhead(self, v: int):
        getattr(self, "tokens").system_overhead = v

    @property
    def token_capture_status(self) -> str:
        return getattr(self, "tokens").capture_status

    @token_capture_status.setter
    def token_capture_status(self, v: str):
        getattr(self, "tokens").capture_status = v

    @property
    def phase_tokens(self) -> Dict[str, int]:
        return getattr(self, "tokens").phase_tokens

    @phase_tokens.setter
    def phase_tokens(self, v: Dict[str, int]):
        getattr(self, "tokens").phase_tokens = v

    # ObservabilityContext
    @property
    def trace_id(self) -> str:
        return getattr(self, "observability").trace_id

    @trace_id.setter
    def trace_id(self, v: str):
        getattr(self, "observability").trace_id = v

    @property
    def span_id(self) -> str:
        return getattr(self, "observability").span_id

    @span_id.setter
    def span_id(self, v: str):
        getattr(self, "observability").span_id = v

    @property
    def auto_actions(self) -> List[Dict[str, Any]]:
        return getattr(self, "observability").auto_actions

    @auto_actions.setter
    def auto_actions(self, v: List[Dict[str, Any]]):
        getattr(self, "observability").auto_actions = v

    # AuditCounters
    @property
    def audit_pass_count(self) -> int:
        return getattr(self, "audit").audit_pass_count

    @audit_pass_count.setter
    def audit_pass_count(self, v: int):
        getattr(self, "audit").audit_pass_count = v

    @property
    def retry_count(self) -> int:
        return getattr(self, "audit").retry_count

    @retry_count.setter
    def retry_count(self, v: int):
        getattr(self, "audit").retry_count = v

    @property
    def turn_count(self) -> int:
        return getattr(self, "audit").turn_count

    @turn_count.setter
    def turn_count(self, v: int):
        getattr(self, "audit").turn_count = v

    @property
    def clarification_count(self) -> int:
        return getattr(self, "audit").clarification_count

    @clarification_count.setter
    def clarification_count(self, v: int):
        getattr(self, "audit").clarification_count = v

    @property
    def correction_count(self) -> int:
        return getattr(self, "audit").correction_count

    @correction_count.setter
    def correction_count(self, v: int):
        getattr(self, "audit").correction_count = v

    @property
    def unresolved_count(self) -> int:
        return getattr(self, "audit").unresolved_count

    @unresolved_count.setter
    def unresolved_count(self, v: int):
        getattr(self, "audit").unresolved_count = v

    # PhaseHealthSnapshot
    @property
    def health_score(self) -> float:
        return getattr(self, "phase_health").health_score

    @health_score.setter
    def health_score(self, v: float):
        getattr(self, "phase_health").health_score = v

    @property
    def health_metrics(self) -> Any: # Type hint Any to avoid circular import if HealthMetrics is complex
        return getattr(self, "phase_health").health_metrics

    @health_metrics.setter
    def health_metrics(self, v: Any):
        getattr(self, "phase_health").health_metrics = v

    @property
    def pipeline_health(self) -> float:
        return getattr(self, "phase_health").pipeline_health

    @pipeline_health.setter
    def pipeline_health(self, v: float):
        getattr(self, "phase_health").pipeline_health = v

    @property
    def learning_velocity(self) -> float:
        return getattr(self, "phase_health").learning_velocity

    @learning_velocity.setter
    def learning_velocity(self, v: float):
        getattr(self, "phase_health").learning_velocity = v

    @property
    def phase_metrics(self) -> Dict[str, Any]:
        return getattr(self, "phase_health").phase_metrics

    @phase_metrics.setter
    def phase_metrics(self, v: Dict[str, Any]):
        getattr(self, "phase_health").phase_metrics = v
    
    # Metadata helpers
    @property
    def last_error(self) -> str:
        return str(getattr(self, "metadata").get("last_error_text", ""))

    @last_error.setter
    def last_error(self, value: str) -> None:
        getattr(self, "metadata")["last_error_text"] = value

    @property
    def last_traceback(self) -> str:
        return str(getattr(self, "metadata").get("last_traceback", ""))

    @last_traceback.setter
    def last_traceback(self, value: str) -> None:
        getattr(self, "metadata")["last_traceback"] = value

    @property
    def review_status(self) -> str:
        return str(getattr(self, "metadata").get("last_review_status", "pending"))

    @review_status.setter
    def review_status(self, value: str) -> None:
        getattr(self, "metadata")["last_review_status"] = value

    @property
    def fault_hash(self) -> str:
        return str(getattr(self, "metadata").get("fault_hash", ""))

    @fault_hash.setter
    def fault_hash(self, value: str) -> None:
        getattr(self, "metadata")["fault_hash"] = value
        
    @property
    def sandbox_hit_rate(self) -> float:
        return float(getattr(self, "metadata").get("sandbox_hit_rate", 0.0))
        
    @sandbox_hit_rate.setter
    def sandbox_hit_rate(self, value: float) -> None:
        getattr(self, "metadata")["sandbox_hit_rate"] = value
