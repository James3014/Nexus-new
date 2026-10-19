"""Measurement-only ``external_target`` on the Gateway worker path (Issue #2721).

Every repository here is a temporary git repository created by the test; no
network and no real external repository is used.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from nexus.engine import canonical_task_seam
from nexus.engine.canonical_task_seam import (
    VerifiedTaskCardIdentity,
    build_canonical_planner_admission,
)
from nexus.orchestrator import measure_external_target as met
from nexus.orchestrator.measure_external_target import (
    MEASURE_EXTERNAL_TARGET_ROOT_ENV,
    ExternalTargetError,
    accepted_external_controller,
    live_forbidden_roots,
    validate_external_target,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import UnifiedMCPGateway

_GIT = [
    "git",
    "-c",
    "user.name=t",
    "-c",
    "user.email=t@example.invalid",
    "-c",
    "commit.gpgsign=false",
]


def _run(*args: str, cwd: Path) -> str:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    return subprocess.run(
        [*_GIT, *args], cwd=cwd, check=True, capture_output=True, text=True, env=environment
    ).stdout.strip()


def _repo(path: Path, files: dict[str, str] | None = None) -> str:
    path.mkdir(parents=True, exist_ok=True)
    _run("init", "-q", "-b", "main", cwd=path)
    for name, text in (files or {"pkg/mod.py": "VALUE = 1\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _run("add", "-A", cwd=path)
    _run("commit", "-q", "-m", "init", cwd=path)
    return _run("rev-parse", "HEAD", cwd=path)


@pytest.fixture
def layout(tmp_path: Path) -> dict[str, Any]:
    nexus_root = tmp_path / "nexus-controller"
    _repo(nexus_root, {"tasks/README.md": "cards\n"})
    measure_root = tmp_path / "measure"
    measure_root.mkdir()
    ext = measure_root / "extrepo"
    sha = _repo(ext)
    return {
        "nexus_root": nexus_root,
        "measure_root": measure_root,
        "ext": ext,
        "sha": sha,
        "env": {MEASURE_EXTERNAL_TARGET_ROOT_ENV: str(measure_root)},
    }


def _code(raw: Any, layout: dict[str, Any], **kwargs: Any) -> str:
    with pytest.raises(ExternalTargetError) as caught:
        validate_external_target(raw, nexus_root=layout["nexus_root"], env=layout["env"], **kwargs)
    return str(caught.value)


# --------------------------------------------------------------------------
# Validation rules (module level)
# --------------------------------------------------------------------------


def test_external_target_accepts_clean_repo_at_exact_head(layout):
    target = validate_external_target(
        {"repo_root": str(layout["ext"]), "base_revision": layout["sha"]},
        nexus_root=layout["nexus_root"],
        env=layout["env"],
    )
    assert target.repo_root == layout["ext"].resolve()
    assert target.base_revision == layout["sha"]


def test_external_target_disabled_without_measurement_env(layout):
    with pytest.raises(ExternalTargetError, match="EXTERNAL_TARGET_DISABLED"):
        validate_external_target(
            {"repo_root": str(layout["ext"]), "base_revision": layout["sha"]},
            nexus_root=layout["nexus_root"],
            env={},
        )


def test_external_target_rejects_shape_and_revision_errors(layout):
    ext, sha = str(layout["ext"]), layout["sha"]
    assert _code("x", layout) == "EXTERNAL_TARGET_INVALID"
    assert _code({"repo_root": ext}, layout) == "EXTERNAL_TARGET_INVALID"
    assert (
        _code({"repo_root": ext, "base_revision": sha, "extra": 1}, layout)
        == "EXTERNAL_TARGET_INVALID"
    )
    for bad in (sha.upper(), sha[:12], "g" * 40, "--all", f"{sha}\n", 7):
        assert (
            _code({"repo_root": ext, "base_revision": bad}, layout)
            == "EXTERNAL_TARGET_BASE_REVISION_INVALID"
        )
    assert (
        _code({"repo_root": "extrepo", "base_revision": sha}, layout)
        == "EXTERNAL_TARGET_REPO_ROOT_NOT_ABSOLUTE"
    )
    assert (
        _code({"repo_root": str(layout["measure_root"] / "missing"), "base_revision": sha}, layout)
        == "EXTERNAL_TARGET_REPO_ROOT_MISSING"
    )


def test_external_target_rejects_path_outside_measurement_root(layout, tmp_path):
    outside = tmp_path / "outside-repo"
    sha = _repo(outside)
    assert (
        _code({"repo_root": str(outside), "base_revision": sha}, layout)
        == "EXTERNAL_TARGET_OUTSIDE_ROOT"
    )
    # The measurement root itself is not a target.
    assert (
        _code({"repo_root": str(layout["measure_root"]), "base_revision": sha}, layout)
        == "EXTERNAL_TARGET_OUTSIDE_ROOT"
    )
    # ``..`` spelled under the root but resolving outside it.
    dotted = layout["measure_root"] / ".." / "outside-repo"
    assert (
        _code({"repo_root": str(dotted), "base_revision": sha}, layout)
        == "EXTERNAL_TARGET_OUTSIDE_ROOT"
    )


def test_external_target_rejects_symlink_escape(layout, tmp_path):
    outside = tmp_path / "outside-repo"
    sha = _repo(outside)
    link = layout["measure_root"] / "looks-inside"
    link.symlink_to(outside, target_is_directory=True)
    assert (
        _code({"repo_root": str(link), "base_revision": sha}, layout)
        == "EXTERNAL_TARGET_OUTSIDE_ROOT"
    )


def test_external_target_symlink_inside_root_resolves_to_real_repo(layout):
    link = layout["measure_root"] / "alias"
    link.symlink_to(layout["ext"], target_is_directory=True)
    target = validate_external_target(
        {"repo_root": str(link), "base_revision": layout["sha"]},
        nexus_root=layout["nexus_root"],
        env=layout["env"],
    )
    assert target.repo_root == layout["ext"].resolve()


def test_external_target_rejects_head_mismatch(layout):
    _run("commit", "-q", "--allow-empty", "-m", "second", cwd=layout["ext"])
    assert (
        _code({"repo_root": str(layout["ext"]), "base_revision": layout["sha"]}, layout)
        == "EXTERNAL_TARGET_HEAD_MISMATCH"
    )


def test_external_target_rejects_non_git_directory(layout):
    plain = layout["measure_root"] / "plain"
    plain.mkdir()
    assert (
        _code({"repo_root": str(plain), "base_revision": layout["sha"]}, layout)
        == "EXTERNAL_TARGET_NOT_GIT_WORKTREE"
    )


def test_external_target_rejects_subdirectory_of_a_repository(layout):
    """Nested path: a directory inside a repository is not that repository's top level."""
    nested = layout["ext"] / "pkg"
    assert (
        _code({"repo_root": str(nested), "base_revision": layout["sha"]}, layout)
        == "EXTERNAL_TARGET_NOT_REPOSITORY_TOPLEVEL"
    )


