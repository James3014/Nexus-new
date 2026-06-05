import logging
import os
from typing import Any, Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)

class ModelProfile:
    """
    Model configuration profiles SSoT to handle parameter compatibility.
    """
    @classmethod
    def get_api_type(cls, model_name: str) -> str:
        if model_name.startswith("gemma4"):
            return "chat"
        return "generate"
    @classmethod
    def get_options(cls, model_name: str) -> Dict[str, Any]:
        if model_name.startswith("gemma4"):
            return {
                "num_predict": 3072,
                "num_ctx": 8192,
            }
        else:
            return {
                "temperature": 0.0,
                "num_predict": 768,
                "num_ctx": 4096,
            }


class LocalModelPolicy:
    """
    Nexus local model routing policy.

    Current formal local-heal runs use Ollama local models: qwen2.5-coder:7b for
    repro/planning and qwen2.5-coder:14b for precision patch retries on Mac.
    """

    OLLAMA_SMALL = os.environ.get("NEXUS_OLLAMA_SMALL_MODEL", "qwen2.5-coder:7b")
    OLLAMA_LARGE = os.environ.get("NEXUS_OLLAMA_MODEL", "gemma4:12b")
    
    SEARCH_TIMEOUT_SECONDS = 120
    PATCH_TIMEOUT_SECONDS = int(os.environ.get("NEXUS_PATCH_TIMEOUT_SECONDS", "600"))
    REPRO_TIMEOUT_SECONDS = 180

    @classmethod
    def select_model(cls, task_type: str, phase: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        根據 Phase 與 Context 決定最適合的本地模型。
        """
        reason = ""
        small_model = cls.OLLAMA_SMALL
        large_model = cls.OLLAMA_LARGE
        model = small_model
        timeout_seconds = cls.SEARCH_TIMEOUT_SECONDS
        
        reasoning_mode = context.get("reasoning_mode", "INTUITIVE")
        attempt = int(context.get("attempt", 1) or 1)
        failure_reason = str(context.get("failure_reason", "") or "")

        # 1. 架構性與前置階段 (Planning / Localization / Repro)
        # 這些階段主要處理邏輯提取與關鍵字檢索，7B 具備足夠能力且速度更快。
        if phase in ["planning", "localization"]:
            model = small_model
            reason = "scaffolding_speed_optimized_ollama"
            timeout_seconds = cls.SEARCH_TIMEOUT_SECONDS
        
        elif phase == "reproduction":
            model = small_model
            reason = "repro_logic_extraction_ollama"
            timeout_seconds = cls.REPRO_TIMEOUT_SECONDS

        # 2. 正式執行階段 (Patch/Repair)
        elif phase == "patch":
            if "NAME_SANITY_ERROR" in failure_reason:
                model = large_model
                reason = "name_sanity_retry_precision_ollama"
                timeout_seconds = cls.PATCH_TIMEOUT_SECONDS
            elif attempt > 1:
                model = large_model
                reason = "retry_precision_escalation_ollama"
                timeout_seconds = cls.PATCH_TIMEOUT_SECONDS
            elif reasoning_mode == "ALGEBRAIC":
                model = large_model
                reason = "algebraic_precision_requirement_ollama"
                timeout_seconds = cls.PATCH_TIMEOUT_SECONDS
            else:
                model = small_model
                reason = "mechanical_repair_efficiency_ollama"
                timeout_seconds = 420

        options = ModelProfile.get_options(model)
        api_type = ModelProfile.get_api_type(model)
        return {
            "model": model,
            "reason_code": reason,
            "policy_version": "v2.1-ollama-qwen25",
            "timeout_seconds": timeout_seconds,
            "ollama_options": options,
            "api_type": api_type,
        }
