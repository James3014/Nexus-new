#!/bin/bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
APP_HOME="${NEXUS_PILOT_HOME:-$HOME/.nexus-pilot-friend}"
VENV_DIR="$APP_HOME/venv"
APP_DIR="$APP_HOME/app"
APP_MAIN="$APP_DIR/nexus_pilot_friend_standalone.py"

mkdir -p "$APP_DIR"

echo "[Nexus] Installing standalone friend CLI..."
rm -rf "$VENV_DIR"
"$PYTHON_BIN" -m venv "$VENV_DIR"
"$VENV_DIR/bin/python" -m ensurepip --upgrade >/dev/null 2>&1 || true
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel >/dev/null
"$VENV_DIR/bin/pip" install requests prompt_toolkit >/dev/null

cat > "$APP_MAIN" <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import getpass
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from prompt_toolkit import PromptSession


DEFAULT_GATEWAY = os.getenv("NEXUS_PILOT_GATEWAY_URL", "http://100.82.155.88:5005")
DEFAULT_PROVIDER = os.getenv("NEXUS_PILOT_PROVIDER", "Gemini")
DEFAULT_MODEL = os.getenv("NEXUS_PILOT_MODEL", "gemini-2.5-flash")
CONFIG_PATH = Path(os.getenv("NEXUS_PILOT_CONFIG", str(Path.home() / ".nexus-pilot-friend" / "config.json")))


@dataclass
class SessionState:
    tenant_id: str
    gateway_url: str
    provider: str
    model: str
    api_key: str


def load_config() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_config(state: SessionState) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tenant_id": state.tenant_id,
        "gateway_url": state.gateway_url,
        "provider": state.provider,
        "model": state.model,
    }
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def status_line(state: SessionState) -> str:
    return (
        f"Tenant: {state.tenant_id}\n"
        f"Gateway: {state.gateway_url}\n"
        f"Provider: {state.provider}\n"
        f"Model: {state.model}"
    )


def request_json(method: str, url: str, *, headers: dict[str, str], payload: dict[str, Any] | None = None) -> tuple[int, Any]:
    try:
        if method == "GET":
            response = requests.get(url, headers=headers, timeout=30)
        else:
            response = requests.post(url, headers=headers, json=payload or {}, timeout=120)
    except requests.RequestException as exc:
        return 0, f"連線失敗: {exc}"
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, response.text


def chat(state: SessionState, message: str) -> str:
    headers = {
        "X-Tenant-ID": state.tenant_id,
        "Accept": "application/json",
    }
    if state.api_key:
        headers["Authorization"] = f"Bearer {state.api_key}"
    code, data = request_json("POST", f"{state.gateway_url}/chat", headers=headers, payload={"question": message, "prompt": message})
    if code == 0:
        return str(data)
    if isinstance(data, dict):
        for key in ("answer", "message", "response", "summary"):
            value = data.get(key)
            if value:
                return str(value)
        return json.dumps(data, ensure_ascii=False)
    return str(data)


def govern(state: SessionState, request_text: str) -> str:
    headers = {"X-Tenant-ID": state.tenant_id, "Accept": "application/json"}
    if state.api_key:
        headers["Authorization"] = f"Bearer {state.api_key}"
    payload = {"request": request_text, "question": request_text}
    code, data = request_json("POST", f"{state.gateway_url}/govern", headers=headers, payload=payload)
    if code == 0:
        return str(data)
    if isinstance(data, dict):
        task_id = data.get("task_id", "n/a")
        summary = data.get("summary", "")
        return f"Governance queued: {task_id}\n{summary}".strip()
    return str(data)


def check_gateway(state: SessionState) -> str:
    headers = {"X-Tenant-ID": state.tenant_id, "Accept": "application/json"}
    code, data = request_json("GET", f"{state.gateway_url}/status", headers=headers)
    if code == 0:
        return str(data)
    if isinstance(data, dict):
        return json.dumps(data, ensure_ascii=False)
    return str(data)


def build_session(argv: list[str]) -> SessionState:
    cfg = load_config()
    tenant_id = (argv[1].strip() if len(argv) >= 2 and argv[1].strip() else "") or str(
        os.getenv("NEXUS_PILOT_TENANT_ID", cfg.get("tenant_id", "pilot_a"))
    )
    gateway_url = str(os.getenv("NEXUS_PILOT_GATEWAY_URL", cfg.get("gateway_url", DEFAULT_GATEWAY))).strip()
    provider = str(os.getenv("NEXUS_PILOT_PROVIDER", cfg.get("provider", DEFAULT_PROVIDER))).strip()
    model = str(os.getenv("NEXUS_PILOT_MODEL", cfg.get("model", DEFAULT_MODEL))).strip()

    api_key = str(os.getenv("NEXUS_PILOT_API_KEY", "")).strip()
    if not api_key:
        api_key = getpass.getpass("API Key (input hidden): ").strip()

    state = SessionState(
        tenant_id=tenant_id,
        gateway_url=gateway_url,
        provider=provider,
        model=model,
        api_key=api_key,
    )
    save_config(state)
    return state


def print_help() -> None:
    print(
        "Commands:\n"
        "/status\n"
        "/gateway <url>\n"
        "/provider <name>\n"
        "/model <name>\n"
        "/govern <task>\n"
        "/help\n"
        "/exit"
    )


def main(argv: list[str]) -> int:
    state = build_session(argv)
    print("Nexus Singularity (Standalone Friend CLI)")
    print(status_line(state))
    print("\nAsk anything, or use /govern for task mode. Type /help for commands.\n")

    prompt = PromptSession()
    while True:
        try:
            line = prompt.prompt("NEXUS > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("")
            return 0

        if not line:
            continue
        if line in ("/exit", "exit", "quit", "/quit"):
            return 0
        if line == "/help":
            print_help()
            continue
        if line == "/status":
            print(status_line(state))
            print(f"Gateway status: {check_gateway(state)}")
            continue
        if line.startswith("/gateway "):
            state.gateway_url = line.split(" ", 1)[1].strip()
            save_config(state)
            print(f"Gateway updated: {state.gateway_url}")
            continue
        if line.startswith("/provider "):
            state.provider = line.split(" ", 1)[1].strip()
            save_config(state)
            print(f"Provider updated: {state.provider}")
            continue
        if line.startswith("/model "):
            state.model = line.split(" ", 1)[1].strip()
            save_config(state)
            print(f"Model updated: {state.model}")
            continue
        if line.startswith("/govern "):
            task = line.split(" ", 1)[1].strip()
            print(govern(state, task))
            continue
        if line.startswith("/"):
            print("Unknown command. Type /help.")
            continue

        print(chat(state, line))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
PY

chmod +x "$APP_MAIN"

mkdir -p "$HOME/.local/bin"

cat > "$HOME/.local/bin/nexus-pilot-friend" <<EOF
#!/bin/bash
exec "$VENV_DIR/bin/python" "$APP_MAIN" "\$@"
EOF
chmod +x "$HOME/.local/bin/nexus-pilot-friend"

echo "[Nexus] Standalone friend CLI installed."
echo "[Nexus] Start with: nexus-pilot-friend pilot_a"
echo "[Nexus] If command not found, add ~/.local/bin to PATH."
