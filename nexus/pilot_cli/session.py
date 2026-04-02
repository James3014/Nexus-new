from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
import os


@dataclass
class PilotSession:
    tenant_id: Optional[str] = None
    provider: Optional[str] = None
    model: Optional[str] = None
    workspace: Optional[str] = None
    api_key: Optional[str] = None
    mode: str = "FAST"
    active_task_id: Optional[str] = None
    last_user_request: Optional[str] = None
    pending_action: Optional[str] = None

    def masked_api_key(self) -> str:
        key = self.api_key
        if not key:
            return "(not set)"
        if len(key) <= 4:
            return "*" * len(key)
        return f"{key[:4]}***"

    def describe(self) -> str:
        tenant_id = self.tenant_id or "(not set)"
        provider = self.provider or "(not set)"
        model = self.model or "(not set)"
        workspace = self.workspace or "(not set)"
        gateway = os.getenv("NEXUS_PILOT_GATEWAY_URL", "http://127.0.0.1:5005")
        return (
            f"Tenant: {tenant_id}\n"
            f"Provider: {provider}\n"
            f"Model: {model}\n"
            f"Workspace: {workspace}\n"
            f"Mode: {self.mode}\n"
            f"API Key: {self.masked_api_key()}\n"
            f"Active Task: {self.active_task_id or '(none)'}\n"
            f"Gateway: {gateway}"
        )

    def reset_context(self) -> None:
        self.workspace = None
        self.mode = "FAST"
        self.active_task_id = None
        self.last_user_request = None
        self.pending_action = None

    def clear_secrets(self) -> None:
        self.api_key = None
