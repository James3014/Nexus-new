from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeprecatedCommand:
    name: str
    replacement: str


def deprecated_command_registry() -> dict[str, DeprecatedCommand]:
    commands = (
        DeprecatedCommand("nexus:status", "uv run scripts/engine/nexus_cli.py nexus status"),
        DeprecatedCommand("nexus:hud", "uv run scripts/engine/nexus_cli.py nexus status"),
        DeprecatedCommand("nexus:spec-lock", "MUSE_ENGINE_SPEC 審計已整合入 ci_gate。"),
        DeprecatedCommand("nexus:governance-check", "uv run scripts/ops/ci_gate.py --dry-run"),
        DeprecatedCommand(
            "nexus:acceptance-check",
            "uv run scripts/engine/nexus_cli.py nexus acceptance-check --evidence <FILE>",
        ),
        DeprecatedCommand(
            "nexus:closeout",
            "uv run scripts/engine/nexus_cli.py nexus contract-check --contract-file <FILE>",
        ),
    )
    return {command.name: command for command in commands}


def deprecated_command_names() -> list[str]:
    return sorted(deprecated_command_registry())


def deprecated_command_message(name: str) -> str:
    command = deprecated_command_registry().get(name)
    replacement = command.replacement if command else ""
    return f"❌ [DEPRECATED_BLOCKED] 此命令 '{name}' 已停用。\n💡 請改用唯一新入口：\n   {replacement}"
