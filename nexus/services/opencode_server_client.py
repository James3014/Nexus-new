"""Dedicated loopback OpenCode server supervisor and request client.

The Nexus external-worker lane uses an isolated OpenCode server profile so it
does not share TUI sessions, plugins, databases, or mutable project state with
an owner's interactive OpenCode usage. The server is transport only.
"""

from __future__ import annotations

import base64
import fcntl
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class OpenCodeServerError(RuntimeError):
    pass


class OpenCodeRequestTimeout(OpenCodeServerError):
    pass


@dataclass(frozen=True)
class OpenCodeResult:
    provider: str
    model: str
    cost: float
    finish: str | None
    session_id: str
    message_id: str | None
    tool_event_count: int
    text: str
    server_version: str | None


def _atomic_text(path: Path, value: str, mode: int = 0o600) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    fd = os.open(str(tmp), os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(value)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def _process_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class OpenCodeServerClient:
    def __init__(
        self,
        *,
        state_root: Path | None = None,
        port: int | None = None,
        binary: str | None = None,
    ) -> None:
        self.state_root = (
            Path(state_root).expanduser()
            if state_root is not None
            else Path(
                os.getenv(
                    "NEXUS_OPENCODE_SERVER_ROOT",
                    str(Path.home() / ".local/state/nexus-opencode-server"),
                )
            ).expanduser()
        )
        self.port = int(port or os.getenv("NEXUS_OPENCODE_SERVER_PORT", "4097"))
        if not 1024 <= self.port <= 65535:
            raise OpenCodeServerError("OPENCODE_SERVER_PORT_INVALID")
        configured = binary or os.getenv("NEXUS_OPENCODE_BIN", "").strip()
        resolved = configured or shutil.which("opencode")
        if not resolved or not Path(resolved).expanduser().is_file():
            raise OpenCodeServerError("OPENCODE_BINARY_MISSING")
        self.binary = str(Path(resolved).expanduser().resolve())
        self.username = "nexus"
        self.password_path = self.state_root / "server-password"
        self.pid_path = self.state_root / "server.pid"
        self.lock_path = self.state_root / "server.lock"
        self.stdout_path = self.state_root / "server.stdout.log"
        self.stderr_path = self.state_root / "server.stderr.log"

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _password(self) -> str:
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.password_path.is_file():
            return self.password_path.read_text(encoding="utf-8").strip()
        value = secrets.token_urlsafe(32)
        try:
            fd = os.open(
                str(self.password_path),
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(value + "\n")
                fh.flush()
                os.fsync(fh.fileno())
        return self.password_path.read_text(encoding="utf-8").strip()

    def _auth_header(self) -> str:
        raw = f"{self.username}:{self._password()}".encode("utf-8")
        return "Basic " + base64.b64encode(raw).decode("ascii")

    def _request(
        self,
        method: str,
        path: str,
        *,
        query: dict[str, str] | None = None,
        payload: dict[str, Any] | None = None,
        timeout: float = 5.0,
        expect_json: bool = True,
    ) -> Any:
        url = self.base_url + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"accept": "application/json"}
        if body is not None:
            headers["content-type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:2000]
            raise OpenCodeServerError(f"OPENCODE_HTTP_{exc.code}:{detail}") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise OpenCodeRequestTimeout("OPENCODE_HTTP_TIMEOUT") from exc
        except urllib.error.URLError as exc:
            if isinstance(getattr(exc, "reason", None), TimeoutError):
                raise OpenCodeRequestTimeout("OPENCODE_HTTP_TIMEOUT") from exc
            raise OpenCodeServerError(f"OPENCODE_HTTP_ERROR:{exc}") from exc
        if not expect_json:
            return raw
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise OpenCodeServerError("OPENCODE_NON_JSON_RESPONSE") from exc

    def health(self, *, timeout: float = 2.0) -> dict[str, Any] | None:
        try:
            value = self._request("GET", "/global/health", timeout=timeout)
        except OpenCodeServerError:
            return None
        return value if isinstance(value, dict) and value.get("healthy") is True else None

    def _read_pid(self) -> int | None:
        try:
            return int(self.pid_path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return None

    def _owned_process(self, pid: int) -> bool:
        proc = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        command = proc.stdout.strip()
        return (
            proc.returncode == 0
            and "opencode" in command
            and "serve" in command
            and str(self.port) in command
        )

    def _stop_stale_owned_server(self) -> None:
        pid = self._read_pid()
        if not pid or not _process_alive(pid) or not self._owned_process(pid):
            return
        try:
            os.killpg(pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        deadline = time.monotonic() + 3
        while _process_alive(pid) and time.monotonic() < deadline:
            time.sleep(0.1)
        if _process_alive(pid):
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def _server_env(self) -> dict[str, str]:
        root = self.state_root
        paths = {
            "HOME": root / "home",
            "XDG_CONFIG_HOME": root / "xdg-config",
            "XDG_DATA_HOME": root / "xdg-data",
            "XDG_CACHE_HOME": root / "xdg-cache",
            "XDG_STATE_HOME": root / "xdg-state",
            "OPENCODE_CONFIG_DIR": root / "configdir",
        }
        for path in paths.values():
            Path(path).mkdir(parents=True, exist_ok=True)
        env = dict(os.environ)
        for key in (
            "GITHUB_TOKEN",
            "GH_TOKEN",
            "GIT_ASKPASS",
            "SSH_ASKPASS",
            "SSH_AUTH_SOCK",
        ):
            env.pop(key, None)
        env.update({key: str(value) for key, value in paths.items()})
        env.update({
            "OPENCODE_CONFIG_CONTENT": '{"$schema":"https://opencode.ai/config.json"}',
            "OPENCODE_DISABLE_PROJECT_CONFIG": "true",
            "OPENCODE_DISABLE_PRUNE": "true",
            "OPENCODE_DISABLE_AUTOUPDATE": "true",
        })
        return env

    def ensure_server(self, *, startup_timeout: float = 20.0) -> dict[str, Any]:
        healthy = self.health()
        if healthy:
            return healthy
        self.state_root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.lock_path.open("a+") as lock_fh:
            fcntl.flock(lock_fh.fileno(), fcntl.LOCK_EX)
            try:
                healthy = self.health()
                if healthy:
                    return healthy
                self._stop_stale_owned_server()
                with (
                    self.stdout_path.open("ab", buffering=0) as out_fh,
                    self.stderr_path.open("ab", buffering=0) as err_fh,
                ):
                    proc = subprocess.Popen(
                        [
                            self.binary,
                            "serve",
                            "--hostname",
                            "127.0.0.1",
                            "--port",
                            str(self.port),
                        ],
                        env=self._server_env(),
                        stdin=subprocess.DEVNULL,
                        stdout=out_fh,
                        stderr=err_fh,
                        start_new_session=True,
                        close_fds=True,
                    )
                _atomic_text(self.pid_path, str(proc.pid) + "\n")
                deadline = time.monotonic() + startup_timeout
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        raise OpenCodeServerError(f"OPENCODE_SERVER_EXITED_EARLY:{proc.returncode}")
                    healthy = self.health(timeout=1.5)
                    if healthy:
                        return healthy
                    time.sleep(0.2)
                self._stop_stale_owned_server()
                raise OpenCodeServerError("OPENCODE_SERVER_START_TIMEOUT")
            finally:
                fcntl.flock(lock_fh.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _normalize_model(model: str) -> str:
        value = model.strip()
        return value.split("/", 1)[1] if value.startswith("opencode/") else value

    @staticmethod
    def _zero_cost(model: dict[str, Any]) -> bool:
        cost = model.get("cost")
        if not isinstance(cost, dict):
            return False
        values: list[float] = []
        for key in ("input", "output"):
            value = cost.get(key)
            if not isinstance(value, (int, float)):
                return False
            values.append(float(value))
        cache = cost.get("cache")
        if isinstance(cache, dict):
            for value in cache.values():
                if isinstance(value, (int, float)):
                    values.append(float(value))
        return bool(values) and all(value == 0.0 for value in values)

    def _attest_model(self, directory: str, model: str, require_free: bool) -> str:
        requested = self._normalize_model(model)
        providers = self._request(
            "GET",
            "/provider",
            query={"directory": directory},
            timeout=8,
        )
        if not isinstance(providers, dict) or "opencode" not in providers.get("connected", []):
            raise OpenCodeServerError("OPENCODE_PROVIDER_NOT_CONNECTED")
        provider = next(
            (
                item
                for item in providers.get("all", [])
                if isinstance(item, dict) and item.get("id") == "opencode"
            ),
            None,
        )
        if provider is None:
            raise OpenCodeServerError("OPENCODE_PROVIDER_MISSING")
        models = provider.get("models") or {}
        if not isinstance(models, dict):
            raise OpenCodeServerError("OPENCODE_MODEL_CATALOG_INVALID")

        if requested == "auto-free":
            priority = [
                value.strip()
                for value in os.getenv(
                    "NEXUS_OPENCODE_FREE_MODEL_PRIORITY",
                    (
                        "mimo-v2.6-flash-free,mimo-v2.5-free,"
                        "ling-3.0-flash-fin-free,nemotron-3.5-lightning-free,"
                        "nemotron-3-ultra-free,muse-spark-1.3-contributor-free"
                    ),
                ).split(",")
                if value.strip()
            ]
            eligible = {
                model_id
                for model_id, info in models.items()
                if isinstance(info, dict) and model_id.endswith("-free") and self._zero_cost(info)
            }
            selected = next(
                (model_id for model_id in priority if model_id in eligible),
                None,
            )
            if selected is None and eligible:
                selected = sorted(eligible)[0]
            if selected is None:
                raise OpenCodeServerError("OPENCODE_FREE_MODEL_UNAVAILABLE")
            return selected

        model_info = models.get(requested)
        if not isinstance(model_info, dict):
            raise OpenCodeServerError(f"OPENCODE_MODEL_NOT_AVAILABLE:{requested}")
        if require_free and not (requested.endswith("-free") and self._zero_cost(model_info)):
            raise OpenCodeServerError("OPENCODE_FREE_MODEL_REQUIRED")
        return requested

    @staticmethod
    def _permission_forbidden(request: dict[str, Any]) -> bool:
        permission = str(request.get("permission") or "")
        if permission in {"external_directory", "question"}:
            return True
        if permission == "read":
            for pattern in request.get("patterns", []):
                name = Path(str(pattern)).name
                if name == ".env" or name.startswith(".env."):
                    return True
        return False

    def _handle_pending_permissions(
        self,
        *,
        session_id: str,
        directory: str,
        mode: str,
        auto_approve: bool,
    ) -> None:
        pending = self._request(
            "GET",
            "/permission",
            query={"directory": directory},
            timeout=3,
        )
        if not isinstance(pending, list):
            return
        for request in pending:
            if not isinstance(request, dict) or request.get("sessionID") != session_id:
                continue
            request_id = str(request.get("id") or "")
            permission = str(request.get("permission") or "unknown")
            if not request_id:
                raise OpenCodeServerError("OPENCODE_PERMISSION_REQUEST_INVALID")
            forbidden = self._permission_forbidden(request)
            allow_once = mode == "act" and auto_approve and not forbidden
            self._request(
                "POST",
                f"/permission/{request_id}/reply",
                query={"directory": directory},
                payload={"reply": "once" if allow_once else "reject"},
                timeout=3,
            )
            if forbidden:
                raise OpenCodeServerError(f"OPENCODE_PERMISSION_DENIED:{permission}")
            if not allow_once:
                raise OpenCodeServerError(f"OPENCODE_PERMISSION_REQUIRED:{permission}")

    def _reject_pending_questions(self, *, session_id: str, directory: str) -> None:
        pending = self._request(
            "GET",
            "/question",
            query={"directory": directory},
            timeout=3,
        )
        if not isinstance(pending, list):
            return
        for request in pending:
            if not isinstance(request, dict) or request.get("sessionID") != session_id:
                continue
            request_id = str(request.get("id") or "")
            if request_id:
                self._request(
                    "POST",
                    f"/question/{request_id}/reject",
                    query={"directory": directory},
                    timeout=3,
                )
            raise OpenCodeServerError("OPENCODE_QUESTION_REQUIRED")

    def _abort_session(self, session_id: str, directory: str) -> None:
        try:
            self._request(
                "POST",
                f"/session/{session_id}/abort",
                query={"directory": directory},
                timeout=3,
            )
        except OpenCodeServerError:
            pass

    @staticmethod
    def _assistant_messages(messages: Any) -> list[dict[str, Any]]:
        if not isinstance(messages, list):
            return []
        return [
            message
            for message in messages
            if isinstance(message, dict)
            and isinstance(message.get("info"), dict)
            and message["info"].get("role") == "assistant"
        ]

    @staticmethod
    def _finish_from_parts(parts: Any) -> str | None:
        if not isinstance(parts, list):
            return None
        for part in reversed(parts):
            if not isinstance(part, dict):
                continue
            if part.get("type") == "step-finish" and part.get("reason") is not None:
                return str(part["reason"])
        return None

    @staticmethod
    def _assistant_error(info: dict[str, Any]) -> str | None:
        error = info.get("error")
        if not isinstance(error, dict):
            return None
        data = error.get("data")
        if isinstance(data, dict) and data.get("message"):
            return str(data["message"])
        if error.get("name"):
            return str(error["name"])
        return "unknown assistant error"

    def run(
        self,
        *,
        model: str,
        prompt: str,
        directory: str,
        mode: str,
        auto_approve: bool,
        timeout_seconds: int,
        require_free: bool,
    ) -> OpenCodeResult:
        health = self.ensure_server()
        model_id = self._attest_model(directory, model, require_free)
        session = self._request(
            "POST",
            "/session",
            query={"directory": directory},
            payload={
                "title": "Nexus external-worker operation",
                "model": {"id": model_id, "providerID": "opencode"},
            },
            timeout=10,
        )
        if not isinstance(session, dict) or not session.get("id"):
            raise OpenCodeServerError("OPENCODE_SESSION_CREATE_INVALID")
        session_id = str(session["id"])
        body = {
            "model": {"providerID": "opencode", "modelID": model_id},
            "agent": "plan" if mode == "plan" else "build",
            "parts": [{"type": "text", "text": prompt}],
        }

        # The free OpenCode provider rejects the synchronous /message route in
        # current 1.18.x builds with "free tier can only be used from within
        # OpenCode". The native asynchronous route is accepted by the same
        # server/provider/model and is therefore the canonical direct-worker
        # transport. Terminal truth is read back from session status/messages.
        try:
            self._request(
                "POST",
                f"/session/{session_id}/prompt_async",
                query={"directory": directory},
                payload=body,
                timeout=min(10, max(1, timeout_seconds)),
                expect_json=False,
            )

            deadline = time.monotonic() + max(1, timeout_seconds)
            messages: Any = None
            final_info: dict[str, Any] | None = None
            final_parts: Any = []
            final_finish: str | None = None
            seen_busy = False

            while time.monotonic() < deadline:
                statuses = self._request(
                    "GET",
                    "/session/status",
                    query={"directory": directory},
                    timeout=5,
                )
                state: str | None = None
                if isinstance(statuses, dict):
                    current = statuses.get(session_id)
                    if isinstance(current, dict) and current.get("type") is not None:
                        state = str(current["type"])
                if state in {"busy", "retry"}:
                    seen_busy = True

                self._handle_pending_permissions(
                    session_id=session_id,
                    directory=directory,
                    mode=mode,
                    auto_approve=auto_approve,
                )
                self._reject_pending_questions(
                    session_id=session_id,
                    directory=directory,
                )

                messages = self._request(
                    "GET",
                    f"/session/{session_id}/message",
                    query={"directory": directory},
                    timeout=8,
                )
                assistant_messages = self._assistant_messages(messages)
                if assistant_messages:
                    latest = assistant_messages[-1]
                    latest_info = latest.get("info")
                    if isinstance(latest_info, dict):
                        final_info = latest_info
                        final_parts = latest.get("parts", [])
                        error = self._assistant_error(final_info)
                        if error is not None:
                            raise OpenCodeServerError(f"OPENCODE_ASSISTANT_ERROR:{error}")
                        final_finish = (
                            str(final_info["finish"])
                            if final_info.get("finish") is not None
                            else self._finish_from_parts(final_parts)
                        )
                        completed = (
                            isinstance(final_info.get("time"), dict)
                            and final_info["time"].get("completed") is not None
                        )
                        if final_finish is not None:
                            break
                        if completed and state not in {"busy", "retry"} and seen_busy:
                            raise OpenCodeServerError("OPENCODE_TERMINAL_FINISH_MISSING")
                time.sleep(0.1)
            else:
                raise OpenCodeRequestTimeout("OPENCODE_SESSION_TIMEOUT")
        except OpenCodeRequestTimeout:
            self._abort_session(session_id, directory)
            raise
        except OpenCodeServerError:
            self._abort_session(session_id, directory)
            raise

        if final_info is None or final_finish is None:
            raise OpenCodeServerError("OPENCODE_TERMINAL_MESSAGE_MISSING")

        tool_event_count = 0
        if isinstance(messages, list):
            for message in messages:
                if not isinstance(message, dict):
                    continue
                for part in message.get("parts", []):
                    if isinstance(part, dict) and part.get("type") == "tool":
                        tool_event_count += 1

        text = "".join(
            str(part.get("text", ""))
            for part in final_parts
            if isinstance(part, dict) and part.get("type") == "text"
        )
        return OpenCodeResult(
            provider=str(final_info.get("providerID") or ""),
            model=str(final_info.get("modelID") or ""),
            cost=float(final_info.get("cost") or 0.0),
            finish=final_finish,
            session_id=session_id,
            message_id=str(final_info["id"]) if final_info.get("id") else None,
            tool_event_count=tool_event_count,
            text=text,
            server_version=str(health.get("version")) if health.get("version") else None,
        )
