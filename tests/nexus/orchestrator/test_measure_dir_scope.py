"""Measurement-only directory scope in ``allowed_files`` (Issue #2721).

With ``NEXUS_MEASURE_DIR_SCOPE=1`` at Gateway start, an ``allowed_files`` entry
may be a directory written with exactly one trailing ``/``.  Without it every
behaviour, including the error text, is what it was before.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from nexus.contracts import measure_dir_scope as mds
from nexus.contracts.lifecycle_action import (
    LifecycleActionEnvelope,
    LifecycleActionType,
    PermissionProfile,
    build_action_envelope,
)
from nexus.orchestrator import measure_external_target as met
from nexus.orchestrator.lifecycle_guards import LifecycleGuardError, pre_action_guard

# Reuse the measurement Gateway fixtures (temporary repositories only).
from tests.nexus.orchestrator.test_measure_external_target import (  # noqa: F401
    _arguments,
    _call,
    _ext_arg,
    _repo,
    gateway_env,
    layout,
)

HEAD = "a" * 40
MANIFEST = "b" * 64
REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
def _switch_off(monkeypatch):
    monkeypatch.setattr(mds, "MEASURE_DIR_SCOPE_AT_START", False)


def _switch_on(monkeypatch) -> None:
    monkeypatch.setattr(mds, "MEASURE_DIR_SCOPE_AT_START", True)


def _envelope(allowed: list[str]) -> LifecycleActionEnvelope:
    return build_action_envelope(
        task_id="dir-task",
        action_type=LifecycleActionType.TASK_RUN,
        request={"what": "bounded", "allowed_files": allowed},
        tool_manifest_hash=MANIFEST,
        expected_head=HEAD,
        allowed_paths=allowed,
        mutation=True,
        permission_profile=PermissionProfile.MUTATE_BOUNDED,
    )


def _envelope_error(allowed: list[str]) -> str:
    with pytest.raises(ValidationError) as caught:
        _envelope(allowed)
    return str(caught.value)


# --------------------------------------------------------------------------
# Envelope
# --------------------------------------------------------------------------


def test_switch_off_envelope_rejects_dir_scope_with_todays_message(monkeypatch):
    message = _envelope_error(["src/pkg/"])
    assert "allowed_paths must be a normalized repository-relative path" in message
    # Byte-identical to the file-path rejection of a non-normalized path today.
    assert message.replace("src/pkg/", "X") == _envelope_error(["src//pkg"]).replace(
        "src//pkg", "X"
    )
    assert _envelope(["src/pkg/mod.py"]).allowed_paths == ("src/pkg/mod.py",)
    monkeypatch.setattr(mds, "MEASURE_DIR_SCOPE_AT_START", True)  # positive control
    assert _envelope(["src/pkg/"]).allowed_paths == ("src/pkg/",)


def test_switch_on_envelope_accepts_one_trailing_slash(monkeypatch):
    _switch_on(monkeypatch)
    envelope = _envelope(["src/pkg/", "README.md", "sympy/"])
    assert envelope.allowed_paths == ("src/pkg/", "README.md", "sympy/")


@pytest.mark.parametrize(
    "bad",
    ["/", "a//", "src/pkg//", "../x/", ".git/", "./a/", "a/../b/", "a/.git/", "/abs/", "a\\b/", ""],
)
def test_switch_on_envelope_rejects_malformed_dir_scopes(monkeypatch, bad):
    _switch_on(monkeypatch)
    assert _envelope(["src/pkg/"]).allowed_paths == ("src/pkg/",)  # positive control
    with pytest.raises(ValidationError):
        _envelope([bad])


def test_switch_on_keeps_other_repo_path_callers_strict(monkeypatch):
    """Only the envelope's ``allowed_paths`` learns ``dir/``; ``task_card_path`` does not."""
    _switch_on(monkeypatch)
    assert _envelope(["src/pkg/"]).allowed_paths == ("src/pkg/",)  # positive control
    with pytest.raises(ValidationError):
        build_action_envelope(
            task_id="dir-task",
            action_type=LifecycleActionType.TASK_RUN,
            request={"what": "bounded"},
            tool_manifest_hash=MANIFEST,
            expected_head=HEAD,
            allowed_paths=["src/pkg/"],
            mutation=True,
            permission_profile=PermissionProfile.MUTATE_BOUNDED,
            task_card_path="tasks/dir/",
            task_card_hash=MANIFEST,
        )


# --------------------------------------------------------------------------
# pre_action_guard
# --------------------------------------------------------------------------


def _guard(action: Any, allowed: list[str], root: Path) -> dict[str, Any]:
    return pre_action_guard(
        action,
        request={"allowed_files": allowed},
        canonical_root=root,
        current_head=HEAD,
        tool_manifest_hash=MANIFEST,
    )


