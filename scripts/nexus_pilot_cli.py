#!/usr/bin/env python3
import sys
from pathlib import Path
import traceback


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from nexus.pilot_cli.commands import handle_command
from nexus.pilot_cli.gateway import (
    build_governance_payload,
    chat_via_gateway,
    ensure_local_gateway_running,
)
from nexus.pilot_cli.health_actions import (
    begin_self_check_prompt,
    begin_self_heal_prompt,
    resolve_pending_health_choice,
    run_pilot_health_command,
)
from nexus.pilot_cli.input_engine import read_interactive_line
from nexus.pilot_cli.onboarding import prompt_for_missing_session_fields
from nexus.pilot_cli.router import route_input
from nexus.pilot_cli.session import PilotSession
from nexus.pilot_cli.ui import render_main_screen


def handle_user_input(user_input: str, session: PilotSession) -> str:
    handled, output = resolve_pending_health_choice(session, user_input)
    if handled:
        return output or ""

    session.last_user_request = user_input
    if user_input.startswith("/"):
        return handle_command(user_input, session)

    route = route_input(user_input)
    if route.lane == "SELF_CHECK_PROMPT":
        return begin_self_check_prompt(session)
    if route.lane == "SELF_HEAL_PROMPT":
        return begin_self_heal_prompt(session)
    if route.lane == "BATTLE_CONFIRM":
        payload = build_governance_payload(session, user_input)
        task_hint = payload.get("tenant_id") or "unassigned-tenant"
        return (
            "Governance task detected. Ready to enter Battle Mode.\n"
            f"Task scope prepared for tenant: {task_hint}\n"
            "Run /govern to queue the task."
        )
    try:
        return chat_via_gateway(session, user_input)
    except Exception:
        log_path = REPO_ROOT / "logs" / "pilot" / "fastlane_errors.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.write_text(
            f"REQUEST:\n{user_input}\n\nERROR:\n{traceback.format_exc()}\n",
            encoding="utf-8",
        )
        return (
            "Initial diagnosis: request accepted in Fast Lane.\n"
            "Share an error, ask a question, or escalate with /govern."
        )


def process_repl_line(user_input: str, pending_lines: list, session: PilotSession):
    stripped = user_input.strip()
    if stripped == "":
        return [], pending_lines
    return [handle_user_input(user_input, session)], pending_lines


def repl() -> int:
    session = PilotSession()
    session = prompt_for_missing_session_fields(session)
    ensure_local_gateway_running()
    print(render_main_screen(session))
    while True:
        try:
            user_input = read_interactive_line("NEXUS > ")
        except EOFError:
            session.clear_secrets()
            return 0
        except KeyboardInterrupt:
            print("\nOperation aborted. Use /exit to quit.")
            continue

        outputs, _ = process_repl_line(user_input, [], session)
        for output in outputs:
            if output == "EXIT":
                session.clear_secrets()
                return 0
            print(output)


def main() -> int:
    return repl()


if __name__ == "__main__":
    raise SystemExit(main())
