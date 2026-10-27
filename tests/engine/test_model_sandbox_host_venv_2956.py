"""#2956: model output still runs when the host's own interpreter sits under a denied subtree.

The deployed Gateway runs from a venv under ``~/Library/Application Support``, a subtree the
model sandbox denies. Granting the host's interpreter prefixes made ``checked_read_roots``
refuse every model-output run there (``sandbox_read_root_inside_forbidden``), even
``/bin/echo``. Model output never runs host code, so the model sandbox no longer grants them;
other confined lanes keep granting them. Without an OS barrier nothing runs. No test skips.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from nexus.core.drone_engine import DroneToolBox
from nexus.engine import model_output_sandbox as mos
from nexus.engine import sandboxed_lane
from nexus.engine.sandboxed_lane import SandboxError, confinement, os_sandbox_available
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierRequest,
    run_isolated_verifier,
)


def _gateway_like_prefix() -> Path:
    home = Path(os.path.expanduser("~")).resolve()
    return home / "Library" / "Application Support" / "Nexus" / "gateway-direct" / "venvs" / "a1"


@pytest.fixture
def host_prefix_in_denied_subtree(monkeypatch):
    # What the deployed Gateway reports as sys.prefix (the path need not exist).
    prefix = str(_gateway_like_prefix())
    monkeypatch.setattr(sandboxed_lane, "interpreter_read_roots", lambda: [prefix, prefix])
    return prefix


def test_drone_bash_runs_when_the_host_venv_is_under_a_denied_subtree(
    tmp_path, host_prefix_in_denied_subtree
):
    out = DroneToolBox(tmp_path).bash_exec("/bin/echo hi")
    if not os_sandbox_available():
        assert out["exit_code"] == -1 and "no_os_barrier" in out["stderr"]
        return
    assert out == {"exit_code": 0, "stdout": "hi\n", "stderr": ""}


def test_isolated_verifier_runs_its_own_interpreter(tmp_path, host_prefix_in_denied_subtree):
    receipt = run_isolated_verifier(
        IsolatedVerifierRequest(
            task_id="t-2956",
            workspace_path=str(tmp_path),
            verifier_command=(sys.executable, "-I", "-c", "open('ok.txt', 'w').write('x')"),
            verifier_allowed=True,
        )
    )
    if not os_sandbox_available():
        assert receipt.verifier_status == "blocked"
        assert "no_os_barrier" in receipt.verifier_error
        return
    assert receipt.verifier_status == "pass", receipt
    assert (tmp_path / "ok.txt").exists()


def test_the_host_interpreter_is_not_readable_by_model_output(tmp_path, monkeypatch):
    # Least privilege: a model command naming an interpreter by absolute path gets no read
    # roots, and the host's prefixes are not granted either, so it cannot start.
    monkeypatch.setattr(
        sandboxed_lane, "interpreter_read_roots", lambda: [sys.prefix, sys.base_prefix]
    )
    if not os_sandbox_available():
        with pytest.raises(SandboxError, match="no_os_barrier"):
            mos.run_model_command_string(
                f"{sys.executable} -I -c pass", work_dir=tmp_path, timeout=20
            )
        return
    res = mos.run_model_command_string(
        f"{sys.executable} -I -c \"print('STARTED')\"", work_dir=tmp_path, timeout=20
    )
    assert res.returncode != 0
    assert "STARTED" not in res.stdout


def test_other_lanes_still_grant_and_check_the_host_interpreter(
    tmp_path, host_prefix_in_denied_subtree
):
    denied = _gateway_like_prefix().parent.parent
    if not os_sandbox_available():
        with pytest.raises(SandboxError, match="no_os_barrier"):
            confinement(sandbox=tmp_path, forbidden_subtrees=[denied])
        return
    with pytest.raises(SandboxError, match="sandbox_read_root_inside_forbidden"):
        confinement(sandbox=tmp_path, forbidden_subtrees=[denied])
    bound = confinement(
        sandbox=tmp_path, forbidden_subtrees=[denied], host_interpreter_readable=False
    )
    assert host_prefix_in_denied_subtree not in bound.profile