def test_external_target_rejects_dirty_work_tree(layout):
    (layout["ext"] / "untracked.txt").write_text("x\n", encoding="utf-8")
    assert (
        _code({"repo_root": str(layout["ext"]), "base_revision": layout["sha"]}, layout)
        == "EXTERNAL_TARGET_DIRTY"
    )


def test_external_target_rejects_a_worktree_of_the_nexus_repository(layout):
    worktree = layout["measure_root"] / "nexus-alias"
    _run("worktree", "add", "-q", "--detach", str(worktree), "HEAD", cwd=layout["nexus_root"])
    head = _run("rev-parse", "HEAD", cwd=worktree)
    assert (
        _code({"repo_root": str(worktree), "base_revision": head}, layout)
        == "EXTERNAL_TARGET_IS_NEXUS_CONTROLLER"
    )


@pytest.mark.parametrize(
    "where", ["parent_of_nexus", "inside_nexus", "is_loaded_root", "parent_of_loaded"]
)
def test_external_target_rejects_measurement_root_overlapping_live_paths(layout, tmp_path, where):
    ext, sha = layout["ext"], layout["sha"]
    forbidden: tuple[Path, ...] = ()
    if where == "parent_of_nexus":
        env = {MEASURE_EXTERNAL_TARGET_ROOT_ENV: str(tmp_path)}
    elif where == "inside_nexus":
        inner = layout["nexus_root"] / "measure"
        inner.mkdir()
        env = {MEASURE_EXTERNAL_TARGET_ROOT_ENV: str(inner)}
    elif where == "is_loaded_root":
        env = layout["env"]
        forbidden = (layout["measure_root"],)
    else:
        env = layout["env"]
        forbidden = (ext / "pkg",)
    with pytest.raises(ExternalTargetError, match="EXTERNAL_TARGET_ROOT_FORBIDDEN"):
        validate_external_target(
            {"repo_root": str(ext), "base_revision": sha},
            nexus_root=layout["nexus_root"],
            env=env,
            forbidden_roots=forbidden,
        )


