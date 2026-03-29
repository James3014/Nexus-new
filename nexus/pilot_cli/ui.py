from rich.console import Console
from nexus.pilot_cli.session import PilotSession


def render_main_screen(session: PilotSession) -> str:
    workspace = session.workspace or "(not set)"
    provider = session.provider or "(not set)"
    model = session.model or "(not set)"
    tenant_id = session.tenant_id or "(not set)"
    return (
        "Nexus Singularity\n"
        f"Tenant: {tenant_id}\n"
        f"Provider: {provider}\n"
        f"Model: {model}\n"
        f"Workspace: {workspace}\n"
        f"Mode: {session.mode}\n\n"
        "Ask anything, paste an error, or mount a repo to start governance.\n"
        "Commands: /mount  /govern  /status  /provider  /model  /exit\n\n"
        "NEXUS >"
    )