def test_switch_off_pre_action_guard_refuses_dir_scope_as_today(tmp_path, monkeypatch):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    raw = {**_envelope(["src/pkg/mod.py"]).model_dump(mode="json"), "allowed_paths": ["src/pkg/"]}
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(raw, ["src/pkg/"], tmp_path)
    assert caught.value.code == "ACTION_ENVELOPE_INVALID"
    # A file scope is unchanged.
    assert _guard(_envelope(["src/pkg/mod.py"]), ["src/pkg/mod.py"], tmp_path)["passed"] is True
    _switch_on(monkeypatch)  # positive control
    assert _guard(_envelope(["src/pkg/"]), ["src/pkg/"], tmp_path)["passed"] is True


def test_switch_off_pre_action_guard_still_drops_a_slash_from_a_prebuilt_envelope(
    tmp_path, monkeypatch
):
    """An envelope built while on, guarded while off, mismatches exactly as before."""
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    _switch_on(monkeypatch)
    action = _envelope(["src/pkg/"])
    monkeypatch.setattr(mds, "MEASURE_DIR_SCOPE_AT_START", False)
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(action, ["src/pkg/"], tmp_path)
    assert caught.value.code == "ALLOWED_PATH_MISMATCH"


def test_switch_on_pre_action_guard_passes_dir_scope(tmp_path, monkeypatch):
    (tmp_path / "src" / "pkg").mkdir(parents=True)
    _switch_on(monkeypatch)
    receipt = _guard(_envelope(["src/pkg/", "README.md"]), ["src/pkg/", "README.md"], tmp_path)
    assert receipt["passed"] is True
    # A directory that does not exist yet resolves inside the root too.
    assert _guard(_envelope(["newpkg/"]), ["newpkg/"], tmp_path)["passed"] is True
    # The request must name the scope exactly as the envelope does.
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_envelope(["src/pkg/"]), ["src/pkg"], tmp_path)
    assert caught.value.code == "ALLOWED_PATH_MISMATCH"


def test_switch_on_pre_action_guard_refuses_symlink_escape(tmp_path, monkeypatch):
    root = tmp_path / "root"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    (root / "real").mkdir()
    (root / "alias").symlink_to(root / "real", target_is_directory=True)
    (root / "self").symlink_to(root, target_is_directory=True)
    _switch_on(monkeypatch)
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_envelope(["escape/"]), ["escape/"], root)
    assert caught.value.code == "ALLOWED_PATH_INVALID"
    # A link inside the root still does not match its own name (fail closed, as for files),
    # and a link to the root itself never becomes a whole-repository scope.
    for link in ("alias/", "self/"):
        with pytest.raises(LifecycleGuardError) as caught:
            _guard(_envelope([link]), [link], root)
        assert caught.value.code == "ALLOWED_PATH_MISMATCH"


def test_switch_on_pre_action_guard_refuses_traversal_in_a_raw_envelope(tmp_path, monkeypatch):
    _switch_on(monkeypatch)
    raw = {**_envelope(["src/"]).model_dump(mode="json"), "allowed_paths": ["../x/"]}
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(raw, ["../x/"], tmp_path)
    assert caught.value.code == "ACTION_ENVELOPE_INVALID"


# --------------------------------------------------------------------------
# Gateway ingress (nexus_worker_candidate) up to submit
# --------------------------------------------------------------------------


def test_switch_off_gateway_refuses_dir_scope_before_submit(gateway_env, monkeypatch):
    result = _call(gateway_env, _arguments(gateway_env, "dir-off-1", allowed_files=["pkg/"]))
    assert result["isError"] is True
    # Today's refusal: the action envelope rejects the entry, before submit.
    assert (
        "allowed_paths must be a normalized repository-relative path"
        in result["structuredContent"]["error"]
    )
    assert gateway_env["service"].submitted == []
    # Positive control: the same arguments reach submit once the snapshot is on.
    _switch_on(monkeypatch)
    result = _call(gateway_env, _arguments(gateway_env, "dir-off-2", allowed_files=["pkg/"]))
    assert result["isError"] is False, result.get("structuredContent")


def test_switch_on_gateway_dir_scope_reaches_submit(gateway_env, monkeypatch):
    _switch_on(monkeypatch)
    result = _call(gateway_env, _arguments(gateway_env, "dir-on-1", allowed_files=["pkg/"]))
    assert result["isError"] is False, result.get("structuredContent")
    request = gateway_env["service"].submitted[0]
    assert request["allowed_files"] == ["pkg/"]
    assert request["action"]["allowed_paths"] == ["pkg/"]
    assert request["bound_action_request"]["allowed_files"] == ["pkg/"]
    # The service re-runs the same guard on the submitted request.
    receipt = pre_action_guard(
        request["action"],
        request=request,
        canonical_root=gateway_env["card_root"],
        current_head=request["action"]["expected_head"],
        tool_manifest_hash=request["action"]["tool_manifest_hash"],
    )
    assert receipt["passed"] is True