def test_live_forbidden_roots_cover_live_locations(layout, tmp_path):
    worktree = tmp_path / "controller-worktree"
    _run("worktree", "add", "-q", "--detach", str(worktree), "HEAD", cwd=layout["nexus_root"])
    configured = tmp_path / "configured-canonical"
    roots = live_forbidden_roots(
        worktree,
        extra=(tmp_path / "loaded",),
        env={"NEXUS_CANONICAL_SOURCE_ROOT": str(configured)},
    )
    assert worktree.resolve() in roots
    # The repository's main checkout (the ``~/workspace/Nexus-new`` clone) is derived from git.
    assert layout["nexus_root"].resolve() in roots
    assert (tmp_path / "loaded").resolve() in roots
    assert configured.resolve() in roots
    assert (Path.home() / "Library" / "Application Support" / "Nexus").resolve() in roots


def test_external_target_rejects_application_support_nexus(layout, tmp_path, monkeypatch):
    home = tmp_path / "home"
    support = home / "Library" / "Application Support" / "Nexus"
    sha = _repo(support / "gateway-direct" / "controller")
    monkeypatch.setattr(met.Path, "home", classmethod(lambda cls: home))
    env = {MEASURE_EXTERNAL_TARGET_ROOT_ENV: str(support)}
    with pytest.raises(ExternalTargetError, match="EXTERNAL_TARGET_ROOT_FORBIDDEN"):
        validate_external_target(
            {"repo_root": str(support / "gateway-direct" / "controller"), "base_revision": sha},
            nexus_root=layout["nexus_root"],
            env=env,
        )


def test_service_recheck_is_off_without_env_and_for_the_nexus_root(layout):
    assert (
        accepted_external_controller(
            str(layout["ext"]), layout["sha"], nexus_root=layout["nexus_root"], env={}
        )
        is None
    )
    assert (
        accepted_external_controller(
            str(layout["nexus_root"]), "a" * 40, nexus_root=layout["nexus_root"], env=layout["env"]
        )
        is None
    )
    accepted = accepted_external_controller(
        str(layout["ext"]), layout["sha"], nexus_root=layout["nexus_root"], env=layout["env"]
    )
    assert accepted is not None and accepted.base_revision == layout["sha"]
    with pytest.raises(ExternalTargetError, match="EXTERNAL_TARGET_HEAD_MISMATCH"):
        accepted_external_controller(
            str(layout["ext"]), "b" * 40, nexus_root=layout["nexus_root"], env=layout["env"]
        )


# --------------------------------------------------------------------------
# Planner seam
# --------------------------------------------------------------------------


def test_planner_admission_route_facts_use_external_root_only_when_given(monkeypatch, tmp_path):
    seen: list[Path] = []
    original = canonical_task_seam._canonical_route_facts

    def capture(**kwargs: Any) -> dict[str, Any]:
        seen.append(kwargs["repo_root"])
        return original(**kwargs)

    monkeypatch.setattr(canonical_task_seam, "_canonical_route_facts", capture)
    card = tmp_path / "tasks" / "seam-ext.md"
    card.parent.mkdir(parents=True)
    card.write_text("task_id: `seam-ext`\nAUTO_CHAIN: false\n", encoding="utf-8")
    identity = VerifiedTaskCardIdentity(
        task_id="seam-ext",
        task_card_path="tasks/seam-ext.md",
        canonical_task_card_path=str(card),
        task_card_hash=hashlib.sha256(card.read_bytes()).hexdigest(),
    )
    ext = tmp_path / "ext"
    _repo(ext)
    for root in (None, ext):
        build_canonical_planner_admission(
            task_id="seam-ext",
            task_text="fix the value",
            allowed_files=("pkg/mod.py",),
            verifier_command=("git diff --check",),
            task_card_identity=identity,
            route_facts_repo_root=root,
        )
    assert seen == [canonical_task_seam.REPO_ROOT, ext]


# --------------------------------------------------------------------------
# Gateway worker_candidate
# --------------------------------------------------------------------------


class _CaptureService(SelfHostedTaskService):
    def __init__(self) -> None:
        self.submitted: list[Any] = []

    def submit_task(self, request):  # type: ignore[override]
        self.submitted.append(request)
        return {"status": "PENDING_HUMAN_APPROVAL", "task_id": request["task_id"]}

    def build_contract(self, request):  # type: ignore[override]
        return super().build_contract(request)


