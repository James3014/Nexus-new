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
    _run,
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


def _envelope(allowed: list[str], *, head: str = HEAD) -> LifecycleActionEnvelope:
    return build_action_envelope(
        task_id="dir-task",
        action_type=LifecycleActionType.TASK_RUN,
        request={"what": "bounded", "allowed_files": allowed},
        tool_manifest_hash=MANIFEST,
        expected_head=head,
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
    [
        "/",
        "a//",
        "src/pkg//",
        "../x/",
        ".git/",
        "./a/",
        "a/../b/",
        "a/.git/",
        "/abs/",
        "a\\b/",
        "",
        "./",
        ".",
        "a/./",
        "./.",
        "a/../",
    ],
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


def _guard(
    action: Any,
    allowed: list[str],
    root: Path,
    ext: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request: dict[str, Any] = {"allowed_files": allowed}
    if ext is not None:
        request.update({"worker_candidate_ingress": True, "controller_repo_root": str(ext["ext"])})
    return pre_action_guard(
        action,
        request=request,
        canonical_root=root,
        current_head=ext["sha"] if ext is not None else HEAD,
        tool_manifest_hash=MANIFEST,
    )


@pytest.fixture
def ext(layout, monkeypatch) -> dict[str, Any]:
    """A clean measurement external target with real directories and tracked symlinks."""
    monkeypatch.setattr(met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(layout["measure_root"]))
    repo = layout["measure_root"] / "dirrepo"
    files = {
        "README.md": "x\n",
        "src/pkg/mod.py": "VALUE = 1\n",
        "real/r.py": "R = 1\n",
        "docsx/a.md": "a\n",
        "docs/governance/g.md": "g\n",
        ".github/workflows/w.yml": "w\n",
        ".nexus-core/c.txt": "c\n",
        "a/b.py": "B = 1\n",
    }
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text, encoding="utf-8")
    # Tracked symlinks inside the EXTERNAL repository (#2786 r2).
    (repo / "alias").symlink_to(".", target_is_directory=True)
    (repo / "govalias").symlink_to("docs/governance", target_is_directory=True)
    (repo / "a" / "link").symlink_to("..", target_is_directory=True)
    sha = _repo(repo, {})
    return {**layout, "ext": repo, "sha": sha}


def _ext_envelope(allowed: list[str], ext: dict[str, Any]) -> LifecycleActionEnvelope:
    return _envelope(allowed, head=ext["sha"])


def _canon(tmp_path: Path) -> Path:
    # Kept apart from the measurement root, which must not overlap the Nexus root.
    root = tmp_path / "canon"
    (root / "src" / "pkg").mkdir(parents=True, exist_ok=True)
    if not (root / ".git").exists():
        _run("init", "-q", cwd=root)  # the Nexus identity (common dir) must be readable
    return root


def test_switch_off_pre_action_guard_refuses_dir_scope_as_today(tmp_path, monkeypatch, ext):
    root = _canon(tmp_path)
    raw = {**_envelope(["src/pkg/mod.py"]).model_dump(mode="json"), "allowed_paths": ["src/pkg/"]}
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(raw, ["src/pkg/"], root)
    assert caught.value.code == "ACTION_ENVELOPE_INVALID"
    # A file scope is unchanged.
    assert _guard(_envelope(["src/pkg/mod.py"]), ["src/pkg/mod.py"], root)["passed"] is True
    _switch_on(monkeypatch)  # positive control
    assert _guard(_ext_envelope(["src/pkg/"], ext), ["src/pkg/"], root, ext)["passed"] is True


def test_switch_off_pre_action_guard_still_drops_a_slash_from_a_prebuilt_envelope(
    tmp_path, monkeypatch, ext
):
    """An envelope built while on, guarded while off, mismatches exactly as before."""
    root = _canon(tmp_path)
    _switch_on(monkeypatch)
    action = _ext_envelope(["src/pkg/"], ext)
    monkeypatch.setattr(mds, "MEASURE_DIR_SCOPE_AT_START", False)
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(action, ["src/pkg/"], root, ext)
    assert caught.value.code == "ALLOWED_PATH_MISMATCH"


def test_switch_on_pre_action_guard_passes_dir_scope(tmp_path, monkeypatch, ext):
    root = _canon(tmp_path)
    _switch_on(monkeypatch)
    receipt = _guard(
        _ext_envelope(["src/pkg/", "README.md"], ext), ["src/pkg/", "README.md"], root, ext
    )
    assert receipt["passed"] is True
    # A directory that does not exist yet resolves inside the root too.
    # A directory missing from the external repository is refused (#2786 r2).
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_ext_envelope(["newpkg/"], ext), ["newpkg/"], root, ext)
    assert caught.value.code == "ALLOWED_PATH_INVALID"
    # The request must name the scope exactly as the envelope does.
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_ext_envelope(["src/pkg/"], ext), ["src/pkg"], root, ext)
    assert caught.value.code == "ALLOWED_PATH_MISMATCH"


