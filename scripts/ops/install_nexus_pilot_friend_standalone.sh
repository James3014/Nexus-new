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
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib import parse, request
from urllib.error import HTTPError, URLError

import requests
from prompt_toolkit import PromptSession


DEFAULT_GATEWAY = os.getenv("NEXUS_PILOT_GATEWAY_URL", "http://100.82.155.88:5005")
DEFAULT_PROVIDER = os.getenv("NEXUS_PILOT_PROVIDER", "Gemini")
DEFAULT_MODEL = os.getenv("NEXUS_PILOT_MODEL", "gemini-2.5-flash")
CONFIG_PATH = Path(os.getenv("NEXUS_PILOT_CONFIG", str(Path.home() / ".nexus-pilot-friend" / "config.json")))
MODEL_CATALOG = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
]
TEXT_FILE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".json", ".yaml", ".yml",
    ".toml", ".rs", ".go", ".java", ".rb", ".php", ".txt", ".sh",
}
IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__", "dist", "build", ".next", ".cache",
}


@dataclass
class SessionState:
    tenant_id: str
    gateway_url: str
    provider: str
    model: str
    api_key: str
    mode: str
    workspace_root: str
    auto_apply: bool


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
        "mode": state.mode,
        "workspace_root": state.workspace_root,
        "auto_apply": state.auto_apply,
    }
    CONFIG_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def status_line(state: SessionState) -> str:
    return (
        f"Tenant: {state.tenant_id}\n"
        f"Gateway: {state.gateway_url}\n"
        f"Provider: {state.provider}\n"
        f"Model: {state.model}\n"
        f"Mode: {state.mode}\n"
        f"Workspace: {state.workspace_root or '(not set)'}\n"
        f"Auto Apply: {'on' if state.auto_apply else 'off'}"
    )


def request_json(method: str, url: str, *, headers: Dict[str, str], payload: Optional[Dict[str, Any]] = None) -> Tuple[int, Any]:
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
    code, data = request_json(
        "POST",
        f"{state.gateway_url}/chat",
        headers=headers,
        payload={
            "question": message,
            "prompt": message,
            "provider": state.provider,
            "model": state.model,
        },
    )
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