def _ready_preflight(**_: Any) -> dict[str, Any]:
    return {
        "status": "VERSION_VERIFIED",
        "readiness_status": "MODEL_VERIFIED",
        "execution_ready": True,
        "provider": "agy",
        "requested_model": "gemini-3.8-flash-medium",
        "resolved_model": "gemini-3.8-flash-medium",
        "model_reachable": True,
        "requested_model_verified": True,
        "authenticated": True,
        "authentication_evidence": "successful_exact_model_probe",
        "probe_evidence_hash": "e" * 64,
        "binary_path": "/usr/bin/true",
        "binary_sha256": "b" * 64,
        "cli_version_sha256": "c" * 64,
        "probe_expires_at": "2099-01-01T00:00:00+00:00",
    }


@pytest.fixture
def gateway_env(layout, tmp_path, monkeypatch):
    """Gateway bound to a temporary card root; ``_git`` (Nexus side) stubbed like the gateway suite."""
    import nexus.orchestrator.self_hosted_task_service as service_module
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    card_root = tmp_path / "canonical-test-repo"
    card_root.mkdir()
    _run("init", "-q", cwd=card_root)  # the Nexus identity (common dir) must be readable
    monkeypatch.setattr(service_module, "CANONICAL_SOURCE_ROOT", card_root)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", card_root)
    monkeypatch.setattr(gateway_module, "_git", lambda *args, **kwargs: "a" * 40)
    original_guard = gateway_module.pre_action_guard
    guard_calls: list[dict[str, Any]] = []

    def test_repo_guard(action, **kwargs):
        guard_calls.append({"action": action, **kwargs})
        return original_guard(action, canonical_root=card_root, **kwargs)

    monkeypatch.setattr(gateway_module, "pre_action_guard", test_repo_guard)
    monkeypatch.setattr(met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", "")
    service = _CaptureService()
    gateway = UnifiedMCPGateway(service=service)
    monkeypatch.setattr(gateway, "_provider_preflight", lambda arguments: _ready_preflight())
    return {
        **layout,
        "card_root": card_root,
        "service": service,
        "gateway": gateway,
        "guard_calls": guard_calls,
    }


def _arguments(ctx: dict[str, Any], task_id: str, **extra: Any) -> dict[str, Any]:
    relative = f"tasks/test/{task_id}.md"
    card = ctx["card_root"] / relative
    card.parent.mkdir(parents=True, exist_ok=True)
    card.write_text(f"task_id: `{task_id}`\nAUTO_CHAIN: false\n", encoding="utf-8")
    return {
        "task_id": task_id,
        "what": "fix the value",
        "why": "measurement task",
        "allowed_files": ["pkg/mod.py"],
        "verifier_commands": ["git diff --check"],
        "owner_confirmation": True,
        "task_card_path": relative,
        "task_card_hash": hashlib.sha256(card.read_bytes()).hexdigest(),
        **extra,
    }


def _call(ctx: dict[str, Any], arguments: dict[str, Any]) -> dict[str, Any]:
    response = ctx["gateway"].handle({
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "nexus_worker_candidate", "arguments": arguments},
    })
    assert response is not None
    return response["result"]


def _ext_arg(ctx: dict[str, Any]) -> dict[str, str]:
    return {"repo_root": str(ctx["ext"]), "base_revision": ctx["sha"]}