def test_switch_on_pre_action_guard_refuses_symlink_escape(tmp_path, monkeypatch, ext):
    root = _canon(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    (root / "real").mkdir()
    (root / "a").symlink_to(root / "real", target_is_directory=True)
    (root / "self").symlink_to(root, target_is_directory=True)
    _switch_on(monkeypatch)
    assert _guard(_ext_envelope(["real/"], ext), ["real/"], root, ext)["passed"] is True
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_ext_envelope(["escape/"], ext), ["escape/"], root, ext)
    assert caught.value.code == "ALLOWED_PATH_INVALID"
    # A link inside the root still does not match its own name (fail closed, as for files).
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_ext_envelope(["a/"], ext), ["a/"], root, ext)
    assert caught.value.code == "ALLOWED_PATH_MISMATCH"
    # A link to the root itself never becomes a whole-repository scope.
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_ext_envelope(["self/"], ext), ["self/"], root, ext)
    assert caught.value.code == "ALLOWED_PATH_INVALID"


def test_switch_on_pre_action_guard_refuses_traversal_in_a_raw_envelope(tmp_path, monkeypatch, ext):
    root = _canon(tmp_path)
    _switch_on(monkeypatch)
    assert _guard(_ext_envelope(["src/"], ext), ["src/"], root, ext)["passed"] is True
    raw = {**_ext_envelope(["src/"], ext).model_dump(mode="json"), "allowed_paths": ["../x/"]}
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(raw, ["../x/"], root, ext)
    assert caught.value.code == "ACTION_ENVELOPE_INVALID"


# --------------------------------------------------------------------------
# #2786 review: a dir scope only with an external target, never over a protected path
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "request_extra",
    [
        {},  # nexus_task_run / candidate_ops / assist: plain request
        {"worker_candidate_ingress": True},  # no Controller: the Nexus-new checkout
        {"worker_candidate_ingress": True, "controller_repo_root": "NEXUS_ROOT"},
        {"worker_candidate_ingress": False, "controller_repo_root": "EXT"},
    ],
    ids=["plain", "ingress_no_controller", "ingress_nexus_controller", "not_ingress_external"],
)
def test_switch_on_pre_action_guard_requires_external_target_for_dir_scope(
    tmp_path, monkeypatch, ext, request_extra
):
    root = _canon(tmp_path)
    _switch_on(monkeypatch)
    action = _ext_envelope(["src/pkg/"], ext)
    assert _guard(action, ["src/pkg/"], root, ext)["passed"] is True  # positive control
    request: dict[str, Any] = {"allowed_files": ["src/pkg/"]}
    for key, value in request_extra.items():
        request[key] = {"NEXUS_ROOT": str(root), "EXT": str(ext["ext"])}.get(value, value)
    with pytest.raises(LifecycleGuardError) as caught:
        pre_action_guard(
            action,
            request=request,
            canonical_root=root,
            current_head=ext["sha"],
            tool_manifest_hash=MANIFEST,
        )
    assert caught.value.code == "DIR_SCOPE_REQUIRES_EXTERNAL_TARGET"
    # A file scope with the same plain request is unaffected.
    assert _guard(_envelope(["src/pkg/mod.py"]), ["src/pkg/mod.py"], root)["passed"] is True


