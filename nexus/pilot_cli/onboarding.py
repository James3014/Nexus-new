from typing import Any, Callable, Dict, List, Optional, Tuple
import os
import re

from nexus.pilot_cli.config import apply_defaults, save_session_defaults
from nexus.pilot_cli.session import PilotSession


DEFAULT_PROVIDER = "OpenAI"
DEFAULT_MODEL_BY_PROVIDER = {
    "OpenAI": "gpt-5.4",
    "Gemini": "gemini-2.5-flash",
}
DEFAULT_TENANT_PREFIX = "pilot"


def build_default_tenant_id() -> str:
    raw = (
        os.getenv("NEXUS_PILOT_DEFAULT_TENANT_ID")
        or os.getenv("USER")
        or os.getenv("USERNAME")
        or DEFAULT_TENANT_PREFIX
    )
    normalized = re.sub(r"[^a-zA-Z0-9]+", "_", raw).strip("_").lower()
    if not normalized:
        normalized = DEFAULT_TENANT_PREFIX
    return f"{DEFAULT_TENANT_PREFIX}_{normalized}"


def infer_provider_from_api_key(api_key: Optional[str]) -> Optional[str]:
    if not api_key:
        return None
    if api_key.startswith("AIza"):
        return "Gemini"
    if api_key.startswith("sk-"):
        return "OpenAI"
    return None


def build_session_from_answers(
    tenant_id: str,
    provider: Optional[str] = None,
    api_key: Optional[str] = None,
    model: Optional[str] = None,
    workspace: Optional[str] = None,
) -> PilotSession:
    resolved_provider = provider or DEFAULT_PROVIDER
    resolved_model = model or DEFAULT_MODEL_BY_PROVIDER.get(
        resolved_provider, "gpt-5.4"
    )
    return PilotSession(
        tenant_id=tenant_id or None,
        provider=resolved_provider,
        api_key=api_key or None,
        model=resolved_model,
        workspace=workspace or None,
    )


def prompt_for_missing_session_fields(
    session: PilotSession,
    input_fn: Callable[[str], str] = input,
) -> PilotSession:
    session = apply_defaults(session)
    if not session.tenant_id:
        session.tenant_id = build_default_tenant_id()
    if not session.provider:
        session.provider = DEFAULT_PROVIDER
    if not session.api_key:
        session.api_key = input_fn("API Key: ").strip() or None
    inferred_provider = infer_provider_from_api_key(session.api_key)
    if inferred_provider and not os.getenv("NEXUS_PILOT_PROVIDER"):
        session.provider = inferred_provider
    if not session.model:
        session.model = DEFAULT_MODEL_BY_PROVIDER.get(session.provider or DEFAULT_PROVIDER, "gpt-5.4")
    elif inferred_provider and inferred_provider == session.provider and not os.getenv("NEXUS_PILOT_MODEL"):
        session.model = DEFAULT_MODEL_BY_PROVIDER.get(session.provider or DEFAULT_PROVIDER, session.model)
    save_session_defaults(session)
    return session
