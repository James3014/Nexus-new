from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from nexus.pilot_cli.session import PilotSession


SELF_CHECK_CHOICES = {
    "1": "quick",
    "2": "standard",
    "3": "high",
    "4": "full",
    "quick": "quick",
    "快速": "quick",
    "standard": "standard",
    "標準": "standard",
    "high": "high",
    "高標": "high",
    "strict": "high",
    "full": "full",
    "完整": "full",
}

SELF_HEAL_CHOICES = {
    "1": "dry-run",
    "2": "standard",
    "3": "strict",
    "dry-run": "dry-run",
    "dry": "dry-run",
    "試跑": "dry-run",
    "standard": "standard",
    "標準": "standard",
    "strict": "strict",
    "嚴格": "strict",
}


def begin_self_check_prompt(session: PilotSession) -> str:
    session.pending_action = "self_check"
    return (
        "選擇自檢強度：\n"
        "1. quick\n"
        "2. standard\n"
        "3. high\n"
        "4. full\n"
        "直接回覆數字或等級名稱。"
    )


def begin_self_heal_prompt(session: PilotSession) -> str:
    session.pending_action = "self_heal"
    return (
        "選擇自癒模式：\n"
        "1. dry-run\n"
        "2. standard\n"
        "3. strict\n"
        "直接回覆數字或模式名稱。"
    )


def resolve_pending_health_choice(session: PilotSession, user_input: str) -> tuple[bool, str | None]:
    action = session.pending_action
    if action not in {"self_check", "self_heal"}:
        return False, None

    normalized = user_input.strip().lower()
    mapping = SELF_CHECK_CHOICES if action == "self_check" else SELF_HEAL_CHOICES
    selected = mapping.get(normalized)
    if not selected:
        prompt = begin_self_check_prompt(session) if action == "self_check" else begin_self_heal_prompt(session)
        return True, f"我需要一個有效選項。\n{prompt}"

    session.pending_action = None
    return True, run_pilot_health_command(action, selected)


def run_pilot_health_command(action: str, level: str) -> str:
    repo_root = Path(__file__).resolve().parents[2]
    cli_path = repo_root / "scripts" / "engine" / "nexus_cli.py"
    command = (
        [sys.executable, str(cli_path), "nexus:check", "--level", level]
        if action == "self_check"
        else [sys.executable, str(cli_path), "nexus:self-heal", "--mode", level]
    )
    completed = subprocess.run(
        command,
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or completed.stderr or "").strip()
    if completed.returncode != 0:
        return output or f"{action} failed with exit code {completed.returncode}"
    return output or f"{action}:{level}"
