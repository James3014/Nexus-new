from typing import Dict, Any
from nexus.core.state_contracts import NexusState

class TokenAccumulator:
    def record(self, state: NexusState, phase: str, res_data: Dict[str, Any], overhead: int = 0):
        if phase not in ["P", "D", "X", "R", "A", "C"]:
            raise ValueError(f"Invalid phase: {phase}")
        
        # Robust extraction
        raw = res_data.get("token_raw_model", 0)
        fallback = res_data.get("token_fallback_est", 0)
        
        # If the handler only provided 'tokens_used', we need to decide where to put it
        total_reported = res_data.get("tokens_used", 0)
        if raw == 0 and fallback == 0 and total_reported > 0:
            # Default to fallback if not specified
            fallback = total_reported
            
        status = res_data.get("token_capture_status") or "unknown"
        if status == "unknown" and (raw > 0 or fallback > 0):
            status = "ok" if raw > 0 else "fallback_est"
            
        # Update State
        state.token_raw_model += raw
        state.token_fallback_est += fallback
        state.token_system_overhead += overhead
        
        # Cumulative status: if any phase had a warning, preserve it? 
        # For simplicity, we keep the last one but ensure it's not empty
        state.token_capture_status = status
        
        # Calculate phase and total
        phase_total = raw + fallback + overhead
        state.phase_tokens[phase] = state.phase_tokens.get(phase, 0) + phase_total
        state.total_token_usage = state.token_raw_model + state.token_fallback_est + state.token_system_overhead
        return phase_total

