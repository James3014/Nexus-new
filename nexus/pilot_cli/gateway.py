import os
import time

from nexus.pilot_cli.gateway_client import (
    ensure_local_gateway_running as ensure_local_gateway_running_via_client,
)
from nexus.pilot_cli.gateway_client import (
    get_gateway_base_url as get_gateway_base_url_via_env,
)
from nexus.pilot_cli.gateway_client import chat_via_gateway as gateway_chat_request
from nexus.pilot_cli.gateway_client import govern_via_gateway as gateway_govern_request
from nexus.pilot_cli.gemini_client import (
    LONG_INPUT_THRESHOLD,
    chat_via_gemini_api,
    coerce_long_gemini_answer,
    compress_long_gemini_answer,
    gemini_payload,
)
from nexus.pilot_cli.fastlane_formatter import (
    build_fastlane_prompt,
    format_gemini_fastlane_response,
)
from nexus.pilot_cli.session import PilotSession


def get_gateway_base_url() -> str:
    return get_gateway_base_url_via_env(os.getenv)


def _build_fastlane_prompt(user_request: str) -> str:
    return build_fastlane_prompt(user_request, LONG_INPUT_THRESHOLD)


def _format_gemini_fastlane_response(text: str) -> str:
    return format_gemini_fastlane_response(text)


def _gemini_payload(user_request: str) -> dict:
    return gemini_payload(user_request)


def _compress_long_gemini_answer(session: PilotSession, original_prompt: str, draft_answer: str) -> str:
    return compress_long_gemini_answer(session, original_prompt, draft_answer)


def _coerce_long_gemini_answer(
    session: PilotSession,
    user_request: str,
    raw_text: str,
    finish_reason: str,
    second_pass_fn=compress_long_gemini_answer,
) -> str:
    return coerce_long_gemini_answer(
        session=session,
        user_request=user_request,
        raw_text=raw_text,
        finish_reason=finish_reason,
        second_pass_fn=second_pass_fn,
    )


def ensure_local_gateway_running(
    get_fn=None,
    spawn_fn=None,
    sleep_fn=time.sleep,
    retries: int = 5,
) -> bool:
    base_url = get_gateway_base_url()
    kwargs = {"base_url": base_url, "sleep_fn": sleep_fn, "retries": retries}
    if get_fn is not None:
        kwargs["get_fn"] = get_fn
    if spawn_fn is not None:
        kwargs["spawn_fn"] = spawn_fn
    return ensure_local_gateway_running_via_client(**kwargs)


def build_governance_payload(session: PilotSession, user_request: str) -> dict:
    return {
        "tenant_id": session.tenant_id,
        "provider": session.provider,
        "model": session.model,
        "workspace": session.workspace,
        "lane": "BATTLE",
        "request": user_request,
    }


def create_local_task_stub(session: PilotSession, user_request: str) -> dict:
    task_id = f"pilot-task-{int(time.time())}"
    session.active_task_id = task_id
    session.mode = "BATTLE"
    session.last_user_request = user_request
    return {
        "status": "QUEUED",
        "task_id": task_id,
        "summary": (
            "Sensing: task accepted\n"
            "Planning: preparing low-risk path\n"
            "Repair: waiting for runtime integration\n"
            "Verify: pending"
        ),
    }


def chat_via_gateway(
    session: PilotSession,
    user_request: str,
    post_fn=None,
    gemini_fn=chat_via_gemini_api,
    timeout: float = 8.0,
) -> str:
    provider = (session.provider or "").strip().lower()
    gemini_error = None
    if provider == "gemini" and session.api_key:
        try:
            return gemini_fn(session, user_request)
        except Exception as exc:
            gemini_error = exc

    try:
        base_url = get_gateway_base_url()
        if post_fn is not None:
            return gateway_chat_request(base_url, session, user_request, post_fn=post_fn, timeout=timeout)
        return gateway_chat_request(base_url, session, user_request, timeout=timeout)
    except Exception as exc:
        if gemini_error is not None:
            raise RuntimeError(
                f"Gemini direct failed: {gemini_error!r}; gateway fallback failed: {exc!r}"
            ) from exc
        raise


def govern_via_gateway(
    session: PilotSession,
    user_request: str,
    post_fn=None,
    timeout: float = 20.0,
) -> dict:
    payload = build_governance_payload(session, user_request)
    try:
        base_url = get_gateway_base_url()
        if post_fn is not None:
            data = gateway_govern_request(base_url, session, payload, post_fn=post_fn, timeout=timeout)
        else:
            data = gateway_govern_request(base_url, session, payload, timeout=timeout)
        task_id = data.get("task_id") or f"pilot-task-{int(time.time())}"
        session.active_task_id = task_id
        session.mode = "BATTLE"
        session.last_user_request = user_request
        return {
            "status": data.get("status", "QUEUED"),
            "task_id": task_id,
            "summary": data.get(
                "summary",
                "Sensing: task accepted\nPlanning: runtime assigned\nRepair: pending\nVerify: pending",
            ),
        }
    except Exception:
        return create_local_task_stub(session, user_request)


__all__ = [
    "LONG_INPUT_THRESHOLD",
    "build_fastlane_prompt",
    "build_governance_payload",
    "chat_via_gateway",
    "chat_via_gemini_api",
    "coerce_long_gemini_answer",
    "compress_long_gemini_answer",
    "create_local_task_stub",
    "ensure_local_gateway_running",
    "format_gemini_fastlane_response",
    "gemini_payload",
    "get_gateway_base_url",
    "govern_via_gateway",
]
