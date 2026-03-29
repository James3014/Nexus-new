import json
import os
from pathlib import Path
from rich.console import Console

from nexus.pilot_cli.session import PilotSession


def get_config_dir() -> Path:
    base = os.getenv("NEXUS_PILOT_CONFIG_DIR")
    if base:
        return Path(base)
    return Path.home() / ".nexus-pilot"


def get_config_path() -> Path:
    return get_config_dir() / "config.json"


def load_saved_defaults() -> dict:
    path = get_config_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_session_defaults(session: PilotSession) -> None:
    path = get_config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "tenant_id": session.tenant_id,
            "provider": session.provider,
            "model": session.model,
            "workspace": session.workspace,
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        return


def apply_defaults(session: PilotSession) -> PilotSession:
    saved = load_saved_defaults()

    def pick(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return None

    session.tenant_id = pick(
        os.getenv("NEXUS_PILOT_TENANT_ID"),
        session.tenant_id,
        saved.get("tenant_id"),
    )
    session.provider = pick(
        os.getenv("NEXUS_PILOT_PROVIDER"),
        session.provider,
        saved.get("provider"),
    )
    session.model = pick(
        os.getenv("NEXUS_PILOT_MODEL"),
        session.model,
        saved.get("model"),
    )
    session.workspace = pick(
        os.getenv("NEXUS_PILOT_WORKSPACE"),
        session.workspace,
        saved.get("workspace"),
    )
    session.api_key = pick(
        os.getenv("NEXUS_PILOT_API_KEY"),
        session.api_key,
    )
    return session
