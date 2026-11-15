from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

_CASES = [
    (
        "nexus.orchestrator.break_glass_recovery",
        {"DEFAULT_BREAK_GLASS_ROOT": ".local/state/nexus/authority/break-glass"},
    ),
    (
        "nexus.orchestrator.standing_grant_store",
        {
            "DEFAULT_RECEIPT_PATH": ".local/state/nexus/authority/standing-grant.json",
            "DEFAULT_TRANSITIONS_DIR": ".local/state/nexus/authority/transitions",
        },
    ),
    (
        "nexus.orchestrator.owner_representation_store",
        {
            "DEFAULT_OWNER_REPRESENTATION_AUTHORITY_ROOT": (
                ".local/state/nexus/authority/owner-representation"
            )
        },
    ),
]

_SCRIPT = textwrap.dedent(
    """
    import importlib, json, pwd, sys

    error = {"KeyError": KeyError, "OSError": OSError}[sys.argv[1]]

    def missing(_uid):
        raise error(_uid)

    pwd.getpwuid = missing
    module = importlib.import_module(sys.argv[2])
    print(json.dumps({name: str(getattr(module, name)) for name in sys.argv[3:]}))
    """
)


@pytest.mark.parametrize("error_name", ["KeyError", "OSError"])
@pytest.mark.parametrize(("module_name", "attributes"), _CASES)
def test_import_uses_fixed_home_fallback_ignoring_environment(
    module_name: str, attributes: dict[str, str], error_name: str
) -> None:
    env = {**os.environ, "HOME": "/environment-home-must-be-ignored"}
    env["PYTHONPATH"] = str(_REPO_ROOT)
    result = subprocess.run(
        [sys.executable, "-c", _SCRIPT, error_name, module_name, *attributes],
        capture_output=True,
        text=True,
        env=env,
        cwd=_REPO_ROOT,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    loaded = json.loads(result.stdout.strip().splitlines()[-1])
    fallback_home = f"/nonexistent-home-uid-{os.getuid()}"
    for name, relative in attributes.items():
        assert loaded[name] == f"{fallback_home}/{relative}"
