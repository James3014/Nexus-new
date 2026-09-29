from __future__ import annotations

import socket
from pathlib import Path

import pytest

from nexus.services.opencode_server_client import (
    OpenCodeRequestTimeout,
    OpenCodeServerClient,
    OpenCodeServerError,
)


def _client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> OpenCodeServerClient:
    fake = tmp_path / "opencode"
    fake.write_text("#!/bin/sh\necho 1.18.32\n", encoding="utf-8")
    fake.chmod(0o755)
    monkeypatch.setenv("NEXUS_OPENCODE_BIN", str(fake))
    return OpenCodeServerClient(state_root=tmp_path / "state", port=19497)


def test_server_env_is_isolated_and_strips_owner_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "owner-token")
    monkeypatch.setenv("GH_TOKEN", "owner-gh-token")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/owner-agent")
    client = _client(tmp_path, monkeypatch)

    env = client._server_env()

    assert env["HOME"].startswith(str(client.state_root))
    assert env["XDG_DATA_HOME"].startswith(str(client.state_root))
    assert env["OPENCODE_DISABLE_PROJECT_CONFIG"] == "true"
    assert "OPENCODE_SERVER_USERNAME" not in env
    assert "OPENCODE_SERVER_PASSWORD" not in env
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "SSH_AUTH_SOCK" not in env


def test_permission_policy_blocks_external_directory_and_env_reads() -> None:
    assert OpenCodeServerClient._permission_forbidden({
        "permission": "external_directory",
        "patterns": ["*"],
    })
    assert OpenCodeServerClient._permission_forbidden({
        "permission": "read",
        "patterns": ["/tmp/project/.env"],
    })
    assert OpenCodeServerClient._permission_forbidden({
        "permission": "read",
        "patterns": ["/tmp/project/.env.local"],
    })
    assert not OpenCodeServerClient._permission_forbidden({
        "permission": "read",
        "patterns": ["/tmp/project/README.md"],
    })