def test_switch_on_gateway_external_target_dir_scope_reaches_submit(gateway_env, monkeypatch):
    _switch_on(monkeypatch)
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    arguments = _arguments(
        gateway_env, "dir-ext-1", external_target=_ext_arg(gateway_env), allowed_files=["pkg/"]
    )
    result = _call(gateway_env, arguments)
    assert result["isError"] is False, result.get("structuredContent")
    request = gateway_env["service"].submitted[0]
    assert request["allowed_files"] == ["pkg/"]
    assert request["action"]["allowed_paths"] == ["pkg/"]
    assert request["action"]["expected_head"] == gateway_env["sha"]
    assert request["controller_repo_root"] == str(gateway_env["ext"].resolve())


def test_switch_on_gateway_external_dir_scope_symlink_escape_is_refused(
    gateway_env, monkeypatch, tmp_path
):
    ext = gateway_env["measure_root"] / "linkrepo"
    ext.mkdir()
    (ext / "escape").symlink_to(tmp_path, target_is_directory=True)
    sha = _repo(ext, {"pkg/mod.py": "VALUE = 1\n"})
    _switch_on(monkeypatch)
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    target = {"repo_root": str(ext), "base_revision": sha}
    result = _call(
        gateway_env,
        _arguments(gateway_env, "dir-ext-2", external_target=target, allowed_files=["escape/"]),
    )
    assert result["isError"] is True
    assert "allowed_files escapes external target root" in result["structuredContent"]["error"]
    assert gateway_env["service"].submitted == []
    # Positive control: a real directory of the same repository is accepted.
    result = _call(
        gateway_env,
        _arguments(gateway_env, "dir-ext-3", external_target=target, allowed_files=["pkg/"]),
    )
    assert result["isError"] is False, result.get("structuredContent")


# --------------------------------------------------------------------------
# The switch is read once, at import
# --------------------------------------------------------------------------


def test_env_set_after_import_has_no_effect(monkeypatch):
    monkeypatch.setenv(mds.MEASURE_DIR_SCOPE_ENV, "1")
    assert mds.MEASURE_DIR_SCOPE_AT_START is False
    assert mds.dir_scope_enabled() is False
    assert "normalized repository-relative path" in _envelope_error(["src/pkg/"])
    # Positive control: only the start-time snapshot turns it on.
    monkeypatch.setattr(mds, "MEASURE_DIR_SCOPE_AT_START", True)
    assert _envelope(["src/pkg/"]).allowed_paths == ("src/pkg/",)


def test_snapshot_is_taken_at_import_and_only_for_exact_one():
    code = (
        "import json, os\n"
        "from nexus.contracts import measure_dir_scope as m\n"
        "first = m.MEASURE_DIR_SCOPE_AT_START\n"
        "os.environ[m.MEASURE_DIR_SCOPE_ENV] = 'flip'\n"
        "print(json.dumps([first, m.MEASURE_DIR_SCOPE_AT_START, m.dir_scope_enabled()]))\n"
    )
    results = {}
    for value in (None, "1", " 1 ", "0", "true", ""):
        env = {k: v for k, v in os.environ.items() if k != mds.MEASURE_DIR_SCOPE_ENV}
        env["PYTHONPATH"] = str(REPO_ROOT)
        if value is not None:
            env[mds.MEASURE_DIR_SCOPE_ENV] = value
        out = subprocess.run(
            [sys.executable, "-c", code],
            env=env,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        results[value] = out
    assert results["1"] == results[" 1 "] == "[true, true, true]"
    for value in (None, "0", "true", ""):
        assert results[value] == "[false, false, false]"


def test_dir_scope_module_has_no_nexus_imports():
    """Shared by contracts and orchestrator: standard library only."""
    source = Path(mds.__file__).read_text(encoding="utf-8")
    assert "import nexus" not in source and "from nexus" not in source


# --------------------------------------------------------------------------
# Deployer: the live launch refuses to start with the switch set
# --------------------------------------------------------------------------


def test_deployer_and_r1_lists_include_the_dir_scope_switch():
    from scripts.ops import mcp_gateway_durable as g
    from scripts.ops import nexus_gateway_auto_deploy as ad

    assert mds.MEASURE_DIR_SCOPE_ENV in ad.MEASUREMENT_ONLY_ENV_VARS
    assert g.R1_MEASUREMENT_ONLY_ENV_VARS == ad.MEASUREMENT_ONLY_ENV_VARS
    assert f"{ad.MEASUREMENT_ENV_REFUSED}:{mds.MEASURE_DIR_SCOPE_ENV}" in ad.measurement_env_guard()
