"""Static pins for the #2620 hardening of two legacy personal scripts.

Both scripts need third-party packages (fastapi, trafilatura) that are not
project dependencies, so these tests inspect the source instead of importing it.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
BRIDGE = REPO_ROOT / "scripts" / "tg_pty_bridge.py"
DASHBOARD = REPO_ROOT / "scripts" / "script_dashboard.py"
SWARM_PAGE = REPO_ROOT / "scripts" / "Swarm_Dashboard.html"

# A Telegram bot token is "<digits>:<35 url-safe chars>"; Jina keys start with "jina_".
TELEGRAM_TOKEN_RE = re.compile(r"\d{8,10}:[A-Za-z0-9_-]{30,}")
JINA_KEY_RE = re.compile(r"jina_[A-Za-z0-9]{20,}")


def _module_assignments(path: Path) -> dict[str, ast.expr]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, ast.expr] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found.setdefault(target.id, node.value)
    return found


def _is_env_lookup(expr: ast.expr) -> bool:
    for node in ast.walk(expr):
        if isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            if func in {"os.environ.get", "os.getenv"}:
                return True
    return False


def test_bridge_has_no_credential_literals() -> None:
    source = BRIDGE.read_text(encoding="utf-8")
    assert not TELEGRAM_TOKEN_RE.search(source)
    assert not JINA_KEY_RE.search(source)


def test_bridge_reads_credentials_from_environment() -> None:
    assigned = _module_assignments(BRIDGE)
    assert _is_env_lookup(assigned["TOKEN"])
    assert _is_env_lookup(assigned["JINA_KEY"])
    assert 'raise SystemExit("NEXUS_TG_BOT_TOKEN is not set")' in BRIDGE.read_text(encoding="utf-8")


def test_bridge_filters_on_sender_allowlist_before_handling() -> None:
    source = BRIDGE.read_text(encoding="utf-8")
    assert "NEXUS_TG_ALLOWED_USER_IDS" in source
    gate = source.index('if msg.get("from", {}).get("id") not in ALLOWED_USER_IDS:')
    assert gate < source.rindex("handle_message(chat_id, text)")


def test_dashboard_has_no_fallback_token_literal() -> None:
    assigned = _module_assignments(DASHBOARD)
    token = assigned["ACCESS_TOKEN"]
    assert _is_env_lookup(token)
    for node in ast.walk(ast.parse(DASHBOARD.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "ACCESS_TOKEN" for t in node.targets
        ):
            assert not (isinstance(node.value, ast.Constant) and isinstance(node.value.value, str))


def test_dashboard_requires_token_on_every_api_route() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    assert 'request.url.path.startswith("/api/")' in source
    assert "hmac.compare_digest(supplied.encode(), ACCESS_TOKEN.encode())" in source
    assert "status_code=503" in source
    assert 'TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost"]' in source


def test_dashboard_does_not_embed_token_in_pages() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "__MUSE_TOKEN__" not in source
    for page in (source, SWARM_PAGE.read_text(encoding="utf-8")):
        assert "'X-Muse-Token': museToken()" in page
        assert "sessionStorage.getItem('museToken')" in page


def test_dashboard_run_route_uses_component_containment() -> None:
    source = DASHBOARD.read_text(encoding="utf-8")
    assert "target_path.is_relative_to(TARGET_DIR)" in source
    assert "if not str(target_path).startswith(str(TARGET_DIR)):" not in source
