from scripts.engine.nexus_cli_registry import deprecated_command_message, deprecated_command_registry


def test_deprecated_command_registry_contains_legacy_status_aliases():
    registry = deprecated_command_registry()

    assert registry["nexus:status"].replacement == "uv run scripts/engine/nexus_cli.py nexus status"
    assert registry["nexus:hud"].replacement == "uv run scripts/engine/nexus_cli.py nexus status"


def test_deprecated_command_message_is_stable_and_actionable():
    message = deprecated_command_message("nexus:closeout")

    assert "DEPRECATED_BLOCKED" in message
    assert "nexus:closeout" in message
    assert "uv run scripts/engine/nexus_cli.py nexus contract-check --contract-file <FILE>" in message
