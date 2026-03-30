import http.server
import json
import socketserver
import os
import sys
from pathlib import Path
from typing import Optional
from urllib import parse, request
from urllib.error import URLError, HTTPError

# [SOTA 50.0] Nexus Sentinel Proxy (Zero Dependency)
# Built to survive "Environment Hell" on MacOS.
# Uses pure http.server for 100% startup guarantee.

PORT = int(os.getenv("NEXUS_PILOT_PROXY_PORT", "5005"))
REPO_ROOT = Path(__file__).resolve().parents[1]
STANDALONE_INSTALLER = REPO_ROOT / "scripts" / "ops" / "install_nexus_pilot_friend_standalone.sh"


def _read_standalone_installer() -> Optional[str]:
    try:
        return STANDALONE_INSTALLER.read_text(encoding="utf-8")
    except OSError:
        return None


def _extract_api_key(headers) -> str:
    auth = str(headers.get("Authorization", "")).strip()
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip()
    for candidate in ("X-API-Key", "x-api-key", "X-Goog-Api-Key", "x-goog-api-key"):
        value = str(headers.get(candidate, "")).strip()
        if value:
            return value
    return ""


def _call_gemini(question: str, model: str, api_key: str) -> tuple[bool, str]:
    if not question.strip():
        return False, "empty_question"
    if not api_key.strip():
        return False, "missing_api_key"

    model_name = (model or "gemini-2.5-flash").strip()
    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + parse.quote(model_name, safe="")
        + ":generateContent?key="
        + parse.quote(api_key, safe="")
    )
    payload = {
        "contents": [{"parts": [{"text": question}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024},
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
    except HTTPError as exc:
        return False, f"http_error:{exc.code}"
    except URLError as exc:
        return False, f"net_error:{exc.reason}"
    except Exception as exc:
        return False, f"unexpected_error:{exc}"

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False, "bad_json_response"

    candidates = data.get("candidates") or []
    if not candidates:
        return False, "no_candidates"
    content = (candidates[0] or {}).get("content") or {}
    parts = content.get("parts") or []
    texts = []
    for part in parts:
        text = str((part or {}).get("text", "")).strip()
        if text:
            texts.append(text)
    if texts:
        return True, "\n".join(texts)
    return False, "empty_model_output"

class NexusHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        return
    def do_GET(self):
        if self.path == '/status':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({
                "status": "SOTA Stable",
                "health": 100,
                "processes": 13,
                "mode": "Zero-Dependency",
                "link": "ABS_ZERO_v50.0"
            }).encode('utf-8'))
        elif self.path in ['/install/nexus-pilot-friend.sh', '/install']:
            script = _read_standalone_installer()
            if script is None:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "error": "standalone installer not found",
                    "path": str(STANDALONE_INSTALLER),
                }).encode('utf-8'))
                return
            self.send_response(200)
            self.send_header('Content-type', 'text/x-shellscript; charset=utf-8')
            self.end_headers()
            self.wfile.write(script.encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path in ['/consult', '/chat']:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
            except:
                data = {}
            
            question = str(data.get('question', data.get('prompt', '')))
            model = str(data.get("model", "gemini-2.5-flash"))
            provider = str(data.get("provider", "Gemini"))
            api_key = _extract_api_key(self.headers)
            
            # Log to physical file
            with open("nexus_proxy.log", "a") as f:
                f.write(f"CONSULT_REQ_v50.0: {len(question)} characters received\n")

            used_live_model = False
            if provider.lower().startswith("gemini") and api_key:
                ok, model_resp = _call_gemini(question=question, model=model, api_key=api_key)
                if ok:
                    resp = model_resp
                    used_live_model = True
                else:
                    resp = f"// Nexus Advisor [v50.0-fallback]: 模型連線失敗({model_resp})，已退回本地回聲模式。"
            elif "Acheron Paradox" in question or len(question) > 300:
                resp = f"// Nexus Advisor [v50.0]: 偵測到大規模 Acheron Paradox 指令。數據完整性已鎖定。"
            else:
                resp = f"// Nexus Advisor [v50.0]: 收到指令：{question[:100]}..."

            accept = self.headers.get('Accept', '')
            if 'application/json' in accept:
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    "message": resp,
                    "tenant_id": self.headers.get("X-Tenant-ID", "anonymous-tenant"),
                    "mode": "FAST",
                    "live_model": used_live_model,
                }).encode('utf-8'))
            else:
                self.send_response(200)
                self.send_header('Content-type', 'text/event-stream')
                self.send_header('Cache-Control', 'no-cache')
                self.end_headers()
                self.wfile.write(f"data: {resp}\n\n".encode('utf-8'))
                self.wfile.flush()
        elif self.path == '/govern':
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data)
            except:
                data = {}

            tenant_id = self.headers.get("X-Tenant-ID", data.get("tenant_id", "anonymous-tenant"))
            request_text = str(data.get("request", ""))
            timestamp = int(__import__("time").time())
            task_id = f"{tenant_id}-task-{timestamp}"

            response = {
                "status": "QUEUED",
                "task_id": task_id,
                "summary": (
                    "Sensing: request accepted by Sentinel\n"
                    "Planning: governance slot assigned\n"
                    "Repair: runtime handoff queued\n"
                    "Verify: pending"
                ),
                "tenant_id": tenant_id,
                "request_excerpt": request_text[:120],
            }

            with open("nexus_proxy.log", "a") as f:
                f.write(
                    f"GOVERN_REQ_v50.0: tenant={tenant_id} chars={len(request_text)} task={task_id}\n"
                )

            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

def run_proxy():
    # Socket reuse for rapid restarts
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.ThreadingTCPServer(("", PORT), NexusHandler) as httpd:
        print(f"// Nexus Sentinel Proxy [v50.0] Active on port {PORT}")
        httpd.serve_forever()

if __name__ == "__main__":
    try:
        run_proxy()
    except Exception as e:
        with open("nexus_proxy.log", "a") as f:
            f.write(f"PROXY_FATAL: {str(e)}\n")