def test_switch_on_pre_action_guard_revalidates_the_external_controller(tmp_path, monkeypatch, ext):
    root = _canon(tmp_path)
    _switch_on(monkeypatch)
    action = _ext_envelope(["src/pkg/"], ext)
    assert _guard(action, ["src/pkg/"], root, ext)["passed"] is True  # positive control
    # A Controller outside the measurement root is not an accepted external target.
    outside = tmp_path / "elsewhere"
    sha = _repo(outside)
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_envelope(["src/pkg/"], head=sha), ["src/pkg/"], root, {"ext": outside, "sha": sha})
    assert caught.value.code == "EXTERNAL_TARGET_OUTSIDE_ROOT"


@pytest.mark.parametrize(
    "scope",
    [
        "docs/",  # ancestor of docs/governance
        "docs/governance/",
        "docs/governance/sub/",
        "DOCS/",
        ".github/",
        ".github/workflows/",
        ".nexus-core/",
    ],
)
def test_switch_on_pre_action_guard_refuses_protected_dir_scopes(tmp_path, monkeypatch, ext, scope):
    root = _canon(tmp_path)
    _switch_on(monkeypatch)
    assert _guard(_ext_envelope(["docsx/"], ext), ["docsx/"], root, ext)["passed"] is True
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_ext_envelope([scope], ext), [scope], root, ext)
    assert caught.value.code == "ALLOWED_PATH_PROTECTED"


def test_protected_dir_scope_reuses_the_task_card_rule():
    """Same rule as Task Cards: tasks/ is not protected there, so it is not here either."""
    from nexus.orchestrator.task_card_scope import protected_path_reason

    for scope in ("docs/", ".github/", "docs/governance/", ".nexus-core/"):
        assert protected_path_reason(scope) == "AUTHORITY_DIRECTORY"
    assert protected_path_reason("tasks/") is None


@pytest.mark.parametrize("scope", ["./", "."])
def test_switch_on_root_equivalent_scopes_are_refused(monkeypatch, scope):
    _switch_on(monkeypatch)
    assert _envelope(["src/pkg/"]).allowed_paths == ("src/pkg/",)  # positive control
    with pytest.raises(ValidationError, match="must not be the repository root"):
        _envelope([scope])


@pytest.mark.parametrize(
    "scope",
    [
        "alias/",  # tracked alias -> . : the external repository root
        "govalias/",  # tracked alias -> docs/governance
        "a/link/",  # nested a/link -> ..
        "alias/src/",  # a symlink in an intermediate component
        "nope/",  # missing directory
        "README.md/",  # a file, not a directory
    ],
)
def test_switch_on_dir_scope_is_resolved_in_the_external_repository(
    tmp_path, monkeypatch, ext, scope
):
    """#2786 r2: symlinks of the external repository never widen a dir scope."""
    root = _canon(tmp_path)
    _switch_on(monkeypatch)
    assert _guard(_ext_envelope(["src/pkg/"], ext), ["src/pkg/"], root, ext)["passed"] is True
    assert not (root / scope.split("/")[0]).exists()  # the Nexus side has no such path
    with pytest.raises(LifecycleGuardError) as caught:
        _guard(_ext_envelope([scope], ext), [scope], root, ext)
    assert caught.value.code == "ALLOWED_PATH_INVALID"


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
    # Positive control: with both measurement switches on, the scope reaches submit.
    _switch_on(monkeypatch)
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    result = _call(
        gateway_env,
        _arguments(
            gateway_env, "dir-off-2", external_target=_ext_arg(gateway_env), allowed_files=["pkg/"]
        ),
    )
    assert result["isError"] is False, result.get("structuredContent")


