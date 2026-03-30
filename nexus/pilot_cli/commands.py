from nexus.pilot_cli.gateway import govern_via_gateway
from nexus.pilot_cli.session import PilotSession
from nexus.pilot_cli.workspace_ops import clone_repo
from nexus.pilot_cli.workspace_ops import is_repo_url


def handle_command(command: str, session: PilotSession) -> str:
    parts = command.split(maxsplit=1)
    verb = parts[0]
    arg = parts[1].strip() if len(parts) > 1 else ""

    if verb == "/status":
        return session.describe()
    if verb == "/reset":
        session.reset_context()
        return "Context reset. Workspace cleared and mode restored to FAST."
    if verb == "/mount":
        if not arg:
            return "Usage: /mount <workspace>"
        if is_repo_url(arg):
            return "GitHub URL detected. Use /clone <repo-url> to fetch it locally first."
        session.workspace = arg
        return f"Mounted workspace: {arg}"
    if verb == "/clone":
        if not arg:
            return "Usage: /clone <repo-url> [dest]"
        parts = arg.split(maxsplit=1)
        repo_url = parts[0]
        dest = parts[1].strip() if len(parts) > 1 else None
        target = clone_repo(repo_url, session.tenant_id or "anonymous-tenant", dest=dest)
        session.workspace = str(target)
        return f"Cloned repo to {target}\nMounted workspace: {target}"
    if verb == "/provider":
        if not arg:
            return "Usage: /provider <name>"
        session.provider = arg
        return f"Provider set to {arg}"
    if verb == "/model":
        if not arg:
            return "Usage: /model <name>"
        session.model = arg
        return f"Model set to {arg}"
    if verb == "/govern":
        request = arg or session.last_user_request
        if not request:
            return "No governance request found. Provide one, or ask in natural language first."
        result = govern_via_gateway(session, request)
        return (
            f"Battle Mode engaged.\nTask: {result['task_id']}\n\n{result['summary']}"
        )
    if verb == "/exit":
        return "EXIT"
    return f"Unknown command: {command}"
