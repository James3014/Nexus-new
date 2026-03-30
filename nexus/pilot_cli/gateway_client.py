import subprocess
import sys
import time
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

from nexus.pilot_cli.http_client import curl_request
from nexus.pilot_cli.session import PilotSession


DEFAULT_GATEWAY_BASE_URL = "http://127.0.0.1:5005"


def get_gateway_base_url(env_get) -> str:
    return env_get("NEXUS_PILOT_GATEWAY_URL", DEFAULT_GATEWAY_BASE_URL).rstrip("/")


def is_local_gateway(base_url: str) -> bool:
    return base_url.startswith("http://127.0.0.1") or base_url.startswith("http://localhost")


def spawn_local_proxy() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    proxy_script = repo_root / "scripts" / "nexus_sentinel_proxy.py"
    subprocess.Popen(
        [sys.executable, str(proxy_script)],
        cwd=str(repo_root),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def tenant_headers(session: PilotSession) -> dict:
    tenant_id = session.tenant_id or "anonymous-tenant"
    return {"X-Tenant-ID": tenant_id, "Accept": "application/json"}


def http_get(url: str, timeout: float = 1.0):
    return curl_request(url, method="GET", timeout=timeout)


def http_post(url: str, json_payload: dict, headers: dict, timeout: float):
    return curl_request(
        url,
        method="POST",
        json_payload=json_payload,
        headers={**headers, "Content-Type": "application/json"},
        timeout=timeout,
    )


def ensure_local_gateway_running(
    *,
    base_url: str,
    get_fn=http_get,
    spawn_fn=spawn_local_proxy,
    sleep_fn=time.sleep,
    retries: int = 5,
) -> bool:
    if not is_local_gateway(base_url):
        return False

    status_url = f"{base_url}/status"
    try:
        response = get_fn(status_url, timeout=1.0)
        if getattr(response, "status_code", None) == 200:
            return False
    except Exception as e:
        # Gateway is not responding, normal if not yet spawned
        logger.debug("gateway_availability_check_failed (expected if not spawned): %s", e)

    spawn_fn()
    for _ in range(retries):
        sleep_fn(0.2)
        try:
            response = get_fn(status_url, timeout=1.0)
            if getattr(response, "status_code", None) == 200:
                return True
        except Exception:
            continue
    return False


def chat_via_gateway(base_url: str, session: PilotSession, user_request: str, post_fn=http_post, timeout: float = 8.0) -> str:
    payload = {
        "question": user_request,
        "provider": session.provider,
        "model": session.model,
        "workspace": session.workspace,
    }
    response = post_fn(f"{base_url}/chat", payload, tenant_headers(session), timeout)
    if "application/json" in response.headers.get("content-type", ""):
        data = response.json()
        return data.get("message") or data.get("output") or response.text

    lines = [line.strip() for line in response.text.splitlines() if line.strip()]
    for line in lines:
        if line.startswith("data:"):
            return line.split("data:", 1)[1].strip()
    return response.text.strip()


def govern_via_gateway(base_url: str, session: PilotSession, payload: dict, post_fn=http_post, timeout: float = 20.0) -> dict:
    response = post_fn(f"{base_url}/govern", payload, tenant_headers(session), timeout)
    return response.json()