def test_switch_on_gateway_dir_scope_without_external_target_is_refused(gateway_env, monkeypatch):
    """#2786: never a dir scope on the Nexus-new checkout itself, even in measurement mode."""
    _switch_on(monkeypatch)
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    result = _call(gateway_env, _arguments(gateway_env, "dir-on-1", allowed_files=["pkg/"]))
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "DIR_SCOPE_REQUIRES_EXTERNAL_TARGET"
    assert gateway_env["service"].submitted == []
    # A file scope on the same Gateway still reaches submit.
    result = _call(gateway_env, _arguments(gateway_env, "dir-on-2", allowed_files=["pkg/mod.py"]))
    assert result["isError"] is False, result.get("structuredContent")


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


# --------------------------------------------------------------------------
# #2786: the ephemeral service skips pre_action_guard; dir scopes are still checked
# --------------------------------------------------------------------------


class _DirGuardPassed(Exception):
    pass


def _ephemeral_submit(ctx: dict[str, Any], monkeypatch, request: dict[str, Any]) -> None:
    import nexus.orchestrator.self_hosted_task_service as service_module
    from nexus.orchestrator.lifecycle_guards import guard_dir_scopes as original
    from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService

    def guard_then_stop(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        raise _DirGuardPassed()

    monkeypatch.setattr(service_module, "guard_dir_scopes", guard_then_stop)
    monkeypatch.setattr(
        service_module,
        "pre_action_guard",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("ephemeral ran the full guard")),
    )
    service = SelfHostedTaskService(
        state_dir=ctx["card_root"].parent / "eph-state", auto_reconcile=False
    )
    assert service.ephemeral is True
    service.submit_task(request)


def test_ephemeral_service_still_checks_dir_scopes(gateway_env, monkeypatch):
    _switch_on(monkeypatch)
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    arguments = _arguments(
        gateway_env, "dir-eph-1", external_target=_ext_arg(gateway_env), allowed_files=["pkg/"]
    )
    assert _call(gateway_env, arguments)["isError"] is False
    request = gateway_env["service"].submitted[0]
    # Positive control: the external-target request passes the dir-scope check.
    with pytest.raises(_DirGuardPassed):
        _ephemeral_submit(gateway_env, monkeypatch, dict(request))
    # The service re-derives the request from the signed bound request, so the
    # Controller cannot be swapped; but a process whose external target is not
    # (or no longer) accepted refuses the dir scope on the ephemeral path too.
    monkeypatch.setattr(met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", "")
    with pytest.raises(LifecycleGuardError) as caught:
        _ephemeral_submit(gateway_env, monkeypatch, dict(request))
    assert caught.value.code == "DIR_SCOPE_REQUIRES_EXTERNAL_TARGET"


def test_guard_dir_scopes_applies_the_root_and_protected_checks(tmp_path, monkeypatch, ext):
    from nexus.orchestrator.lifecycle_guards import guard_dir_scopes

    root = _canon(tmp_path)
    request = {"worker_candidate_ingress": True, "controller_repo_root": str(ext["ext"])}
    _switch_on(monkeypatch)
    prebuilt = _ext_envelope(["src/pkg/"], ext)
    monkeypatch.setattr(mds, "MEASURE_DIR_SCOPE_AT_START", False)
    guard_dir_scopes(prebuilt, request={}, canonical_root=root)  # switch off: a no-op
    _switch_on(monkeypatch)
    guard_dir_scopes(prebuilt, request=request, canonical_root=root)
    for scope, code in (
        ("docs/", "ALLOWED_PATH_PROTECTED"),
        ("alias/", "ALLOWED_PATH_INVALID"),
        ("nope/", "ALLOWED_PATH_INVALID"),
    ):
        with pytest.raises(LifecycleGuardError) as caught:
            guard_dir_scopes(_ext_envelope([scope], ext), request=request, canonical_root=root)
        assert caught.value.code == code
    with pytest.raises(LifecycleGuardError) as caught:
        guard_dir_scopes(_ext_envelope(["src/pkg/"], ext), request={}, canonical_root=root)
    assert caught.value.code == "DIR_SCOPE_REQUIRES_EXTERNAL_TARGET"
