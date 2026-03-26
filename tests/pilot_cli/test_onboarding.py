from nexus.pilot_cli.session import PilotSession
from nexus.pilot_cli.onboarding import build_session_from_answers
from nexus.pilot_cli.onboarding import prompt_for_missing_session_fields
from nexus.pilot_cli.ui import render_main_screen


def test_session_defaults():
    session = PilotSession()
    assert session.tenant_id is None
    assert session.mode == "FAST"


def test_render_main_screen_includes_session_state():
    session = PilotSession(
        tenant_id="pilot_a",
        provider="OpenAI",
        model="gpt-5.4",
        workspace="~/project",
    )
    screen = render_main_screen(session)
    assert "Tenant: pilot_a" in screen
    assert "Provider: OpenAI" in screen
    assert "Model: gpt-5.4" in screen
    assert "Workspace: ~/project" in screen
    assert "Mode: FAST" in screen


def test_onboarding_builds_session_from_answers():
    session = build_session_from_answers(
        tenant_id="tenant_a",
        provider="OpenAI",
        api_key="sk-test",
        model="gpt-5.4",
        workspace="~/repo",
    )
    assert session.tenant_id == "tenant_a"
    assert session.provider == "OpenAI"
    assert session.model == "gpt-5.4"
    assert session.workspace == "~/repo"


def test_prompt_for_missing_session_fields_collects_answers():
    import tempfile
    from pathlib import Path

    config_dir = Path(tempfile.mkdtemp(prefix="nexus-pilot-test-"))
    import os
    os.environ["NEXUS_PILOT_CONFIG_DIR"] = str(config_dir)
    os.environ.pop("NEXUS_PILOT_TENANT_ID", None)
    os.environ["NEXUS_PILOT_DEFAULT_TENANT_ID"] = "tenant_a"
    os.environ.pop("NEXUS_PILOT_PROVIDER", None)
    os.environ.pop("NEXUS_PILOT_MODEL", None)
    os.environ.pop("NEXUS_PILOT_WORKSPACE", None)
    os.environ.pop("NEXUS_PILOT_API_KEY", None)

    session = PilotSession()
    answers = iter(["sk-test"])

    updated = prompt_for_missing_session_fields(
        session,
        input_fn=lambda prompt: next(answers),
    )

    assert updated.tenant_id == "pilot_tenant_a"
    assert updated.provider == "OpenAI"
    assert updated.api_key == "sk-test"
    assert updated.model == "gpt-5.4"
    assert updated.workspace is None


def test_prompt_for_missing_session_fields_only_requires_api_key_when_defaults_missing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("NEXUS_PILOT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("NEXUS_PILOT_TENANT_ID", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_MODEL", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_WORKSPACE", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_API_KEY", raising=False)

    prompts = []
    updated = prompt_for_missing_session_fields(
        PilotSession(),
        input_fn=lambda prompt: prompts.append(prompt) or "AIza-test",
    )

    assert prompts == ["API Key: "]
    assert updated.tenant_id is not None
    assert updated.workspace is None
    assert updated.api_key == "AIza-test"
    assert updated.provider == "Gemini"
    assert updated.model == "gemini-2.5-flash"


def test_prompt_for_missing_session_fields_uses_saved_defaults(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_PILOT_CONFIG_DIR", str(tmp_path))
    config_file = tmp_path / "config.json"
    config_file.write_text(
        '{"tenant_id":"pilot_saved","provider":"Gemini","model":"gemini-2.5-flash","workspace":"~/saved"}',
        encoding="utf-8",
    )
    session = PilotSession()
    answers = iter(["AIza-test"])

    updated = prompt_for_missing_session_fields(
        session,
        input_fn=lambda prompt: next(answers),
    )

    assert updated.tenant_id == "pilot_saved"
    assert updated.provider == "Gemini"
    assert updated.model == "gemini-2.5-flash"
    assert updated.workspace == "~/saved"
    assert updated.api_key == "AIza-test"


def test_prompt_for_missing_session_fields_does_not_prompt_for_workspace(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_PILOT_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("NEXUS_PILOT_TENANT_ID", "pilot_env")
    monkeypatch.setenv("NEXUS_PILOT_PROVIDER", "Gemini")
    monkeypatch.setenv("NEXUS_PILOT_MODEL", "gemini-2.5-flash")
    monkeypatch.delenv("NEXUS_PILOT_WORKSPACE", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_API_KEY", raising=False)

    prompts = []
    updated = prompt_for_missing_session_fields(
        PilotSession(),
        input_fn=lambda prompt: prompts.append(prompt) or "AIza-env",
    )

    assert prompts == ["API Key: "]
    assert updated.workspace is None
    assert updated.api_key == "AIza-env"


def test_prompt_for_missing_session_fields_prefers_env_defaults(monkeypatch, tmp_path):
    monkeypatch.setenv("NEXUS_PILOT_CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("NEXUS_PILOT_TENANT_ID", "pilot_env")
    monkeypatch.setenv("NEXUS_PILOT_PROVIDER", "Gemini")
    monkeypatch.setenv("NEXUS_PILOT_MODEL", "gemini-2.5-flash")
    monkeypatch.setenv("NEXUS_PILOT_WORKSPACE", "~/env-workspace")
    monkeypatch.setenv("NEXUS_PILOT_API_KEY", "AIza-env")

    updated = prompt_for_missing_session_fields(
        PilotSession(),
        input_fn=lambda prompt: "",
    )

    assert updated.tenant_id == "pilot_env"
    assert updated.provider == "Gemini"
    assert updated.model == "gemini-2.5-flash"
    assert updated.workspace == "~/env-workspace"
    assert updated.api_key == "AIza-env"


def test_prompt_for_missing_session_fields_keeps_openai_for_sk_keys(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_PILOT_CONFIG_DIR", str(tmp_path))
    monkeypatch.delenv("NEXUS_PILOT_TENANT_ID", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_PROVIDER", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_MODEL", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_WORKSPACE", raising=False)
    monkeypatch.delenv("NEXUS_PILOT_API_KEY", raising=False)

    updated = prompt_for_missing_session_fields(
        PilotSession(),
        input_fn=lambda prompt: "sk-test",
    )

    assert updated.provider == "OpenAI"
    assert updated.model == "gpt-5.4"