def test_plan_rejects_pending_permission_instead_of_auto_approving(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    replies: list[dict[str, str]] = []

    def fake_request(method, path, **kwargs):
        if method == "GET" and path == "/permission":
            return [
                {
                    "id": "per_test",
                    "sessionID": "ses_test",
                    "permission": "bash",
                    "patterns": ["*"],
                }
            ]
        if method == "POST" and path == "/permission/per_test/reply":
            replies.append(kwargs["payload"])
            return True
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(client, "_request", fake_request)
    with pytest.raises(OpenCodeServerError, match="OPENCODE_PERMISSION_REQUIRED:bash"):
        client._handle_pending_permissions(
            session_id="ses_test",
            directory=str(tmp_path),
            mode="plan",
            auto_approve=False,
        )
    assert replies == [{"reply": "reject"}]


def test_act_auto_approve_uses_one_shot_permission_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    replies: list[dict[str, str]] = []

    def fake_request(method, path, **kwargs):
        if method == "GET" and path == "/permission":
            return [
                {
                    "id": "per_test",
                    "sessionID": "ses_test",
                    "permission": "bash",
                    "patterns": ["pwd"],
                }
            ]
        if method == "POST" and path == "/permission/per_test/reply":
            replies.append(kwargs["payload"])
            return True
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(client, "_request", fake_request)
    client._handle_pending_permissions(
        session_id="ses_test",
        directory=str(tmp_path),
        mode="act",
        auto_approve=True,
    )
    assert replies == [{"reply": "once"}]


def test_http_socket_timeout_is_classified_as_opencode_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    def raise_timeout(*args, **kwargs):
        raise socket.timeout("not ready")

    monkeypatch.setattr("urllib.request.urlopen", raise_timeout)
    with pytest.raises(OpenCodeRequestTimeout, match="OPENCODE_HTTP_TIMEOUT"):
        client._request("GET", "/global/health", timeout=0.1)


def test_zero_cost_model_requires_all_declared_costs_zero() -> None:
    assert OpenCodeServerClient._zero_cost({
        "cost": {"input": 0, "output": 0, "cache": {"read": 0, "write": 0}}
    })
    assert not OpenCodeServerClient._zero_cost({
        "cost": {"input": 0, "output": 1, "cache": {"read": 0, "write": 0}}
    })


def test_run_attests_provider_model_cost_and_counts_tool_parts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    calls: list[tuple[str, str]] = []
    status_reads = 0

    monkeypatch.setattr(
        client,
        "ensure_server",
        lambda **kwargs: {"healthy": True, "version": "1.18.32"},
    )
    monkeypatch.setattr(
        client,
        "_attest_model",
        lambda directory, model, require_free: "mimo-v2.6-flash-free",
    )

    def fake_request(method, path, **kwargs):
        nonlocal status_reads
        calls.append((method, path))
        if method == "POST" and path == "/session":
            assert "permission" not in kwargs["payload"]
            return {"id": "ses_test"}
        if method == "POST" and path == "/session/ses_test/prompt_async":
            assert kwargs["expect_json"] is False
            return None
        if method == "GET" and path in {"/permission", "/question"}:
            return []
        if method == "GET" and path == "/session/status":
            status_reads += 1
            return {"ses_test": {"type": "busy"}} if status_reads == 1 else {}
        if method == "GET" and path == "/session/ses_test/message":
            if status_reads == 1:
                return []
            return [
                {
                    "info": {
                        "id": "msg_final",
                        "role": "assistant",
                        "providerID": "opencode",
                        "modelID": "mimo-v2.6-flash-free",
                        "cost": 0,
                        "finish": "stop",
                        "time": {"completed": 1},
                    },
                    "parts": [
                        {"type": "tool", "tool": "read", "state": {"status": "completed"}},
                        {"type": "text", "text": "OK"},
                    ],
                }
            ]
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(client, "_request", fake_request)

    result = client.run(
        model="opencode/mimo-v2.6-flash-free",
        prompt="hello",
        directory=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=30,
        require_free=True,
    )

    assert result.provider == "opencode"
    assert result.model == "mimo-v2.6-flash-free"
    assert result.cost == 0.0
    assert result.finish == "stop"
    assert result.session_id == "ses_test"
    assert result.tool_event_count == 1
    assert result.text == "OK"
    assert ("POST", "/session/ses_test/prompt_async") in calls
    assert ("POST", "/session/ses_test/message") not in calls


def test_run_waits_for_status_terminal_then_reads_assistant_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    monkeypatch.setattr(
        client,
        "ensure_server",
        lambda **kwargs: {"healthy": True, "version": "1.18.32"},
    )
    monkeypatch.setattr(
        client,
        "_attest_model",
        lambda directory, model, require_free: "mimo-v2.6-flash-free",
    )
    status_reads = 0

    def fake_request(method, path, **kwargs):
        nonlocal status_reads
        if method == "POST" and path == "/session":
            return {"id": "ses_race"}
        if method == "POST" and path == "/session/ses_race/prompt_async":
            return None
        if method == "GET" and path in {"/permission", "/question"}:
            return []
        if method == "GET" and path == "/session/status":
            status_reads += 1
            if status_reads == 1:
                return {"ses_race": {"type": "busy"}}
            return {}
        if method == "GET" and path == "/session/ses_race/message":
            if status_reads == 1:
                return [
                    {
                        "info": {
                            "id": "msg_partial",
                            "role": "assistant",
                            "providerID": "opencode",
                            "modelID": "mimo-v2.6-flash-free",
                            "cost": 0,
                        },
                        "parts": [{"type": "text", "text": "partial"}],
                    }
                ]
            return [
                {
                    "info": {
                        "id": "msg_final",
                        "role": "assistant",
                        "providerID": "opencode",
                        "modelID": "mimo-v2.6-flash-free",
                        "cost": 0,
                        "time": {"completed": 2},
                    },
                    "parts": [
                        {"type": "text", "text": "done"},
                        {"type": "step-finish", "reason": "stop"},
                    ],
                }
            ]
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(client, "_request", fake_request)
    result = client.run(
        model="opencode/mimo-v2.6-flash-free",
        prompt="hello",
        directory=str(tmp_path),
        mode="plan",
        auto_approve=False,
        timeout_seconds=20,
        require_free=True,
    )
    assert status_reads == 2
    assert result.finish == "stop"
    assert result.text == "done"
    assert result.message_id == "msg_final"


def test_run_aborts_session_on_poll_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    aborted = False

    monkeypatch.setattr(client, "ensure_server", lambda: {"healthy": True, "version": "1.18.32"})
    monkeypatch.setattr(
        client,
        "_attest_model",
        lambda directory, model, require_free: "mimo-v2.6-flash-free",
    )

    def fake_request(method, path, **kwargs):
        nonlocal aborted
        if method == "POST" and path == "/session":
            return {"id": "ses_timeout"}
        if method == "POST" and path == "/session/ses_timeout/prompt_async":
            return None
        if method == "GET" and path == "/session/status":
            raise OpenCodeRequestTimeout("OPENCODE_HTTP_TIMEOUT")
        if method == "POST" and path == "/session/ses_timeout/abort":
            aborted = True
            return True
        raise AssertionError((method, path))

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(OpenCodeRequestTimeout):
        client.run(
            model="opencode/mimo-v2.6-flash-free",
            prompt="hello",
            directory=str(tmp_path),
            mode="plan",
            auto_approve=False,
            timeout_seconds=1,
            require_free=True,
        )
    assert aborted


def test_run_fails_closed_on_terminal_assistant_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)
    aborted = False

    monkeypatch.setattr(client, "ensure_server", lambda: {"healthy": True, "version": "1.18.32"})
    monkeypatch.setattr(
        client,
        "_attest_model",
        lambda directory, model, require_free: "mimo-v2.6-flash-free",
    )

    def fake_request(method, path, **kwargs):
        nonlocal aborted
        if method == "POST" and path == "/session":
            return {"id": "ses_error"}
        if method == "POST" and path == "/session/ses_error/prompt_async":
            return None
        if method == "GET" and path == "/session/status":
            return {}
        if method == "GET" and path in {"/permission", "/question"}:
            return []
        if method == "GET" and path == "/session/ses_error/message":
            return [
                {
                    "info": {
                        "id": "msg_error",
                        "role": "assistant",
                        "providerID": "opencode",
                        "modelID": "mimo-v2.6-flash-free",
                        "cost": 0,
                        "time": {"completed": 2},
                        "error": {
                            "name": "APIError",
                            "data": {"message": "provider rejected request"},
                        },
                    },
                    "parts": [],
                }
            ]
        if method == "POST" and path == "/session/ses_error/abort":
            aborted = True
            return True
        raise AssertionError((method, path))

    monkeypatch.setattr(client, "_request", fake_request)

    with pytest.raises(OpenCodeServerError, match="OPENCODE_ASSISTANT_ERROR:provider rejected"):
        client.run(
            model="opencode/mimo-v2.6-flash-free",
            prompt="hello",
            directory=str(tmp_path),
            mode="plan",
            auto_approve=False,
            timeout_seconds=5,
            require_free=True,
        )
    assert aborted