def test_env_unset_external_target_is_an_unknown_field_and_never_read(gateway_env, monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway_parts.worker_candidate as wc

    def must_not_run(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("external_target was read on a live Gateway")

    monkeypatch.setattr(wc, "validate_external_target", must_not_run)
    monkeypatch.setattr(wc, "external_target_head", must_not_run)
    result = _call(
        gateway_env, _arguments(gateway_env, "ext-off-1", external_target=_ext_arg(gateway_env))
    )
    other = _call(gateway_env, _arguments(gateway_env, "ext-off-2", zz_unknown_field={"x": 1}))
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == "WORKER_CANDIDATE_UNKNOWN_FIELDS:external_target"
    assert other["structuredContent"]["error"] == "WORKER_CANDIDATE_UNKNOWN_FIELDS:zz_unknown_field"
    # Same rejection shape as any unknown key, nothing submitted.
    assert set(result["structuredContent"]) == set(other["structuredContent"])
    assert gateway_env["service"].submitted == []


def test_env_unset_tool_schema_and_request_are_unchanged(gateway_env, monkeypatch):
    spec = next(s for s in UnifiedMCPGateway.tool_specs() if s["name"] == "nexus_worker_candidate")
    assert "external_target" not in spec["inputSchema"]["properties"]
    unset_specs = json.dumps(UnifiedMCPGateway.tool_specs(), sort_keys=True)
    result = _call(gateway_env, _arguments(gateway_env, "ext-off-3"))
    assert result["isError"] is False, result.get("structuredContent")
    request = gateway_env["service"].submitted[0]
    root = str(gateway_env["card_root"])
    for source in (request, request["bound_action_request"]):
        assert source["controller_repo_root"] == root
        assert source["controller_revision"] == source["target_base_revision"] == "a" * 40
    assert request["action"]["expected_head"] == "a" * 40
    assert gateway_env["guard_calls"][-1]["current_head"] == "a" * 40
    # Measurement mode only adds the one optional property; nothing else moves.
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    set_specs = UnifiedMCPGateway.tool_specs()
    set_spec = next(s for s in set_specs if s["name"] == "nexus_worker_candidate")
    assert (
        set_spec["inputSchema"]["properties"].pop("external_target")["additionalProperties"]
        is False
    )
    assert json.dumps(set_specs, sort_keys=True) == unset_specs


def test_env_set_external_target_binds_external_controller(gateway_env, monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway as gateway_module

    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    admission_kwargs: list[dict[str, Any]] = []
    real_admission = gateway_module.build_canonical_planner_admission

    def capture_admission(**kwargs: Any) -> Any:
        admission_kwargs.append(kwargs)
        return real_admission(**kwargs)

    monkeypatch.setattr(gateway_module, "build_canonical_planner_admission", capture_admission)
    arguments = _arguments(
        gateway_env,
        "ext-on-1",
        external_target=_ext_arg(gateway_env),
        codeintel_lookup={"target_symbol": "VALUE", "search_paths": ["pkg/mod.py"]},
    )
    result = _call(gateway_env, arguments)
    assert result["isError"] is False, result.get("structuredContent")
    request = gateway_env["service"].submitted[0]
    ext_root, sha = str(gateway_env["ext"].resolve()), gateway_env["sha"]
    for source in (request, request["bound_action_request"]):
        assert source["controller_repo_root"] == ext_root
        assert source["controller_revision"] == source["target_base_revision"] == sha
        # Contract binding unchanged: the Task Card is the Nexus-new tasks/ card.
        assert source["task_card_path"] == arguments["task_card_path"]
        assert source["task_card_hash"] == arguments["task_card_hash"]
        assert source["contract_kind"] == "TRACKED_TASK_CARD"
        assert "external_target" not in source
    assert request["target_worktree_root"] == str(
        gateway_env["card_root"].parent / "nexus-runtime-targets"
    )
    assert request["action"]["expected_head"] == sha
    assert request["action"]["task_card_path"] == arguments["task_card_path"]
    assert gateway_env["guard_calls"][-1]["current_head"] == sha
    assert admission_kwargs[-1]["route_facts_repo_root"] == gateway_env["ext"].resolve()
    # The service-side binding check accepts the envelope (controller_revision == expected_head).
    from nexus.orchestrator.self_hosted_task_service import _validated_action_request

    effective, envelope = _validated_action_request(request)
    assert envelope is not None
    assert effective["controller_revision"] == sha
    assert effective["controller_repo_root"] == ext_root


def test_env_set_allowed_files_are_checked_against_the_external_root(
    gateway_env, monkeypatch, tmp_path
):
    ext = gateway_env["measure_root"] / "linkrepo"
    ext.mkdir()
    (ext / "escape").symlink_to(tmp_path, target_is_directory=True)
    sha = _repo(ext, {"pkg/mod.py": "VALUE = 1\n"})
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    target = {"repo_root": str(ext), "base_revision": sha}
    result = _call(
        gateway_env,
        _arguments(gateway_env, "ext-on-2", external_target=target, allowed_files=["escape/x.py"]),
    )
    assert result["isError"] is True
    assert "allowed_files escapes external target root" in result["structuredContent"]["error"]
    result = _call(
        gateway_env,
        _arguments(
            gateway_env,
            "ext-on-3",
            external_target=target,
            codeintel_lookup={"target_symbol": "x", "search_paths": ["escape/x.py"]},
        ),
    )
    assert "CODEINTEL_LOOKUP_INVALID" in result["structuredContent"]["error"]
    assert gateway_env["service"].submitted == []


@pytest.mark.parametrize(
    ("mutate", "code"),
    [
        (lambda ctx, t: {**t, "base_revision": "f" * 40}, "EXTERNAL_TARGET_HEAD_MISMATCH"),
        (
            lambda ctx, t: {**t, "base_revision": t["base_revision"].upper()},
            "EXTERNAL_TARGET_BASE_REVISION_INVALID",
        ),
        (lambda ctx, t: {**t, "repo_root": str(ctx["nexus_root"])}, "EXTERNAL_TARGET_OUTSIDE_ROOT"),
        (
            lambda ctx, t: {**t, "repo_root": str(ctx["ext"] / "pkg")},
            "EXTERNAL_TARGET_NOT_REPOSITORY_TOPLEVEL",
        ),
        (lambda ctx, t: {**t, "unexpected": True}, "EXTERNAL_TARGET_INVALID"),
    ],
)
def test_env_set_invalid_external_target_fails_closed_before_submit(
    gateway_env, monkeypatch, mutate, code
):
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    target = mutate(gateway_env, _ext_arg(gateway_env))
    result = _call(gateway_env, _arguments(gateway_env, "ext-bad", external_target=target))
    assert result["isError"] is True
    assert result["structuredContent"]["error"] == code
    assert gateway_env["service"].submitted == []


def test_env_set_external_target_still_requires_the_tracked_task_card(gateway_env, monkeypatch):
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    arguments = _arguments(gateway_env, "ext-card", external_target=_ext_arg(gateway_env))
    for field in ("task_card_path", "task_card_hash"):
        missing = {k: v for k, v in arguments.items() if k != field}
        result = _call(gateway_env, missing)
        assert result["isError"] is True
        assert "TASK_CARD_PATH_HASH_PAIR_REQUIRED" in result["structuredContent"]["error"]
    tampered = {**arguments, "task_card_hash": "0" * 64}
    result = _call(gateway_env, tampered)
    assert result["isError"] is True
    assert "TASK_CARD_BINDING_MISMATCH" in result["structuredContent"]["error"]
    # The card must live under the Nexus-new tasks/ tree, not the external repository.
    outside = {**arguments, "task_card_path": "pkg/mod.py"}
    result = _call(gateway_env, outside)
    assert "TASK_CARD_PATH_INVALID" in result["structuredContent"]["error"]
    assert gateway_env["service"].submitted == []


def test_env_set_external_target_refuses_rie_identity(gateway_env, monkeypatch):
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    arguments = _arguments(
        gateway_env,
        "ext-rie",
        external_target=_ext_arg(gateway_env),
        rie_knowledge_identity={"repository": "a/b", "pr_number": 1, "base_sha": "a" * 40},
    )
    result = _call(gateway_env, arguments)
    assert result["structuredContent"]["error"] == "EXTERNAL_TARGET_RIE_KNOWLEDGE_UNSUPPORTED"


def test_env_set_external_head_drift_before_submit_is_refused(gateway_env, monkeypatch):
    import nexus.orchestrator.unified_mcp_gateway_parts.worker_candidate as wc

    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    monkeypatch.setattr(wc, "external_target_head", lambda repo_root: "d" * 40)
    result = _call(
        gateway_env, _arguments(gateway_env, "ext-drift", external_target=_ext_arg(gateway_env))
    )
    assert result["structuredContent"]["error"] == "EXTERNAL_TARGET_HEAD_DRIFT"
    assert gateway_env["service"].submitted == []


# --------------------------------------------------------------------------
# Service submit_task: lifecycle guard binds the external HEAD only in measurement mode
# --------------------------------------------------------------------------


class _GuardReached(Exception):
    pass


def _submit_until_guard(
    ctx: dict[str, Any], monkeypatch, request: dict[str, Any]
) -> dict[str, Any]:
    import nexus.orchestrator.self_hosted_task_service as service_module

    seen: dict[str, Any] = {}

    def guard(action, **kwargs):
        seen.update(kwargs)
        raise _GuardReached()

    monkeypatch.setattr(service_module, "pre_action_guard", guard)
    monkeypatch.setattr(service_module, "trusted_runtime_manifest_hash", lambda: "f" * 64)
    service = SelfHostedTaskService(
        state_dir=ctx["card_root"].parent / "svc-state", auto_reconcile=False
    )
    # A temporary state dir makes the service ephemeral, which skips the guard;
    # force the production branch since only the guard call is exercised.
    service.ephemeral = False
    with pytest.raises(_GuardReached):
        service.submit_task(request)
    return seen


def test_service_guard_uses_external_head_only_in_measurement_mode(gateway_env, monkeypatch):
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    assert (
        _call(
            gateway_env, _arguments(gateway_env, "ext-svc", external_target=_ext_arg(gateway_env))
        )["isError"]
        is False
    )
    request = gateway_env["service"].submitted[0]
    seen = _submit_until_guard(gateway_env, monkeypatch, request)
    assert seen["current_head"] == gateway_env["sha"]
    assert seen["canonical_root"] == gateway_env["card_root"]
    # Same request on a Gateway without the variable: no external HEAD is supplied,
    # so the guard reads the canonical HEAD exactly as before.
    monkeypatch.setattr(met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", "")
    seen = _submit_until_guard(gateway_env, monkeypatch, request)
    assert "current_head" not in seen


def test_service_guard_refuses_external_controller_that_moved(gateway_env, monkeypatch):
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    assert (
        _call(
            gateway_env, _arguments(gateway_env, "ext-svc-2", external_target=_ext_arg(gateway_env))
        )["isError"]
        is False
    )
    request = gateway_env["service"].submitted[0]
    _run("commit", "-q", "--allow-empty", "-m", "moved", cwd=gateway_env["ext"])
    with pytest.raises(ExternalTargetError, match="EXTERNAL_TARGET_HEAD_MISMATCH"):
        _submit_until_guard(gateway_env, monkeypatch, request)


def test_module_has_no_nexus_imports():
    """The gate module stays dependency-free so the live import graph is unchanged."""
    source = Path(met.__file__).read_text(encoding="utf-8")
    assert "import nexus" not in source and "from nexus" not in source
    assert sys.modules[met.__name__] is met


# --------------------------------------------------------------------------
# PR #2742 review round 1
# --------------------------------------------------------------------------


def test_linked_worktree_of_an_outside_repository_is_refused(layout, tmp_path):
    """Fix 1: the git dir / common dir must also live under the measurement root."""
    outside = tmp_path / "outside-main"
    _repo(outside)
    linked = layout["measure_root"] / "linked"
    _run("worktree", "add", "-q", "--detach", str(linked), "HEAD", cwd=outside)
    head = _run("rev-parse", "HEAD", cwd=linked)
    assert (
        _code({"repo_root": str(linked), "base_revision": head}, layout)
        == "EXTERNAL_TARGET_GIT_METADATA_OUTSIDE_ROOT"
    )


def test_linked_worktree_whose_repository_is_inside_the_root_is_accepted(layout):
    linked = layout["measure_root"] / "linked-inside"
    _run("worktree", "add", "-q", "--detach", str(linked), "HEAD", cwd=layout["ext"])
    target = validate_external_target(
        {"repo_root": str(linked), "base_revision": layout["sha"]},
        nexus_root=layout["nexus_root"],
        env=layout["env"],
    )
    assert target.repo_root == linked.resolve()


def test_env_set_after_start_changes_nothing(gateway_env, monkeypatch):
    """Fix 2: only the import-time snapshot counts; a later variable enables nothing."""
    monkeypatch.setenv(MEASURE_EXTERNAL_TARGET_ROOT_ENV, str(gateway_env["measure_root"]))
    assert met.MEASURE_EXTERNAL_TARGET_ROOT_AT_START == ""
    assert met.external_target_enabled() is False
    spec = next(s for s in UnifiedMCPGateway.tool_specs() if s["name"] == "nexus_worker_candidate")
    assert "external_target" not in spec["inputSchema"]["properties"]
    result = _call(
        gateway_env, _arguments(gateway_env, "ext-late", external_target=_ext_arg(gateway_env))
    )
    assert result["structuredContent"]["error"] == "WORKER_CANDIDATE_UNKNOWN_FIELDS:external_target"
    assert (
        accepted_external_controller(
            str(gateway_env["ext"]), "f" * 40, nexus_root=gateway_env["nexus_root"]
        )
        is None
    )
    assert gateway_env["service"].submitted == []


def test_git_probe_environment_is_isolated(monkeypatch):
    """Fix 3: every inherited GIT_* variable is dropped; no system/global config, no prompt."""
    for key, value in {
        "GIT_DIR": "/elsewhere/.git",
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "core.fsmonitor",
        "GIT_CONFIG_VALUE_0": "/bin/sh",
        "GIT_EXEC_PATH": "/elsewhere",
    }.items():
        monkeypatch.setenv(key, value)
    environment = met._git_environment()
    git_keys = {key for key in environment if key.startswith("GIT_")}
    assert git_keys == {"GIT_CONFIG_NOSYSTEM", "GIT_CONFIG_GLOBAL", "GIT_TERMINAL_PROMPT"}
    assert environment["GIT_CONFIG_NOSYSTEM"] == "1"
    assert environment["GIT_CONFIG_GLOBAL"] == os.devnull
    assert environment["GIT_TERMINAL_PROMPT"] == "0"


def _fsmonitor_hook(tmp_path: Path) -> tuple[Path, Path]:
    marker = tmp_path / "FSMONITOR_RAN"
    hook = tmp_path / "fsmonitor-hook.sh"
    hook.write_text(f'#!/bin/sh\ntouch "{marker}"\nexit 1\n', encoding="utf-8")
    hook.chmod(0o755)
    return hook, marker


def test_inherited_git_config_env_cannot_run_a_command(layout, tmp_path, monkeypatch):
    """Fix 3: an fsmonitor injected through GIT_CONFIG_* in the Gateway env never runs."""
    hook, marker = _fsmonitor_hook(tmp_path)
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "core.fsmonitor")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", str(hook))
    validate_external_target(
        {"repo_root": str(layout["ext"]), "base_revision": layout["sha"]},
        nexus_root=layout["nexus_root"],
        env=layout["env"],
    )
    assert not marker.exists()


def test_repository_fsmonitor_config_is_not_executed(layout, tmp_path):
    """1d (a): core.fsmonitor in the external repository's own config never runs."""
    hook, marker = _fsmonitor_hook(tmp_path)
    _run("config", "core.fsmonitor", str(hook), cwd=layout["ext"])
    target = validate_external_target(
        {"repo_root": str(layout["ext"]), "base_revision": layout["sha"]},
        nexus_root=layout["nexus_root"],
        env=layout["env"],
    )
    assert target.base_revision == layout["sha"]
    assert not marker.exists()


def test_unreadable_nexus_identity_refuses_the_target(layout, tmp_path):
    """Fix 3: the Nexus common dir must be readable; the identity check never fails open."""
    not_a_repo = tmp_path / "nexus-not-a-repo"
    not_a_repo.mkdir()
    with pytest.raises(ExternalTargetError, match="EXTERNAL_TARGET_NEXUS_IDENTITY_UNREADABLE"):
        validate_external_target(
            {"repo_root": str(layout["ext"]), "base_revision": layout["sha"]},
            nexus_root=not_a_repo,
            env=layout["env"],
        )


def _case_insensitive(path: Path) -> bool:
    swapped = path.parent / path.name.swapcase()
    return swapped != path and swapped.exists()


def test_forbidden_root_spelled_in_a_different_case_is_still_forbidden(layout):
    """1d (b): on a case-insensitive volume a different spelling is the same directory."""
    if not _case_insensitive(layout["measure_root"]):
        pytest.skip("volume is case-sensitive")
    respelled = layout["measure_root"].parent / layout["measure_root"].name.upper()
    with pytest.raises(ExternalTargetError, match="EXTERNAL_TARGET_ROOT_FORBIDDEN"):
        validate_external_target(
            {"repo_root": str(layout["ext"]), "base_revision": layout["sha"]},
            nexus_root=layout["nexus_root"],
            env=layout["env"],
            forbidden_roots=(respelled,),
        )


@pytest.mark.skipif(sys.platform != "darwin", reason="case folding applies on darwin")
def test_overlap_is_case_insensitive_on_darwin_even_for_missing_paths(tmp_path):
    assert met._overlaps(tmp_path / "A" / "b", tmp_path / "a")
    assert met._overlaps(tmp_path / "a", tmp_path / "A" / "B")
    assert not met._overlaps(tmp_path / "a", tmp_path / "ab")


def test_ephemeral_service_still_rechecks_the_external_controller(gateway_env, monkeypatch):
    """Unverified note: an ephemeral service must not skip the external re-check."""
    monkeypatch.setattr(
        met, "MEASURE_EXTERNAL_TARGET_ROOT_AT_START", str(gateway_env["measure_root"])
    )
    assert (
        _call(
            gateway_env, _arguments(gateway_env, "ext-eph", external_target=_ext_arg(gateway_env))
        )["isError"]
        is False
    )
    request = gateway_env["service"].submitted[0]
    _run("commit", "-q", "--allow-empty", "-m", "moved", cwd=gateway_env["ext"])
    service = SelfHostedTaskService(
        state_dir=gateway_env["card_root"].parent / "eph-state", auto_reconcile=False
    )
    assert service.ephemeral is True
    with pytest.raises(ExternalTargetError, match="EXTERNAL_TARGET_HEAD_MISMATCH"):
        service.submit_task(request)