def _call_gemini_direct(question: str, state: SessionState) -> Tuple[bool, str]:
    if not state.api_key:
        return False, "missing_api_key"
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + parse.quote(state.model, safe="")
        + ":generateContent?key="
        + parse.quote(state.api_key, safe="")
    )
    payload = {
        "contents": [{"parts": [{"text": question}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 2048},
    }
    req = request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return False, f"http_error:{exc.code}"
    except URLError as exc:
        return False, f"net_error:{exc.reason}"
    except Exception as exc:
        return False, f"unexpected_error:{exc}"

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return False, "bad_json_response"

    candidates = body.get("candidates") or []
    if not candidates:
        return False, "no_candidates"
    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    text_parts: List[str] = []
    for part in parts:
        text = str((part or {}).get("text", "")).strip()
        if text:
            text_parts.append(text)
    if not text_parts:
        return False, "empty_output"
    return True, "\n".join(text_parts)


def _resolve_workspace_path(state: SessionState, rel_path: str) -> Path:
    root = Path(state.workspace_root).expanduser().resolve()
    if not state.workspace_root or not root.exists() or not root.is_dir():
        raise ValueError("workspace_not_set_or_missing")
    rel = rel_path.strip()
    if not rel:
        raise ValueError("empty_path")
    if os.path.isabs(rel):
        raise ValueError("absolute_path_not_allowed")
    if ".." in Path(rel).parts:
        raise ValueError("path_traversal_not_allowed")
    target = (root / rel).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ValueError("path_out_of_workspace") from exc
    return target


def _iter_workspace_files(root: Path, max_files: int = 200) -> List[Path]:
    results: List[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS and not d.startswith(".")]
        for name in filenames:
            if len(results) >= max_files:
                return results
            file_path = Path(current_root) / name
            if file_path.suffix.lower() not in TEXT_FILE_EXTENSIONS:
                continue
            results.append(file_path)
    return results


def _select_context_files(task: str, files: List[Path], root: Path, limit: int = 14) -> List[Path]:
    words = re.findall(r"[A-Za-z0-9_\\-]+", task.lower())
    words = [w for w in words if len(w) >= 3]
    scored: List[Tuple[int, Path]] = []
    for f in files:
        rel = str(f.relative_to(root)).lower()
        score = 0
        for w in words:
            if w in rel:
                score += 2
            if w in f.name.lower():
                score += 3
        scored.append((score, f))
    scored.sort(key=lambda item: item[0], reverse=True)
    selected = [p for s, p in scored if s > 0][:limit]
    if len(selected) < min(limit, len(files)):
        fallback = [p for _, p in scored if p not in selected][: (limit - len(selected))]
        selected.extend(fallback)
    return selected


def _build_workspace_context(state: SessionState, task: str) -> Tuple[bool, str, Dict[str, Any]]:
    if not state.workspace_root:
        return False, "workspace_not_set", {}
    root = Path(state.workspace_root).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return False, "workspace_not_found", {}
    files = _iter_workspace_files(root=root, max_files=240)
    selected = _select_context_files(task=task, files=files, root=root, limit=14)
    file_payload: List[Dict[str, str]] = []
    for path in selected:
        rel = str(path.relative_to(root))
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(content) > 12000:
            content = content[:12000] + "\n/* ...truncated... */\n"
        file_payload.append({"path": rel, "content": content})
    context = {
        "workspace_root": str(root),
        "candidate_file_count": len(files),
        "selected_file_count": len(file_payload),
        "files": file_payload,
    }
    return True, "ok", context


def _extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json\n", "", 1).strip()
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            obj = json.loads(raw[start : end + 1])
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            return None
    return None


def _apply_local_edits(state: SessionState, edits: List[Dict[str, Any]]) -> Tuple[bool, str]:
    applied = 0
    for item in edits:
        rel = str(item.get("path", "")).strip()
        content = item.get("content")
        if not rel or not isinstance(content, str):
            return False, f"invalid_edit_item:{item}"
        try:
            target = _resolve_workspace_path(state, rel)
        except ValueError as exc:
            return False, f"path_rejected:{rel}:{exc}"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        applied += 1
    return True, f"applied_edits:{applied}"


def govern_local(state: SessionState, request_text: str) -> str:
    ok, reason, context = _build_workspace_context(state, request_text)
    if not ok:
        if reason == "workspace_not_set":
            return "Local mode requires workspace. Use /workspace <path> first."
        if reason == "workspace_not_found":
            return f"Workspace not found: {state.workspace_root}"
        return f"Workspace error: {reason}"

    prompt = (
        "You are Nexus local coding worker. "
        "Given task + workspace files, return STRICT JSON only.\n"
        "Schema:\n"
        "{\n"
        "  \"summary\": \"...\",\n"
        "  \"edits\": [{\"path\": \"relative/path\", \"content\": \"full file content\", \"reason\": \"...\"}],\n"
        "  \"tests\": [\"optional command strings\"]\n"
        "}\n"
        "Rules:\n"
        "- Return only JSON, no markdown.\n"
        "- path must be relative to workspace root.\n"
        "- If no edits required, return edits: [].\n\n"
        f"TASK:\n{request_text}\n\n"
        f"WORKSPACE_CONTEXT_JSON:\n{json.dumps(context, ensure_ascii=False)}"
    )
    ok_model, model_output = _call_gemini_direct(prompt, state)
    if not ok_model:
        return f"Local worker model call failed: {model_output}"

    payload = _extract_json_object(model_output)
    if not payload:
        return "Local worker returned non-JSON output. Try refining task or model."
    summary = str(payload.get("summary", "")).strip() or "(no summary)"
    edits = payload.get("edits", [])
    tests = payload.get("tests", [])
    if not isinstance(edits, list):
        edits = []
    if not isinstance(tests, list):
        tests = []

    lines: List[str] = []
    lines.append(f"[Local Worker] {summary}")
    lines.append(f"- edits: {len(edits)}")
    if edits:
        preview_paths = [str((e or {}).get("path", "")).strip() for e in edits[:8]]
        lines.append(f"- files: {', '.join([p for p in preview_paths if p])}")
    if tests:
        lines.append("- tests:")
        for t in tests[:6]:
            lines.append(f"  {t}")

    if edits and state.auto_apply:
        applied_ok, apply_msg = _apply_local_edits(state, edits)
        if applied_ok:
            lines.append(f"- apply: success ({apply_msg})")
        else:
            lines.append(f"- apply: failed ({apply_msg})")
    elif edits:
        lines.append("- apply: skipped (auto_apply=off, use /apply on)")
    return "\n".join(lines)


def build_session(argv: List[str]) -> SessionState:
    cfg = load_config()
    tenant_id = (argv[1].strip() if len(argv) >= 2 and argv[1].strip() else "") or str(
        os.getenv("NEXUS_PILOT_TENANT_ID", cfg.get("tenant_id", "pilot_a"))
    )
    gateway_url = str(os.getenv("NEXUS_PILOT_GATEWAY_URL", cfg.get("gateway_url", DEFAULT_GATEWAY))).strip()
    provider = str(os.getenv("NEXUS_PILOT_PROVIDER", cfg.get("provider", DEFAULT_PROVIDER))).strip()
    model = str(os.getenv("NEXUS_PILOT_MODEL", cfg.get("model", DEFAULT_MODEL))).strip()
    mode = str(os.getenv("NEXUS_PILOT_MODE", cfg.get("mode", "remote"))).strip().lower()
    if mode not in ("remote", "local"):
        mode = "remote"
    workspace_root = str(os.getenv("NEXUS_PILOT_WORKSPACE_ROOT", cfg.get("workspace_root", ""))).strip()
    auto_apply = bool(cfg.get("auto_apply", False))
    if os.getenv("NEXUS_PILOT_AUTO_APPLY", "").strip().lower() in ("1", "true", "yes", "on"):
        auto_apply = True
    elif os.getenv("NEXUS_PILOT_AUTO_APPLY", "").strip().lower() in ("0", "false", "no", "off"):
        auto_apply = False

    api_key = str(os.getenv("NEXUS_PILOT_API_KEY", "")).strip()
    if not api_key:
        api_key = getpass.getpass("API Key (input hidden): ").strip()

    state = SessionState(
        tenant_id=tenant_id,
        gateway_url=gateway_url,
        provider=provider,
        model=model,
        api_key=api_key,
        mode=mode,
        workspace_root=workspace_root,
        auto_apply=auto_apply,
    )
    save_config(state)
    return state


def print_help() -> None:
    print(
        "Commands:\n"
        "/status\n"
        "/mode [remote|local]\n"
        "/workspace <path>\n"
        "/apply [on|off]\n"
        "/gateway <url>\n"
        "/provider <name>\n"
        "/model              (open model picker)\n"
        "/model <name>\n"
        "/govern              (prompt task)\n"
        "/govern <task>\n"
        "/help\n"
        "/exit"
    )


def choose_model(prompt: PromptSession, state: SessionState) -> None:
    print("Select Model")
    for idx, model_name in enumerate(MODEL_CATALOG, start=1):
        marker = "*" if model_name == state.model else " "
        print(f" {marker} {idx}. {model_name}")
    raw = prompt.prompt("MODEL # > ").strip()
    if not raw:
        print("Model selection cancelled.")
        return
    if not raw.isdigit():
        print("Invalid selection. Enter a number from the list.")
        return
    index = int(raw)
    if index < 1 or index > len(MODEL_CATALOG):
        print("Invalid selection index.")
        return
    state.model = MODEL_CATALOG[index - 1]
    save_config(state)
    print(f"Model updated: {state.model}")


def set_workspace(state: SessionState, path_arg: str) -> str:
    path_raw = path_arg.strip()
    if not path_raw:
        return "Workspace path is empty."
    root = Path(path_raw).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        return f"Workspace not found: {root}"
    state.workspace_root = str(root)
    save_config(state)
    return f"Workspace updated: {state.workspace_root}"


def set_mode(state: SessionState, value: str) -> str:
    mode = value.strip().lower()
    if mode not in ("remote", "local"):
        return "Invalid mode. Use /mode remote or /mode local"
    state.mode = mode
    save_config(state)
    return f"Mode updated: {state.mode}"


def set_apply(state: SessionState, value: str) -> str:
    v = value.strip().lower()
    if v not in ("on", "off"):
        return "Invalid apply mode. Use /apply on or /apply off"
    state.auto_apply = (v == "on")
    save_config(state)
    return f"Auto Apply updated: {'on' if state.auto_apply else 'off'}"


def main(argv: List[str]) -> int:
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
        if line.startswith("/mode "):
            print(set_mode(state, line.split(" ", 1)[1]))
            continue
        if line == "/mode":
            print(f"Current mode: {state.mode}")
            continue
        if line.startswith("/workspace "):
            print(set_workspace(state, line.split(" ", 1)[1]))
            continue
        if line == "/workspace":
            print(f"Workspace: {state.workspace_root or '(not set)'}")
            continue
        if line.startswith("/apply "):
            print(set_apply(state, line.split(" ", 1)[1]))
            continue
        if line == "/apply":
            print(f"Auto Apply: {'on' if state.auto_apply else 'off'}")
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
        if line == "/model":
            choose_model(prompt, state)
            continue
        if line.startswith("/model "):
            state.model = line.split(" ", 1)[1].strip()
            if not state.model:
                print("Model cannot be empty.")
                continue
            save_config(state)
            print(f"Model updated: {state.model}")
            continue
        if line == "/govern":
            task = prompt.prompt("GOVERN > ").strip()
            if not task:
                print("Govern task is empty. Use /govern <task> or enter task after /govern.")
                continue
            if state.mode == "local":
                print(govern_local(state, task))
            else:
                print(govern(state, task))
            continue
        if line.startswith("/govern "):
            task = line.split(" ", 1)[1].strip()
            if not task:
                print("Govern task is empty.")
                continue
            if state.mode == "local":
                print(govern_local(state, task))
            else:
                print(govern(state, task))
            continue
        if line.startswith("/"):
            print("Unknown command. Type /help.")
            continue

        if state.mode == "local":
            print(govern_local(state, line))
        else:
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