def test_auto_free_selects_highest_available_zero_cost_priority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    def fake_request(method, path, **kwargs):
        assert method == "GET"
        assert path == "/provider"
        return {
            "connected": ["opencode"],
            "all": [
                {
                    "id": "opencode",
                    "models": {
                        "mimo-v2.5-free": {
                            "cost": {
                                "input": 0,
                                "output": 0,
                                "cache": {"read": 0, "write": 0},
                            }
                        },
                        "ling-3.0-flash-fin-free": {
                            "cost": {
                                "input": 0,
                                "output": 0,
                                "cache": {"read": 0, "write": 0},
                            }
                        },
                        "paid-free-name-only": {
                            "cost": {
                                "input": 1,
                                "output": 1,
                                "cache": {"read": 0, "write": 0},
                            }
                        },
                    },
                }
            ],
        }

    monkeypatch.setattr(client, "_request", fake_request)

    assert client._attest_model(str(tmp_path), "opencode/auto-free", True) == "mimo-v2.5-free"


def test_explicit_missing_model_never_falls_back_to_auto_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = _client(tmp_path, monkeypatch)

    monkeypatch.setattr(
        client,
        "_request",
        lambda *args, **kwargs: {
            "connected": ["opencode"],
            "all": [
                {
                    "id": "opencode",
                    "models": {
                        "mimo-v2.5-free": {
                            "cost": {
                                "input": 0,
                                "output": 0,
                                "cache": {"read": 0, "write": 0},
                            }
                        }
                    },
                }
            ],
        },
    )

    with pytest.raises(
        OpenCodeServerError,
        match="OPENCODE_MODEL_NOT_AVAILABLE:mimo-v2.6-flash-free",
    ):
        client._attest_model(
            str(tmp_path),
            "opencode/mimo-v2.6-flash-free",
            True,
        )
