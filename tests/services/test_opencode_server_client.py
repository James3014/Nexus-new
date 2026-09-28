from __future__ import annotations

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
    assert env["OPENCODE_SERVER_USERNAME"] == "nexus"
    assert env["OPENCODE_SERVER_PASSWORD"]
    assert "GITHUB_TOKEN" not in env
    assert "GH_TOKEN" not in env
    assert "SSH_AUTH_SOCK" not in env


def test_permission_contract_is_read_only_by_default_and_explicit_for_act() -> None:
    plan = OpenCodeServerClient._permission("plan", False)
    assert {"permission": "edit", "pattern": "*", "action": "deny"} in plan
    assert {"permission": "external_directory", "pattern": "*", "action": "deny"} in plan

    with pytest.raises(OpenCodeServerError, match="OPENCODE_ACT_REQUIRES_AUTO_APPROVE"):
        OpenCodeServerClient._permission("act", False)

    act = OpenCodeServerClient._permission("act", True)
    assert act[0] == {"permission": "*", "pattern": "*", "action": "allow"}
    assert {"permission": "external_directory", "pattern": "*", "action": "deny"} in act


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

    def fake_health(*, timeout: float = 2.0):
        return {"healthy": True, "version": "1.18.32"}

    def fake_attest(directory: str, model: str, require_free: bool):
        assert directory == str(tmp_path)
        assert model == "opencode/mimo-v2.6-flash-free"
        assert require_free is True
        return "mimo-v2.6-flash-free"

    def fake_request(method, path, **kwargs):
        calls.append((method, path))
        if method == "POST" and path == "/session":
            return {"id": "ses_test"}
        if method == "POST" and path == "/session/ses_test/message":
            return {
                "info": {
                    "id": "msg_final",
                    "providerID": "opencode",
                    "modelID": "mimo-v2.6-flash-free",
                    "cost": 0,
                    "finish": "stop",
                },
                "parts": [{"type": "text", "text": "OK"}],
            }
        if method == "GET" and path == "/session/ses_test/message":
            return [
                {
                    "info": {"role": "assistant"},
                    "parts": [{"type": "tool", "tool": "read", "state": {"status": "completed"}}],
                },
                {
                    "info": {"role": "assistant"},
                    "parts": [{"type": "text", "text": "OK"}],
                },
            ]
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(client, "ensure_server", fake_health)
    monkeypatch.setattr(client, "_attest_model", fake_attest)
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
    assert result.session_id == "ses_test"
    assert result.tool_event_count == 1
    assert result.text == "OK"
    assert ("POST", "/session/ses_test/message") in calls


def test_run_aborts_session_on_http_timeout(
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
        if method == "POST" and path == "/session/ses_timeout/message":
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
