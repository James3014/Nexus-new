from nexus.pilot_cli.commands import handle_command
from nexus.pilot_cli.session import PilotSession
from scripts import nexus_chat_cli as legacy_chat_cli
from scripts.nexus_pilot_cli import handle_user_input, process_repl_line


def test_status_command_returns_session_summary():
    session = PilotSession(
        tenant_id="pilot_a",
        provider="OpenAI",
        model="gpt-5.4",
        workspace="~/repo",
    )
    output = handle_command("/status", session)
    assert "pilot_a" in output
    assert "OpenAI" in output
    assert "gpt-5.4" in output
    assert "Gateway:" in output


def test_reset_command_clears_workspace_context():
    session = PilotSession(
        tenant_id="pilot_a",
        provider="OpenAI",
        model="gpt-5.4",
        workspace="~/repo",
    )
    output = handle_command("/reset", session)
    assert session.workspace is None
    assert "Context reset" in output


def test_natural_language_fast_lane_returns_quick_response():
    session = PilotSession()
    output = handle_user_input("這個錯誤代表什麼", session)
    assert output.strip()
    assert "Battle Mode" not in output


def test_natural_language_fix_request_returns_battle_prompt():
    session = PilotSession()
    output = handle_user_input("幫我修這個 bug", session)
    assert "Battle Mode" in output


def test_mount_command_sets_workspace():
    session = PilotSession()
    output = handle_command("/mount ~/repo", session)
    assert session.workspace == "~/repo"
    assert "Mounted workspace" in output


def test_mount_command_rejects_repo_url():
    session = PilotSession()
    output = handle_command("/mount https://github.com/example/repo.git", session)
    assert "Use /clone <repo-url>" in output


def test_clone_command_clones_and_mounts_repo(monkeypatch):
    session = PilotSession(tenant_id="pilot_a")

    monkeypatch.setattr(
        "nexus.pilot_cli.commands.clone_repo",
        lambda repo_url, tenant_id, dest=None: __import__("pathlib").Path("/tmp/pilot-a/repo"),
    )

    output = handle_command("/clone https://github.com/example/repo.git", session)
    assert "Cloned repo to /tmp/pilot-a/repo" in output
    assert session.workspace == "/tmp/pilot-a/repo"


def test_provider_command_updates_provider():
    session = PilotSession(provider="OpenAI")
    output = handle_command("/provider Gemini", session)
    assert session.provider == "Gemini"
    assert "Provider set to Gemini" in output


def test_model_command_updates_model():
    session = PilotSession(model="gpt-5.4")
    output = handle_command("/model gemini-2.5-flash", session)
    assert session.model == "gemini-2.5-flash"
    assert "Model set to gemini-2.5-flash" in output


def test_single_line_input_submits_immediately():
    session = PilotSession(provider="OpenAI", model="gpt-5.4")
    pending = []

    outputs, pending = process_repl_line("第一行", pending, session)
    assert len(outputs) == 1
    assert outputs[0].strip()
    assert pending == []


def test_repl_no_longer_buffers_followup_lines():
    session = PilotSession(provider="OpenAI", model="gpt-5.4")
    pending = ["第一行"]

    outputs, pending = process_repl_line("第二行", pending, session)
    assert len(outputs) == 1
    assert outputs[0].strip()
    assert pending == ["第一行"]


def test_command_executes_without_flushing_legacy_pending_buffer():
    session = PilotSession(provider="OpenAI", model="gpt-5.4")
    pending = ["長題第一行", "長題第二行"]

    outputs, pending = process_repl_line("/status", pending, session)
    assert len(outputs) == 1
    assert "Tenant:" in outputs[0]
    assert pending == ["長題第一行", "長題第二行"]


def test_legacy_chat_cli_shim_points_to_new_entry():
    assert legacy_chat_cli.handle_user_input is handle_user_input
    assert legacy_chat_cli.process_repl_line is process_repl_line
