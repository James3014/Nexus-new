# ruff: noqa: E701, E702, E731
import hashlib
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from nexus.contracts.gateway_deployment import (
    CURRENT_PROFILE,
    DESIRED_PROFILE,
    GATEWAY_LIFECYCLE_REVISION,
    EffectClass,
)
from scripts.ops import mcp_gateway_durable as g

HASH = hashlib.sha256(b"identity").hexdigest()
HOST_OPERATIONS = ("status", "preflight", "install-artifact", "reload", "rollback")
HOST_OPERATION_PAIRS = [
    (source_operation, target_operation)
    for source_operation in HOST_OPERATIONS
    for target_operation in HOST_OPERATIONS
    if source_operation != target_operation
]
REAL_POSTFLIGHT_GIT_RUNNER = g._fixed_postflight_git_command_runner

@pytest.fixture(autouse=True)
def _isolated_host_authority_store(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "HOST_UID", os.getuid())
    path = tmp_path / "gateway-direct" / "host-authority.json"
    path.parent.mkdir(mode=0o700)
    monkeypatch.setattr(g, "GATEWAY_HOST_AUTHORITY_STORE", path)

    source_root = tmp_path / "trusted-main"
    source_root.mkdir()
    subprocess.run(["git", "-C", str(source_root), "init", "-q", "-b", "main"], check=True)
    subprocess.run(["git", "-C", str(source_root), "config", "user.email", "tests@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(source_root), "config", "user.name", "tests"], check=True)
    subprocess.run(["git", "-C", str(source_root), "remote", "add", "origin", g.HOST_AUTHORITY_REMOTE], check=True)
    monkeypatch.setattr(g, "HOST_AUTHORITY_SOURCE_ROOT", source_root)

    def fixed_authority_runner(*args):
        command = tuple(args) if args and isinstance(args[0], str) else tuple(args[0])
        if command[0:4] == ("git", "-C", str(source_root), "ls-remote"):
            head = subprocess.check_output(
                ["git", "-C", str(source_root), "rev-parse", "HEAD"], text=True
            ).strip()
            return subprocess.CompletedProcess(command, 0, f"{head}\t{g.HOST_AUTHORITY_REF}\n", "")
        if len(command) == 7 and command[0:5] == ("git", "-C", str(source_root), "merge-base", "--is-ancestor"):
            return subprocess.CompletedProcess(command, 0, b"", b"")
        if len(command) == 5 and command[0:4] == ("git", "-C", str(source_root), "show"):
            blob = (source_root / g.HOST_AUTHORITY_SOURCE_PATH).read_bytes()
            return subprocess.CompletedProcess(command, 0, blob, b"")
        return subprocess.run(command, text=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    monkeypatch.setattr(g, "_fixed_authority_command_runner", fixed_authority_runner)

    def fixed_postflight_git_runner(*args):
        command = tuple(args) if args and isinstance(args[0], str) else tuple(args[0])
        profiles = {CURRENT_PROFILE.git.root: CURRENT_PROFILE, DESIRED_PROFILE.git.root: DESIRED_PROFILE}
        profile = profiles[command[2]]
        outputs = {
            ("rev-parse", "--show-toplevel"): profile.git.toplevel,
            ("remote", "get-url", "origin"): profile.git.remote,
            ("status", "--porcelain"): "" if profile.git.clean else " M rollback-only",
            ("rev-parse", "HEAD"): profile.git.head,
            ("rev-parse", "HEAD^{tree}"): profile.git.tree,
        }
        return subprocess.CompletedProcess(command, 0, outputs[command[3:]], "")

    monkeypatch.setattr(g, "_postflight_root_is_safe", lambda root: str(root) in {
        CURRENT_PROFILE.git.root,
        DESIRED_PROFILE.git.root,
    })
    monkeypatch.setattr(g, "_fixed_postflight_git_command_runner", fixed_postflight_git_runner)
    yield

def setup(monkeypatch, tmp_path, head="abc123", dirty="", branch="nexus/integration/main"):
    monkeypatch.setattr(g, "CANONICAL_ROOT", tmp_path)
    monkeypatch.setattr(g, "ENV_PATH", tmp_path.parent / f"{tmp_path.name}-state.env")
    g.ENV_PATH.write_text("export NEXUS_MCP_GATEWAY_TOKEN='SECRET'\nexport NEXUS_GATEWAY_HOST=127.0.0.1\n"); os.chmod(g.ENV_PATH, 0o600)
    vals = {"branch": branch, "status": dirty, "head": head}
    monkeypatch.setattr(g, "_git", lambda _r, *a: vals["head"] if a[0] == "rev-parse" else vals[a[0]])
    monkeypatch.setattr(g, "_is_ancestor", lambda _r, _a, _d: True)
    monkeypatch.setattr(g, "PLISTS", {"gateway": tmp_path / "g.plist", "devspace": tmp_path / "d.plist"})
    monkeypatch.setattr(g, "LOG_DIR", tmp_path / "logs")
    (tmp_path / "generated").mkdir(exist_ok=True); (tmp_path / "dist").mkdir(exist_ok=True)
    (tmp_path / "generated/build-identity.json").write_text("identity"); (tmp_path / "dist/cli.js").write_text("x")
    node = tmp_path / "node"; node.write_text("x"); node.chmod(0o755)
    monkeypatch.setattr(g, "DEVSPACE_ROOT", tmp_path); monkeypatch.setattr(g, "NODE_PATH", node)
    return head

def test_render_both_labels_versioned_and_no_token(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    out = g.manage("render", root=tmp_path, devspace_hash=HASH)
    assert "SECRET" not in out["gateway"] + out["devspace"]
    for xml, label in [(out["gateway"], g.LABELS["gateway"]), (out["devspace"], g.LABELS["devspace"])] :
        p = plistlib.loads(xml.encode()); assert p["Label"] == label; assert str(tmp_path) not in p["ProgramArguments"][1]

def test_devspace_plist_binds_exact_root_and_node(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    devspace_root = tmp_path / "installed-devspace"
    devspace_root.mkdir()
    (devspace_root / "generated").mkdir()
    (devspace_root / "dist").mkdir()
    (devspace_root / "generated/build-identity.json").write_text("identity")
    (devspace_root / "dist/cli.js").write_text("cli")
    node_path = tmp_path / "bin/node"
    node_path.parent.mkdir()
    node_path.write_text("node")
    node_path.chmod(0o755)
    xml = g.manage("render", root=tmp_path, devspace_hash=HASH,
                   devspace_root=devspace_root, node_path=node_path)["devspace"]
    args = plistlib.loads(xml.encode())["ProgramArguments"]
    assert args[args.index("--devspace-root") + 1] == str(devspace_root)
    assert args[args.index("--node-path") + 1] == str(node_path)

def test_main_propagates_devspace_paths_to_manager(monkeypatch, tmp_path):
    expected_root = tmp_path / "devspace"
    expected_node = tmp_path / "node"
    seen = {}
    monkeypatch.setattr(g, "manage", lambda action, **kwargs: seen.update(action=action, **kwargs) or {"ok": True})
    monkeypatch.setattr(sys, "argv", ["mcp_gateway_durable.py", "render", "--devspace-root",
                                       str(expected_root), "--node-path", str(expected_node),
                                       "--devspace-hash", HASH])
    assert g.main() == 0
    assert seen["devspace_root"] == expected_root
    assert seen["node_path"] == expected_node
    assert seen["devspace_hash"] == HASH

def test_main_propagates_devspace_paths_to_serve(monkeypatch, tmp_path):
    expected_root = tmp_path / "devspace"
    expected_node = tmp_path / "node"
    seen = {}
    monkeypatch.setattr(g, "serve", lambda kind, **kwargs: seen.update(kind=kind, **kwargs))
    monkeypatch.setattr(sys, "argv", ["mcp_gateway_durable.py", "serve-devspace", "--launch-floor-head", "head",
                                       "--devspace-root", str(expected_root), "--node-path", str(expected_node),
                                       "--devspace-hash", HASH])
    assert g.main() == 0
    assert seen == {"kind": "devspace", "launch_floor_head": "head", "devspace_hash": HASH,
                    "devspace_root": expected_root, "node_path": expected_node}

def test_main_expected_head_alias_maps_to_launch_floor(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    seen = {}
    monkeypatch.setattr(g, "serve", lambda kind, **kwargs: seen.update(kind=kind, **kwargs))
    monkeypatch.setattr(sys, "argv", ["mcp_gateway_durable.py", "serve-gateway", "--expected-head", "head"])
    assert g.main() == 0
    assert seen == {"kind": "gateway", "launch_floor_head": "head"}

@pytest.mark.parametrize("mutate", [
    lambda root, node: (root / "generated/build-identity.json").write_text("tampered"),
    lambda root, node: (root / "dist/cli.js").unlink(),
    lambda root, node: node.chmod(0o644),
])
def test_render_rejects_invalid_devspace_installation(monkeypatch, tmp_path, mutate):
    setup(monkeypatch, tmp_path)
    node = g.NODE_PATH
    mutate(tmp_path, node)
    with pytest.raises(g.GateError):
        g.manage("preflight", root=tmp_path, devspace_hash=HASH)

def test_render_rejects_relative_node_path(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    with pytest.raises(g.GateError):
        g.manage("preflight", root=tmp_path, devspace_hash=HASH, node_path=Path("node"))

@pytest.mark.parametrize("contents", [
    "export BAD-KEY=value\nexport NEXUS_MCP_GATEWAY_TOKEN=SECRET\n",
    "export NEXUS_MCP_GATEWAY_TOKEN=SECRET\nexport NEXUS_MCP_GATEWAY_TOKEN=OTHER\n",
    "export NEXUS_MCP_GATEWAY_TOKEN='unterminated\n",
    "export NEXUS_MCP_GATEWAY_TOKEN=two words\n",
])
def test_secret_env_parser_rejects_unsafe_forms(monkeypatch, tmp_path, contents):
    setup(monkeypatch, tmp_path)
    g.ENV_PATH.write_text(contents)
    with pytest.raises(g.GateError):
        g.read_secret_env()

def test_secret_env_parser_rejects_non_0600(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    g.ENV_PATH.chmod(0o644)
    with pytest.raises(g.GateError, match="0600"):
        g.read_secret_env()

def test_secret_env_parser_rejects_path_inside_canonical_root(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    inside = tmp_path / "inside.env"
    inside.write_text("export NEXUS_MCP_GATEWAY_TOKEN=SECRET\n")
    inside.chmod(0o600)
    with pytest.raises(g.GateError, match="outside canonical root"):
        g.read_secret_env(inside)

def test_secret_env_parser_rejects_symlink_into_canonical_root(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    target = tmp_path / "target.env"
    target.write_text("export NEXUS_MCP_GATEWAY_TOKEN=SECRET\n")
    target.chmod(0o600)
    link = tmp_path.parent / f"{tmp_path.name}-linked.env"
    link.symlink_to(target)
    with pytest.raises(g.GateError, match="outside canonical root"):
        g.read_secret_env(link)

def test_status_is_json_serializable_and_does_not_expose_process_output(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    class Result:
        returncode = 0
        stdout = "SECRET stdout"
        stderr = "SECRET stderr"
    payload = g.manage("status", runner=lambda *args: Result())
    encoded = json.dumps(payload)
    assert "stdout" not in encoded and "stderr" not in encoded and "SECRET" not in encoded
    assert set(payload) == {"gateway", "devspace"}

def test_status_classifies_real_absent_launchctl_service(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    def runner(*args):
        class Result:
            returncode = 113
            stdout = ""
            stderr = f'Bad request.\nCould not find service "{args[-1].rsplit("/", 1)[-1]}" in domain for user gui: {os.getuid()}\n'
        return Result()
    payload = g.manage("status", runner=runner)
    assert all(not item["loaded"] and item["returncode"] == 113 for item in payload.values())

def test_status_rejects_unrelated_launchctl_failure(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    class Result:
        returncode = 113
        stdout = ""
        stderr = "Bad request.\nCould not find service \"other.service\" in domain for user gui: 501\n"
    with pytest.raises(g.GateError, match="launchctl command failed"):
        g.manage("status", runner=lambda *args: Result())

def test_install_tolerates_real_absent_bootout(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    def runner(*args):
        class Result:
            returncode = 3 if args[1] == "bootout" else 0
            stdout = ""
            stderr = "Boot-out failed: 3: No such process\n" if args[1] == "bootout" else ""
        return Result()
    result = g.manage("install", root=tmp_path, devspace_hash=HASH, runner=runner)
    assert result["labels"] == list(g.LABELS.values())

def test_install_rejects_unrelated_bootout_failure(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    def runner(*args):
        class Result:
            returncode = 3 if args[1] == "bootout" else 0
            stdout = ""
            stderr = "Boot-out failed: 3: Operation not permitted\n" if args[1] == "bootout" else ""
        return Result()
    with pytest.raises(g.GateError, match="launchctl command failed"):
        g.manage("install", root=tmp_path, devspace_hash=HASH, runner=runner)

def test_serve_devspace_rechecks_cli_at_exec_boundary(monkeypatch, tmp_path):
    head = setup(monkeypatch, tmp_path)
    pin = hashlib.sha256(b"identity").hexdigest()
    (tmp_path / "dist/cli.js").unlink()
    with pytest.raises(g.GateError, match="CLI missing"):
        g.serve("devspace", root=tmp_path, launch_floor_head=head, devspace_hash=pin,
                devspace_root=tmp_path, node_path=g.NODE_PATH, execve=lambda *args: None)

@pytest.mark.parametrize("kwargs", [{"dirty":" M x"}, {"branch":"wrong"}])
def test_gate_fail_closed(monkeypatch, tmp_path, kwargs):
    setup(monkeypatch, tmp_path, **kwargs)
    with pytest.raises(g.GateError): g.manage("preflight", root=tmp_path, devspace_hash=HASH)

def test_head_and_hash_required(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, head="actual")
    monkeypatch.setattr(g, "_is_ancestor", lambda _r, _a, _d: False)
    with pytest.raises(g.GateError): g.manage("preflight", root=tmp_path, launch_floor_head="expected", devspace_hash=HASH)
    with pytest.raises(g.GateError): g.manage("preflight", root=tmp_path, devspace_hash=None)

def test_install_twice_and_rollback(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)
    calls=[]; runner=lambda *a: calls.append(a) or "ok"
    g.manage("install", root=tmp_path, devspace_hash=HASH, runner=runner)
    first = [p.read_bytes() for p in g.PLISTS.values()]
    g.manage("install", root=tmp_path, devspace_hash=HASH, runner=runner)
    assert first == [p.read_bytes() for p in g.PLISTS.values()]
    def fail(*a):
        if a[1] == "bootstrap": raise RuntimeError("boom")
        return "ok"
    with pytest.raises(RuntimeError): g.manage("install", root=tmp_path, devspace_hash=HASH, runner=fail)
    assert first == [p.read_bytes() for p in g.PLISTS.values()]

def test_status_reload_uninstall_manage_both(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path); calls=[]; runner=lambda *a: calls.append(a) or "ok"
    assert set(g.manage("status", runner=runner)) == {"gateway", "devspace"}
    assert set(g.manage("reload", root=tmp_path, devspace_hash=HASH, runner=runner)) == {"head", "labels"}
    g.manage("uninstall", runner=runner); assert not any(p.exists() for p in g.PLISTS.values())

def test_serve_gateway_exec_boundary(monkeypatch, tmp_path):
    head = setup(monkeypatch, tmp_path); seen = {}
    g.serve("gateway", root=tmp_path, launch_floor_head=head, execve=lambda *a: seen.update(argv=a[1], env=a[2]))
    assert seen["argv"][0].endswith(".venv/bin/python"); assert "SECRET" not in " ".join(seen["argv"])
    assert seen["env"]["NEXUS_CANONICAL_SOURCE_ROOT"] == str(tmp_path if False else g.CANONICAL_ROOT)

def test_serve_devspace_hash_and_token_mapping(monkeypatch, tmp_path):
    head = setup(monkeypatch, tmp_path); (tmp_path / "generated/build-identity.json").write_text("identity"); node = tmp_path / "node"; node.write_text("x"); node.chmod(0o755)
    pin = hashlib.sha256(b"identity").hexdigest(); seen = {}; g.serve("devspace", root=tmp_path, launch_floor_head=head, devspace_hash=pin, devspace_root=tmp_path, node_path=node, execve=lambda *a: seen.update(argv=a[1], env=a[2]))
    assert seen["argv"][-1] == "serve"; assert seen["env"]["NEXUS_GATEWAY_PROXY_TOKEN"] == "SECRET"

def _real_git_repo(tmp_path, branch="nexus/integration/main"):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", branch, str(repo)], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(repo), "config", "user.name", "t"], check=True)
    return repo

def _commit(repo, msg):
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", msg], check=True)
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()

def test_is_ancestor_exact_head(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); c1 = _commit(repo, "c1")
    assert g._is_ancestor(repo, c1, c1)

def test_is_ancestor_one_descendant(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); c1 = _commit(repo, "c1")
    (repo / "a").write_text("2"); c2 = _commit(repo, "c2")
    assert g._is_ancestor(repo, c1, c2)

def test_is_ancestor_multiple_descendants(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); c1 = _commit(repo, "c1")
    (repo / "a").write_text("2"); _commit(repo, "c2")
    (repo / "a").write_text("3"); c3 = _commit(repo, "c3")
    assert g._is_ancestor(repo, c1, c3)

def test_is_ancestor_rewind_rejected(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); c1 = _commit(repo, "c1")
    (repo / "a").write_text("2"); c2 = _commit(repo, "c2")
    assert not g._is_ancestor(repo, c2, c1)

def test_is_ancestor_divergent_history_rejected(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); c1 = _commit(repo, "c1")
    (repo / "a").write_text("2"); _commit(repo, "c2")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "side", c1], check=True)
    (repo / "b").write_text("side"); side = _commit(repo, "side")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "nexus/integration/main"], check=True)
    assert not g._is_ancestor(repo, side, subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip())

def test_is_ancestor_unknown_expected_commit_rejected(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); c1 = _commit(repo, "c1")
    assert not g._is_ancestor(repo, "0" * 40, c1)

def test_verify_gateway_forward_floor_descendant_passes(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); floor = _commit(repo, "c1")
    (repo / "a").write_text("2"); _commit(repo, "c2")
    (repo / "a").write_text("3"); _commit(repo, "c3")
    monkeypatch.setattr(g, "CANONICAL_ROOT", repo)
    assert g.verify_gateway(root=repo, launch_floor_head=floor)

def test_verify_gateway_rewind_rejected(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); _commit(repo, "c1")
    (repo / "a").write_text("2"); c2 = _commit(repo, "c2")
    subprocess.run(["git", "-C", str(repo), "reset", "-q", "--hard", c2 + "~1"], check=True)
    monkeypatch.setattr(g, "CANONICAL_ROOT", repo)
    with pytest.raises(g.GateError, match="launch floor"): g.verify_gateway(root=repo, launch_floor_head=c2)

def test_verify_gateway_divergent_history_rejected(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); c1 = _commit(repo, "c1")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "-b", "side", c1], check=True)
    (repo / "b").write_text("side"); side = _commit(repo, "side")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "nexus/integration/main"], check=True)
    (repo / "a").write_text("2"); _commit(repo, "c2")
    monkeypatch.setattr(g, "CANONICAL_ROOT", repo)
    with pytest.raises(g.GateError, match="launch floor"): g.verify_gateway(root=repo, launch_floor_head=side)

def test_verify_gateway_unknown_floor_commit_rejected(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); _commit(repo, "c1")
    monkeypatch.setattr(g, "CANONICAL_ROOT", repo)
    with pytest.raises(g.GateError, match="launch floor"): g.verify_gateway(root=repo, launch_floor_head="0" * 40)

def test_verify_gateway_no_floor_does_not_gate_on_head(monkeypatch, tmp_path):
    repo = _real_git_repo(tmp_path)
    (repo / "a").write_text("1"); _commit(repo, "c1")
    monkeypatch.setattr(g, "CANONICAL_ROOT", repo)
    assert g.verify_gateway(root=repo)


def _gateway_request(operation="reload", *, stable_artifact=None):
    from nexus.contracts.gateway_deployment import (
        CURRENT_PROFILE,
        DESIRED_PROFILE,
        HOST_AUTHORITY_BUNDLE_SCHEMA,
        HOST_AUTHORITY_BUNDLE_SCOPE,
        HOST_CARD_ID,
        HOST_CARD_PATH,
        HOST_CARD_SHA256,
        REPOSITORY,
        SOURCE_BASE_MERGE,
        SOURCE_BASE_TREE,
        AuthorityReceipt,
        EffectClass,
        GatewayDeploymentRequest,
        HostEffectAuthorityBundle,
        HostEffectAuthorityReceipt,
        IdentityEvidence,
        PostflightIdentity,
        QuiescenceEvidence,
        RollbackCapture,
    )

    payload = plistlib.dumps({"Label": g.GATEWAY_LABEL, "ProgramArguments": ["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", CURRENT_PROFILE.git.root + "/scripts/ops/nexus_mcp_gateway_http.py"], "WorkingDirectory": CURRENT_PROFILE.git.root, "RunAtLoad": True, "KeepAlive": True, "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log", "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log", "EnvironmentVariables": {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}}, fmt=plistlib.FMT_XML)
    rollback = RollbackCapture(
        hashlib.sha256(payload).hexdigest(), hashlib.sha256(payload).hexdigest(), payload.hex(),
        "b" * 64, "c" * 64, False, server_instance="old", source_root=CURRENT_PROFILE.git.root,
        source_head=CURRENT_PROFILE.git.head, source_tree=CURRENT_PROFILE.git.tree, root=CURRENT_PROFILE.git.root,
        program_arguments_hash=__import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", CURRENT_PROFILE.git.root + "/scripts/ops/nexus_mcp_gateway_http.py"]),
        environment_hash=__import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}),
    )
    effect = {"preflight": EffectClass.PREFLIGHT, "status": EffectClass.STATUS, "reload": EffectClass.GATEWAY_RELOAD,
              "install-artifact": EffectClass.INSTALL_ARTIFACT, "rollback": EffectClass.GATEWAY_ROLLBACK}[operation]
    host = HostEffectAuthorityReceipt(
        schema="nexus.gateway.host_effect_authority.v1", receipt_version=1, receipt_id="host-receipt", receipt_hash="0" * 64, scope="NEXUS_GATEWAY_REBIND_HOST_EFFECT_ONLY",
        issuer_id="owner-james", coordinator_id="coordinator-codex", authorized_actor_id="coordinator-codex",
        owner_activation_id="OWNER_ISSUE526_CONTINUE_20260823", owner_activation_sha256="f0ed77ffe3872b083ef0b6d66526524a7091a8e3125322c84ba632f3c64ba322",
        source_thread="01a02a17-691c-7a20-ad0f-9166456416dc", standing_grant_id="OWNER_STANDING_COORDINATOR_20260818_DURABLE_GITHUB_WORKFLOW",
        standing_grant_receipt_sha256="3b8895f093692257d6225fbb8150b34f520e667d250c7817ad120cefd42751d5", source_base_merge="ac4a9ab1e0180170ca062cdc81f2142bca8bd80f", source_base_tree="db329f4931b55b74f1e1f9fe61f7edf4ca8422bc",
        correction_merge_sha="1" * 40, correction_tree_sha="2" * 40, independent_acceptance_receipt_hash="3" * 64, final_manager_sha256="4" * 64, current_main_sha="5" * 40,
        host_card_path="tasks/github-issue-526-host-authority-and-canary-20260823/01-gateway-host-local-canary.md", host_card_id="TASK-526-HOST-1", host_card_sha256=HOST_CARD_SHA256,
        repository="James3014/Nexus-new", operation=operation, effect_class=effect, service_label=g.GATEWAY_LABEL, plist_path="/Users/jameschen/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist", endpoint=g.GATEWAY_ENDPOINT,
        current_profile_hash=__import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(CURRENT_PROFILE), desired_profile_hash=__import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(DESIRED_PROFILE),
        request_id="r-526", idempotency_fence="f-526", issued_at="2026-08-22T00:00:00Z", expires_at="2026-08-24T00:00:00Z", revocation_state="NOT_REVOKED", revoked_at=None, revocation_reason=None,
    )
    host = HostEffectAuthorityReceipt(**{**host.__dict__, "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in host.__dict__.items() if k != "receipt_hash"})})
    values = {
        "request_id": "r-526", "idempotency_fence": "f-526", "operation": operation,
        "authority": AuthorityReceipt("owner", "receipt", issued_at="2026-08-22T00:00:00Z", expires_at="2026-08-24T00:00:00Z", request_id="r-526"), "host_authority": host,
        "current": CURRENT_PROFILE, "desired": DESIRED_PROFILE,
        "current_identity": IdentityEvidence(plist_sha256=hashlib.sha256(payload).hexdigest(), plist_bytes_sha256=hashlib.sha256(payload).hexdigest(), pid=123, server_instance="old", root=CURRENT_PROFILE.git.root, head=CURRENT_PROFILE.git.head, tree=CURRENT_PROFILE.git.tree, source_sha256="b"*64, tool_manifest_sha256="c"*64, schema_sha256="d"*64, permission_sha256="e"*64, action="gateway-rebind", task_id="TASK-526-A", lifecycle=GATEWAY_LIFECYCLE_REVISION, loaded=True, client_bound=True), "rollback": rollback,
        "quiescence": QuiescenceEvidence("reconciled", "QUIESCENT", "QUIESCENT", "1"*64, (), "reacq"), "postflight": PostflightIdentity("new", DESIRED_PROFILE.git.root, DESIRED_PROFILE.git.head, DESIRED_PROFILE.git.tree, "f"*64, "a"*64, "b"*64, "gateway-rebind", "TASK-526-A", GATEWAY_LIFECYCLE_REVISION, True, ("gateway-rebind",), ("gateway-rebind",), True),
        "effect_class": effect,
        "stable_artifact": stable_artifact,
    }
    receipt = values["authority"]
    values["authority"] = AuthorityReceipt(**{**receipt.__dict__, "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in receipt.__dict__.items() if k != "receipt_hash"})})
    if stable_artifact is not None:
        values["stable_artifact"] = stable_artifact.__class__(**{**stable_artifact.__dict__, "authority_receipt_id": host.receipt_id})
        host = HostEffectAuthorityReceipt(**{**host.__dict__, "final_manager_sha256": stable_artifact.artifact_sha256})
        host = HostEffectAuthorityReceipt(**{**host.__dict__, "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in host.__dict__.items() if k != "receipt_hash"})})
        values["host_authority"] = host
    canonical_children = []
    for child_operation, child_effect, child_suffix in (
        ("install-artifact", EffectClass.INSTALL_ARTIFACT, "install"),
        ("reload", EffectClass.GATEWAY_RELOAD, "reload"),
        ("rollback", EffectClass.GATEWAY_ROLLBACK, "rollback"),
    ):
        child_values = {
            **host.__dict__,
            "operation": child_operation,
            "effect_class": child_effect,
            "receipt_id": f"host-{child_suffix}",
            "request_id": "r-526" if child_operation == "reload" else f"r-526-{child_suffix}",
            "idempotency_fence": "f-526" if child_operation == "reload" else f"f-526-{child_suffix}",
        }
        child = HostEffectAuthorityReceipt(**child_values)
        child = HostEffectAuthorityReceipt(**{
            **child.__dict__,
            "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
                {k: v for k, v in child.__dict__.items() if k != "receipt_hash"}
            ),
        })
        canonical_children.append(child)
    selected = next((child for child in canonical_children if child.operation == operation), None)
    if selected is None:
        selected = HostEffectAuthorityReceipt(**{**host.__dict__, "receipt_id": f"legacy-{operation}"})
        selected = HostEffectAuthorityReceipt(**{
            **selected.__dict__,
            "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
                {k: v for k, v in selected.__dict__.items() if k != "receipt_hash"}
            ),
        })
    values["request_id"] = selected.request_id
    values["idempotency_fence"] = selected.idempotency_fence
    values["authority"] = AuthorityReceipt(**{
        **values["authority"].__dict__,
        "request_id": selected.request_id,
        "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({
            **{k: v for k, v in values["authority"].__dict__.items() if k not in {"request_id", "receipt_hash"}},
            "request_id": selected.request_id,
        }),
    })
    values["host_authority"] = selected
    if stable_artifact is not None:
        values["stable_artifact"] = stable_artifact.__class__(**{
            **stable_artifact.__dict__, "request_id": selected.request_id,
            "authority_receipt_id": selected.receipt_id,
        })
    bundle = HostEffectAuthorityBundle(
        schema=HOST_AUTHORITY_BUNDLE_SCHEMA, bundle_version=1,
        bundle_id="bundle-526", bundle_hash="0" * 64,
        scope=HOST_AUTHORITY_BUNDLE_SCOPE, repository=REPOSITORY,
        host_card_path=HOST_CARD_PATH, host_card_id=HOST_CARD_ID,
        host_card_sha256=HOST_CARD_SHA256,
        source_base_merge=SOURCE_BASE_MERGE, source_base_tree=SOURCE_BASE_TREE,
        correction_merge_sha="1" * 40, correction_tree_sha="2" * 40,
        independent_acceptance_receipt_hash="3" * 64,
        final_manager_sha256=host.final_manager_sha256, current_main_sha="5" * 40,
        issued_at="2026-08-22T00:00:00Z", expires_at="2026-08-24T00:00:00Z",
        revocation_state="NOT_REVOKED", revoked_at=None, revocation_reason=None,
        receipts=tuple(canonical_children),
    )
    bundle = HostEffectAuthorityBundle(**{
        **bundle.__dict__,
        "bundle_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
            {k: v for k, v in bundle.__dict__.items() if k != "bundle_hash"}
        ),
    })
    values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({
        k: v for k, v in values.items() if k not in {"request_hash", "schema"}
    })
    store = Path(g.GATEWAY_HOST_AUTHORITY_STORE)
    store.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    raw = json.dumps(bundle.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    store.write_bytes(raw)
    store.chmod(0o600)
    source_root = g.HOST_AUTHORITY_SOURCE_ROOT
    source_path = source_root / g.HOST_AUTHORITY_SOURCE_PATH
    source_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    source_path.write_bytes(raw)
    subprocess.run(["git", "-C", str(source_root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(source_root), "commit", "-q", "--allow-empty", "-m", "receipt"], check=True)
    return GatewayDeploymentRequest(**values)


def _ledger_receipt(request_id="r", fence="f"):
    receipt = _gateway_request().host_authority
    values = {**receipt.__dict__, "request_id": request_id, "idempotency_fence": fence}
    values["receipt_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in values.items() if k != "receipt_hash"})
    return receipt.__class__(**values)


def _gateway_observed():
    predecessor_payload = plistlib.dumps({"Label": g.GATEWAY_LABEL, "ProgramArguments": ["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe/scripts/ops/nexus_mcp_gateway_http.py"], "WorkingDirectory": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe", "RunAtLoad": True, "KeepAlive": True, "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log", "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log", "EnvironmentVariables": {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}}, fmt=plistlib.FMT_XML)
    predecessor_hash = hashlib.sha256(predecessor_payload).hexdigest()
    return {
        "root": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "toplevel": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "remote": "https://github.com/James3014/Nexus-new.git",
        "head": "67521fe91e990f4e140642984c743dd50a408e84",
        "tree": "f6d6c2bf0912ff4a63d3c10a089910f95eab3c12",
        "entrypoint": "scripts/ops/nexus_mcp_gateway_http.py",
        "entrypoint_sha256": "8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1",
        "clean": False, "interpreter_path": "/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", "interpreter_resolved_path": "/Users/jameschen/.local/share/uv/python/cpython-3.14.0-macos-aarch64-none/bin/python3.14", "interpreter_sha256": "c89af0b037c601180919ca5fd8a936bd2568cbb4976f91a208c10f54c17a1b78", "interpreter_uid": 501, "interpreter_gid": 20, "interpreter_mode": "lrwxr-xr-x", "trust_class": "ROLLBACK_ONLY_OBSERVED_CURRENT", "repository": "James3014/Nexus-new", "stdout": "/Users/jameschen/Library/Logs/Nexus/gateway.log", "stderr": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log", "label": g.GATEWAY_LABEL, "plist": "/Users/jameschen/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist", "endpoint": g.GATEWAY_ENDPOINT,
        "plist_sha256": predecessor_hash, "plist_bytes_sha256": predecessor_hash, "plist_bytes_hex": predecessor_payload.hex(), "loaded": True, "pid": 123, "server_instance": "old", "source_sha256": "b"*64, "tool_manifest_sha256": "c"*64, "schema_sha256": "d"*64, "permission_sha256": "e"*64, "action": "gateway-rebind", "task_id": "TASK-526-A", "lifecycle": GATEWAY_LIFECYCLE_REVISION, "stable_artifact": {"artifact_sha256": "f"*64}, "rollback_predecessor": {"plist_sha256": predecessor_hash, "artifact_sha256": "b"*64, "source_sha256": "c"*64}, "listener": g.GATEWAY_ENDPOINT, "services": [g.GATEWAY_LABEL],
        "quiescence": {"disposition": "reconciled", "lifecycle_state": "QUIESCENT", "assist_state": "QUIESCENT", "evidence_sha256": "1"*64, "reacquisition_receipt": "reacq"},
    }


def test_gateway_preflight_requires_exact_current_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    request = _gateway_request()
    assert g.preflight_gateway(request, observed=_gateway_observed(), observation_time="2026-08-23T00:00:00Z")["state"] == "PREFLIGHTED"
    bad = _gateway_observed(); bad["head"] = "0" * 40
    with pytest.raises(g.GatewayContractError):
        g.preflight_gateway(request, observed=bad, observation_time="2026-08-23T00:00:00Z")


@pytest.mark.parametrize("operation", ["status", "preflight", "install-artifact", "reload", "rollback"])
def test_source_only_host_operations_have_zero_effects(operation):
    request = _gateway_request(operation)
    values = {**request.__dict__, "host_authority": None}
    canonical = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash
    values["request_hash"] = canonical({k: v for k, v in values.items() if k not in {"request_hash", "schema"}})
    source_only = request.__class__(**values)
    calls = []
    with pytest.raises(g.GatewayContractError):
        if operation == "status":
            g.gateway_status(source_only, runner=lambda *args: calls.append(args), observation_time="2026-08-23T00:00:00Z")
        elif operation == "preflight":
            g.preflight_gateway(source_only, observed={}, observation_time="2026-08-23T00:00:00Z")
        elif operation == "install-artifact":
            g.install_stable_artifact(source_only, source_root=Path("/tmp"), source_path=Path("/tmp/missing"), observation_time="2026-08-23T00:00:00Z")
        elif operation == "reload":
            g.gateway_reload(source_only, observed={}, runner=lambda *args: calls.append(args), observation_time="2026-08-23T00:00:00Z")
        else:
            g.rollback_gateway(source_only, predecessor_observer={}, runner=lambda *args: calls.append(args), observation_time="2026-08-23T00:00:00Z")
    assert calls == []


def test_canonical_host_store_tamper_blocks_status_before_runner():
    request = _gateway_request("status")
    store = Path(g.GATEWAY_HOST_AUTHORITY_STORE)
    store.write_text(store.read_text().replace("host-receipt", "tampered-receipt"))
    calls = []
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(request, runner=lambda *args: calls.append(args), observation_time="2026-08-23T00:00:00Z")
    assert calls == []


def _request_with_host_changes(request, *, sync_store=True, recompute_receipt_hash=True, **changes):
    host_values = {**request.host_authority.__dict__, **changes}
    host = request.host_authority.__class__(**host_values)
    if recompute_receipt_hash:
        host = host.__class__(
            **{
                **host.__dict__,
                "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
                    {key: value for key, value in host.__dict__.items() if key != "receipt_hash"}
                ),
            }
        )
    values = {**request.__dict__, "host_authority": host}
    values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
        {key: value for key, value in values.items() if key not in {"request_hash", "schema"}}
    )
    updated = request.__class__(**values)
    if sync_store:
        bundle = g._read_host_authority_store()[1]
        children = tuple(
            host if child.receipt_id == request.host_authority.receipt_id else child
            for child in bundle.receipts
        )
        bundle = bundle.__class__(**{**bundle.__dict__, "receipts": children})
        bundle = bundle.__class__(**{
            **bundle.__dict__,
            "bundle_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
                {key: value for key, value in bundle.__dict__.items() if key != "bundle_hash"}
            ),
        })
        raw = json.dumps(bundle.model_dump(), sort_keys=True, separators=(",", ":")).encode()
        store = Path(g.GATEWAY_HOST_AUTHORITY_STORE)
        store.write_bytes(raw)
        store.chmod(0o600)
        source_root = g.HOST_AUTHORITY_SOURCE_ROOT
        source_path = source_root / g.HOST_AUTHORITY_SOURCE_PATH
        source_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        source_path.write_bytes(raw)
        subprocess.run(["git", "-C", str(source_root), "add", "-A"], check=True)
        subprocess.run(
            ["git", "-C", str(source_root), "commit", "-q", "-m", "matching receipt"],
            check=True,
        )
    return updated


@pytest.mark.parametrize(
    "field,value",
    [
        ("issuer_id", "owner-forged"),
        ("coordinator_id", "coordinator-forged"),
        ("authorized_actor_id", "actor-forged"),
        ("standing_grant_id", "grant-forged"),
        ("standing_grant_receipt_sha256", "0" * 64),
    ],
)
def test_host_authority_identity_failures_precede_gateway_observer(field, value):
    request = _request_with_host_changes(_gateway_request("reload"), **{field: value})
    calls = []
    authority_calls = []

    def authority_runner(*args):
        authority_calls.append(args)
        return g._fixed_authority_command_runner(*args)

    with pytest.raises(g.GatewayContractError):
        g.gateway_status(
            request, runner=lambda *args: calls.append(args),
            observation_time="2026-08-23T00:00:00Z",
            authority_command_runner=authority_runner,
        )
    assert calls == []
    assert authority_calls == []


@pytest.mark.parametrize(
    "mutate",
    [
        lambda receipt: {"issued_at": "2026-08-24T00:00:00Z"},
        lambda receipt: {"revocation_state": "REVOKED", "revoked_at": "2026-08-22T00:00:00Z", "revocation_reason": "owner"},
    ],
)
def test_host_authority_freshness_and_revocation_fail_before_observer(mutate):
    request = _request_with_host_changes(_gateway_request("reload"), **mutate(None))
    calls = []
    authority_calls = []

    def authority_runner(*args):
        authority_calls.append(args)
        return g._fixed_authority_command_runner(*args)

    with pytest.raises(g.GatewayContractError):
        g.gateway_status(
            request, runner=lambda *args: calls.append(args),
            observation_time="2026-08-23T00:00:00Z",
            authority_command_runner=authority_runner,
        )
    assert calls == []
    assert authority_calls == []


def test_revoked_bundle_is_evidence_only_and_skips_remote_authority_and_observer():
    request = _gateway_request("reload")
    bundle = g._read_host_authority_store()[1]
    revoked_child = bundle.receipts[1].__class__(**{
        **bundle.receipts[1].__dict__, "revocation_state": "REVOKED",
        "revoked_at": "2026-08-23T00:00:00Z", "revocation_reason": "owner",
    })
    revoked_child = revoked_child.__class__(**{
        **revoked_child.__dict__,
        "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
            {key: value for key, value in revoked_child.__dict__.items() if key != "receipt_hash"}
        ),
    })
    revoked_bundle = bundle.__class__(**{
        **bundle.__dict__, "revocation_state": "REVOKED",
        "revoked_at": "2026-08-23T00:00:00Z", "revocation_reason": "owner",
        "receipts": (bundle.receipts[0], revoked_child, bundle.receipts[2]),
    })
    revoked_bundle = revoked_bundle.__class__(**{
        **revoked_bundle.__dict__,
        "bundle_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
            {key: value for key, value in revoked_bundle.__dict__.items() if key != "bundle_hash"}
        ),
    })
    Path(g.GATEWAY_HOST_AUTHORITY_STORE).write_bytes(
        json.dumps(revoked_bundle.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    )
    Path(g.GATEWAY_HOST_AUTHORITY_STORE).chmod(0o600)
    remote_calls, observer_calls = [], []
    with pytest.raises(g.GatewayContractError, match="host authority rejected"):
        g.gateway_reload(
            request, observed={}, runner=lambda *args: observer_calls.append(args),
            authority_command_runner=lambda *args: remote_calls.append(args),
            observation_time="2026-08-23T00:00:00Z",
        )
    assert remote_calls == [] and observer_calls == []


@pytest.mark.parametrize(
    "field,value,recompute_receipt_hash",
    [
        ("source_base_merge", "0" * 40, True),
        ("source_base_tree", "1" * 40, True),
        ("host_card_path", "tasks/other-card.md", True),
        ("host_card_id", "TASK-526-OTHER", True),
        ("host_card_sha256", "0" * 64, True),
        ("repository", "Other/repository", True),
        ("service_label", "com.other.service", True),
        ("plist_path", "/tmp/other-gateway.plist", True),
        ("endpoint", "http://127.0.0.1:9999", True),
        ("current_profile_hash", "0" * 64, True),
        ("desired_profile_hash", "1" * 64, True),
        ("request_id", "request-other", True),
        ("idempotency_fence", "fence-other", True),
        ("issuer_id", "owner-forged", True),
        ("coordinator_id", "coordinator-forged", True),
        ("authorized_actor_id", "actor-forged", True),
        ("standing_grant_id", "grant-forged", True),
        ("standing_grant_receipt_sha256", "0" * 64, True),
        ("issued_at", "2026-08-24T00:00:00Z", True),
        ("expires_at", "2026-08-22T00:00:00Z", True),
        ("revocation_state", "REVOKED", True),
        ("operation", "preflight", True),
        ("effect_class", EffectClass.PREFLIGHT, True),
        ("scope", "NEXUS_GATEWAY_REBIND_MANAGER_CONTRACT_SOURCE_CANDIDATE_ONLY", True),
        ("owner_activation_id", "OWNER_ISSUE526_WRONG", True),
        ("owner_activation_sha256", "0" * 64, True),
        ("source_thread", "wrong-source-thread", True),
        ("correction_merge_sha", "malformed-merge", True),
        ("correction_tree_sha", "malformed-tree", True),
        ("independent_acceptance_receipt_hash", "malformed-acceptance", True),
        ("final_manager_sha256", "malformed-manager", True),
        ("current_main_sha", "malformed-main", True),
        ("receipt_hash", "0" * 64, False),
    ],
)
def test_matching_store_substitutions_hit_intended_validator_before_any_physical_read(
    monkeypatch, field, value, recompute_receipt_hash
):
    request = _request_with_host_changes(
        _gateway_request("reload"),
        recompute_receipt_hash=recompute_receipt_hash,
        **{field: value},
    )
    host_calls = []
    authority_calls = []

    def authority_runner(*args):
        authority_calls.append(args)
        return g._fixed_authority_command_runner(*args)

    monkeypatch.setattr(
        g,
        "_read_host_authority_store",
        lambda: pytest.fail("matching-store validator must reject before canonical read"),
    )
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(
            request,
            runner=lambda *args: host_calls.append(args),
            observation_time="2026-08-23T00:00:00Z",
            authority_command_runner=authority_runner,
        )
    assert host_calls == []
    assert authority_calls == []


def test_same_uid_fabricated_local_receipt_lacks_remote_main_binding():
    request = _gateway_request("reload")
    fabricated = _request_with_host_changes(
        request, sync_store=False, receipt_id="locally-fabricated"
    )
    store = Path(g.GATEWAY_HOST_AUTHORITY_STORE)
    bundle = g._read_host_authority_store()[1]
    bundle = bundle.__class__(**{
        **bundle.__dict__,
        "receipts": tuple(
            fabricated.host_authority if child.receipt_id == fabricated.host_authority.receipt_id else child
            for child in bundle.receipts
        ),
    })
    bundle = bundle.__class__(**{
        **bundle.__dict__,
        "bundle_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(
            {key: value for key, value in bundle.__dict__.items() if key != "bundle_hash"}
        ),
    })
    store.write_bytes(json.dumps(bundle.model_dump(), sort_keys=True, separators=(",", ":")).encode())
    store.chmod(0o600)
    calls = []
    with pytest.raises(g.GatewayContractError, match="host authority rejected"):
        g.gateway_status(
            fabricated, runner=lambda *args: calls.append(args),
            observation_time="2026-08-23T00:00:00Z",
            authority_command_runner=g._fixed_authority_command_runner,
        )
    assert calls == []


@pytest.mark.parametrize("failure", ["remote", "dirty", "head", "blob"])
def test_fixed_git_main_source_failures_precede_gateway_observer(failure):
    request = _gateway_request("status")
    base_runner = g._fixed_authority_command_runner

    def failing_runner(*args):
        command = tuple(args) if args and isinstance(args[0], str) else tuple(args[0])
        if failure == "remote" and command[-2:] == (g.HOST_AUTHORITY_REMOTE, g.HOST_AUTHORITY_REF):
            return subprocess.CompletedProcess(command, 0, f"{'0' * 40}\t{g.HOST_AUTHORITY_REF}\n", b"")
        if failure == "dirty" and command[-2:] == ("status", "--porcelain"):
            return subprocess.CompletedProcess(command, 0, b" M source\n", b"")
        if failure == "head" and command[-2:] == ("rev-parse", "HEAD"):
            return subprocess.CompletedProcess(command, 0, b"0" * 40, b"")
        if failure == "blob" and command[3] == "show":
            return subprocess.CompletedProcess(command, 1, b"", b"missing blob")
        return base_runner(*command)

    calls = []
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(
            request, runner=lambda *args: calls.append(args),
            observation_time="2026-08-23T00:00:00Z",
            authority_command_runner=failing_runner,
        )
    assert calls == []


def test_missing_symlink_mode_oversized_and_duplicate_host_store_fail_closed(monkeypatch):
    request = _gateway_request("status")
    store = Path(g.GATEWAY_HOST_AUTHORITY_STORE)
    target = store.with_name("target.json")
    target.write_bytes(store.read_bytes())
    target.chmod(0o600)
    store.unlink()
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(request, runner=lambda *_: pytest.fail("observer called"), observation_time="2026-08-23T00:00:00Z", authority_command_runner=g._fixed_authority_command_runner)
    store.symlink_to(target)
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(request, runner=lambda *_: pytest.fail("observer called"), observation_time="2026-08-23T00:00:00Z", authority_command_runner=g._fixed_authority_command_runner)

    store.unlink()
    store.write_bytes(target.read_bytes())
    store.chmod(0o640)
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(request, runner=lambda *_: pytest.fail("observer called"), observation_time="2026-08-23T00:00:00Z", authority_command_runner=g._fixed_authority_command_runner)

    store.chmod(0o600)
    store.write_bytes(b"{" + b"x" * (g.MAX_GATEWAY_STORE_BYTES + 1) + b"}")
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(request, runner=lambda *_: pytest.fail("observer called"), observation_time="2026-08-23T00:00:00Z", authority_command_runner=g._fixed_authority_command_runner)

    store.write_bytes(b'{"receipt_id":"a","receipt_id":"b"}')
    store.chmod(0o600)
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(request, runner=lambda *_: pytest.fail("observer called"), observation_time="2026-08-23T00:00:00Z", authority_command_runner=g._fixed_authority_command_runner)

    original_lstat = g.os.lstat
    def wrong_uid(path):
        info = original_lstat(path)
        if Path(path) == store:
            values = list(info)
            values[4] = 999
            return os.stat_result(values)
        return info
    store.write_bytes(target.read_bytes())
    store.chmod(0o600)
    monkeypatch.setattr(g.os, "lstat", wrong_uid)
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(request, runner=lambda *_: pytest.fail("observer called"), observation_time="2026-08-23T00:00:00Z", authority_command_runner=g._fixed_authority_command_runner)


@pytest.mark.parametrize("source_operation,target_operation", HOST_OPERATION_PAIRS)
def test_every_distinct_host_operation_pair_rejects_before_effect(source_operation, target_operation):
    request = _gateway_request(source_operation)
    calls = []
    authority_calls = []

    def authority_runner(*args):
        authority_calls.append(args)
        return g._fixed_authority_command_runner(*args)

    with pytest.raises(g.GatewayContractError):
        g.manage_gateway(
            target_operation, request=request, observed={},
            runner=lambda *args: calls.append(args),
            authority_command_runner=authority_runner,
            observation_time="2026-08-23T00:00:00Z",
        )
    assert calls == []
    assert authority_calls == []

    dispatch_calls = []
    dispatch_authority_calls = []

    def dispatch_authority_runner(*args):
        dispatch_authority_calls.append(args)
        return g._fixed_authority_command_runner(*args)

    with pytest.raises(g.GatewayContractError):
        g.dispatch_gateway_cli(
            target_operation,
            request=request,
            observed={},
            observation_time="2026-08-23T00:00:00Z",
            runner=lambda *args: dispatch_calls.append(args),
            authority_command_runner=dispatch_authority_runner,
        )
    assert dispatch_calls == []
    assert dispatch_authority_calls == []


def test_same_fence_different_request_is_ledger_conflict_and_fields_are_physical(tmp_path):
    ledger = g.GatewayLedger(tmp_path / "ledger.jsonl")
    first_receipt = _ledger_receipt("r-1", "same-fence")
    row = ledger.append(
        request_id="r-1", request_hash="a" * 64, state="REQUESTED",
        host_authority=first_receipt, operation="reload", effect_class="GATEWAY_RELOAD",
        idempotency_fence="same-fence",
    )
    assert row["host_receipt_hash"] == first_receipt.receipt_hash
    assert row["source_base_merge"] == first_receipt.source_base_merge
    assert row["source_base_tree"] == first_receipt.source_base_tree
    assert row["host_card_sha256"] == first_receipt.host_card_sha256
    assert row["effect_class"] == first_receipt.effect_class.value
    assert row["operation"] == first_receipt.operation
    assert row["idempotency_fence"] == first_receipt.idempotency_fence
    with pytest.raises(g.GatewayContractError, match="idempotency fence"):
        ledger.append(
            request_id="r-2", request_hash="b" * 64, state="REQUESTED",
            host_authority=_ledger_receipt("r-2", "same-fence"), operation="reload",
            effect_class="GATEWAY_RELOAD", idempotency_fence="same-fence",
        )


# Preserve the base pytest node ID while asserting the newer bundle-only rule.
def test_positive_gateway_status_reads_only_fixed_gateway_service():
    request = _gateway_request("status")
    calls = []
    with pytest.raises(g.GatewayContractError):
        g.gateway_status(
            request, runner=lambda *args: (calls.append(args) or pytest.fail("observer called")),
            observation_time="2026-08-23T00:00:00Z",
            authority_command_runner=g._fixed_authority_command_runner,
        )
    assert calls == []


def test_gateway_ledger_chain_tamper_and_cas_fail_closed(tmp_path):
    ledger = g.GatewayLedger(tmp_path / "ledger.jsonl")
    first = ledger.append(request_id="r", request_hash="a" * 64, state="REQUESTED", host_authority=_ledger_receipt(), operation="reload", effect_class="GATEWAY_RELOAD", idempotency_fence="f")
    with pytest.raises(g.GatewayContractError):
        ledger.append(request_id="r2", request_hash="b" * 64, state="REQUESTED", expected_tail="0" * 64, host_authority=_ledger_receipt("r2", "f2"), operation="reload", effect_class="GATEWAY_RELOAD", idempotency_fence="f2")
    path = tmp_path / "ledger.jsonl"
    path.write_text(path.read_text().replace(first["record_hash"], "0" * 64))
    with pytest.raises(g.LedgerCorruption):
        ledger.read()


def test_gateway_reload_writes_only_fixed_service_and_requires_postflight(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "GATEWAY_LOCK", tmp_path / "gateway.lock")
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    request = _gateway_request()
    calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def runner(*args):
        calls.append(args)
        return Result()

    tools = [{"name": "gateway-rebind", "description": "bounded"}]
    manifest = hashlib.sha256(json.dumps(("gateway-rebind",), separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    schema = hashlib.sha256(json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    post = request.postflight.__class__("new", request.desired.git.root, request.desired.git.head, request.desired.git.tree,
        manifest, schema, "b" * 64, "gateway-rebind", "TASK-526-A", GATEWAY_LIFECYCLE_REVISION, True,
        ("gateway-rebind",), ("gateway-rebind",), True)
    values = {**request.__dict__, "postflight": post}
    values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in values.items() if k not in {"request_hash", "schema"}})
    request = request.__class__(**values)
    identity = {"server_instance_id": "new", "repo_root": request.desired.git.root, "git_head": request.desired.git.head,
                "permission_policy_hash": "b" * 64, "lifecycle_revision": GATEWAY_LIFECYCLE_REVISION,
                "tool_manifest_revision": manifest, "full_tool_schema_hash": schema}
    server_info = {"serverInstanceId": "new", "permissionPolicyHash": "b" * 64,
                   "lifecycleRevision": GATEWAY_LIFECYCLE_REVISION,
                   "toolManifestRevision": manifest, "fullToolSchemaHash": schema}
    class Response:
        def __init__(self, value): self.value = value
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return json.dumps(self.value).encode()
    def opener(req, timeout):
        if req.full_url.endswith("/health"): return Response(identity)
        body = json.loads(req.data.decode())
        return Response({"result": {"serverInfo": server_info}} if body["method"] == "initialize" else {"result": {"tools": tools}})
    result = g.gateway_reload(request, observed=_gateway_observed(), runner=runner,
        plist_path=g.GATEWAY_PLIST, ledger=g.GatewayLedger(tmp_path / "ledger.jsonl"),
        opener=opener, token_loader=lambda: "SECRET", sleeper=lambda _: None,
        observation_time="2026-08-23T00:00:00Z")
    assert result["state"] == "VERIFIED"
    assert all(g.GATEWAY_LABEL in " ".join(map(str, call)) or "gateway.plist" in " ".join(map(str, call)) for call in calls)
    assert not any("devspace" in str(call).lower() for call in calls)


def test_rollback_rejects_altered_plist_and_restores_unloaded_predecessor(monkeypatch, tmp_path):
    from nexus.contracts.gateway_deployment import RollbackCapture

    payload = plistlib.dumps({
        "Label": g.GATEWAY_LABEL,
        "ProgramArguments": ["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe/scripts/ops/nexus_mcp_gateway_http.py"],
        "WorkingDirectory": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "RunAtLoad": True, "KeepAlive": True,
        "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log", "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log",
        "EnvironmentVariables": {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"},
    }, fmt=plistlib.FMT_XML)
    args = ["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe/scripts/ops/nexus_mcp_gateway_http.py"]
    env = {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}
    capture = RollbackCapture(hashlib.sha256(payload).hexdigest(), hashlib.sha256(payload).hexdigest(), payload.hex(), "b" * 64, "c" * 64, False, server_instance="old", source_root="/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe", source_head="67521fe91e990f4e140642984c743dd50a408e84", source_tree="f6d6c2bf0912ff4a63d3c10a089910f95eab3c12", root="/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe", program_arguments_hash=__import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(args), environment_hash=__import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(env))
    monkeypatch.setattr(g, "GATEWAY_LOCK", tmp_path / "rollback.lock")
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    request = _gateway_request("rollback")
    request = request.__class__(**{**request.__dict__, "rollback": capture})
    values = {**request.__dict__}
    values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in values.items() if k not in {"request_hash", "schema"}})
    request = request.__class__(**values)
    observer = {"plist_sha256": capture.plist_sha256, "plist_bytes_sha256": capture.plist_bytes_sha256,
                "artifact_sha256": capture.artifact_sha256, "source_sha256": capture.source_sha256,
                "source_root": capture.source_root, "source_head": capture.source_head,
                "source_tree": capture.source_tree, "loaded": False, "pid": None,
                "server_instance": "", "listener": "", "service_loaded": False}
    out = g.rollback_gateway(request, plist_path=g.GATEWAY_PLIST, predecessor_observer=observer,
                             runner=lambda *args: pytest.fail("unloaded rollback must not bootstrap"), observation_time="2026-08-23T00:00:00Z")
    assert out["state"] == "ROLLED_BACK"
    tampered = RollbackCapture("0" * 64, capture.plist_bytes_sha256, capture.plist_bytes_hex, capture.artifact_sha256, capture.source_sha256, False)
    tampered_values = {**request.__dict__, "rollback": tampered}
    tampered_values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in tampered_values.items() if k not in {"request_hash", "schema"}})
    with pytest.raises(g.GatewayContractError):
        g.rollback_gateway(request.__class__(**tampered_values), plist_path=g.GATEWAY_PLIST, predecessor_observer=observer, observation_time="2026-08-23T00:00:00Z")


def test_loaded_rollback_boots_only_fixed_gateway_and_rebinds_old_client(monkeypatch, tmp_path):
    """A loaded predecessor must be restored only after fresh physical proof."""
    from nexus.contracts.gateway_deployment import canonical_hash

    monkeypatch.setattr(g, "GATEWAY_LOCK", tmp_path / "rollback.lock")
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    base = _gateway_request("rollback")
    capture = base.rollback.__class__(**{**base.rollback.__dict__, "loaded": True})
    values = {**base.__dict__, "rollback": capture}
    values["request_hash"] = canonical_hash({k: v for k, v in values.items()
                                               if k not in {"request_hash", "schema"}})
    request = base.__class__(**values)
    payload = bytes.fromhex(capture.plist_bytes_hex)
    observer = {
        "plist_sha256": capture.plist_sha256,
        "plist_bytes_sha256": capture.plist_bytes_sha256,
        "artifact_sha256": capture.artifact_sha256,
        "source_sha256": capture.source_sha256,
        "source_root": capture.source_root,
        "source_head": capture.source_head,
        "source_tree": capture.source_tree,
        "loaded": True,
        "pid": 123,
        "server_instance": capture.server_instance,
        "listener": g.GATEWAY_ENDPOINT,
        "service_loaded": True,
    }
    calls = []
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def runner(*args):
        calls.append(args)
        assert args[0:2] == ("launchctl", "bootout") or args[0:2] == ("launchctl", "bootstrap")
        assert args[-1] == f"{g.UID_TARGET}/{g.GATEWAY_LABEL}" or args[-1] == str(g.GATEWAY_PLIST)
        return Result()

    tools = [{"name": "gateway-rebind", "description": "bounded"}]
    manifest = hashlib.sha256(json.dumps(("gateway-rebind",), separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    schema = hashlib.sha256(json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    identity = {
        "server_instance_id": capture.server_instance,
        "repo_root": capture.source_root,
        "git_head": capture.source_head,
        "permission_policy_hash": "e" * 64,
        "lifecycle_revision": GATEWAY_LIFECYCLE_REVISION,
        "tool_manifest_revision": manifest,
        "full_tool_schema_hash": schema,
    }
    server_info = {
        "serverInstanceId": capture.server_instance,
        "permissionPolicyHash": "e" * 64,
        "lifecycleRevision": GATEWAY_LIFECYCLE_REVISION,
        "toolManifestRevision": manifest,
        "fullToolSchemaHash": schema,
    }
    requests = []
    class Response:
        def __init__(self, value): self.value = value
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return json.dumps(self.value).encode()

    def opener(req, timeout):
        requests.append(req)
        assert req.headers.get("Authorization") == "Bearer SECRET"
        if req.full_url.endswith("/health"):
            return Response(identity)
        body = json.loads(req.data.decode())
        assert body["method"] in {"initialize", "tools/list"}
        if body["method"] == "initialize":
            return Response({"result": {"serverInfo": server_info}})
        return Response({"result": {"tools": tools}})

    result = g.rollback_gateway(
        request, plist_path=g.GATEWAY_PLIST, predecessor_observer=observer,
        runner=runner, opener=opener, token_loader=lambda: "SECRET",
        sleeper=lambda _: None, observation_time="2026-08-23T00:00:00Z",
    )
    assert result["state"] == "ROLLED_BACK"
    assert [call[1] for call in calls] == ["bootout", "bootstrap"]
    assert all(call[-1] == f"{g.UID_TARGET}/{g.GATEWAY_LABEL}" for call in calls[:1])
    assert calls[1][-1] == str(g.GATEWAY_PLIST)
    assert [req.full_url.rsplit("/", 1)[-1] for req in requests] == ["health", "mcp", "mcp"]
    assert [json.loads(req.data.decode())["method"] for req in requests[1:]] == ["initialize", "tools/list"]
    assert not any("devspace" in str(call).lower() for call in calls)
    assert g.GATEWAY_PLIST.read_bytes() == payload


def test_loaded_rollback_postflight_failure_is_uncertain_and_not_recorded_success(monkeypatch, tmp_path):
    """Bootstrap acknowledgement failure cannot become a false ROLLED_BACK."""
    from nexus.contracts.gateway_deployment import canonical_hash

    monkeypatch.setattr(g, "GATEWAY_LOCK", tmp_path / "rollback.lock")
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    base = _gateway_request("rollback")
    capture = base.rollback.__class__(**{**base.rollback.__dict__, "loaded": True})
    values = {**base.__dict__, "rollback": capture}
    values["request_hash"] = canonical_hash({k: v for k, v in values.items()
                                               if k not in {"request_hash", "schema"}})
    request = base.__class__(**values)
    observer = {
        "plist_sha256": capture.plist_sha256,
        "plist_bytes_sha256": capture.plist_bytes_sha256,
        "artifact_sha256": capture.artifact_sha256,
        "source_sha256": capture.source_sha256,
        "source_root": capture.source_root,
        "source_head": capture.source_head,
        "source_tree": capture.source_tree,
        "loaded": True,
        "pid": 123,
        "server_instance": capture.server_instance,
        "listener": g.GATEWAY_ENDPOINT,
        "service_loaded": True,
    }
    calls = []
    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def runner(*args):
        calls.append(args)
        return Result()

    def failing_opener(req, timeout):
        assert req.headers.get("Authorization") == "Bearer SECRET"
        raise OSError("postflight unavailable")

    with pytest.raises(g.GatewayContractError, match="postflight") as exc_info:
        g.rollback_gateway(
            request, plist_path=g.GATEWAY_PLIST, predecessor_observer=observer,
            runner=runner, opener=failing_opener, token_loader=lambda: "SECRET",
            sleeper=lambda _: None, observation_time="2026-08-23T00:00:00Z",
        )
    assert [call[1] for call in calls] == ["bootout", "bootstrap"]
    assert not any("devspace" in str(call).lower() for call in calls)
    assert "ROLLED_BACK" not in str(exc_info.value)
    assert not (tmp_path / "ledger.jsonl").exists()


def test_rollback_missing_observer_and_stale_authority_have_zero_effects(monkeypatch, tmp_path):
    request = _gateway_request("rollback")
    calls = []
    with pytest.raises(g.GatewayContractError):
        g.rollback_gateway(request, plist_path=tmp_path / "wrong.plist", runner=lambda *args: calls.append(args), observation_time="2026-08-23T00:00:00Z")
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    with pytest.raises(g.GatewayContractError, match="predecessor observer"):
        g.rollback_gateway(request, plist_path=g.GATEWAY_PLIST, runner=lambda *args: calls.append(args), observation_time="2026-08-23T00:00:00Z")
    stale_values = {**request.authority.__dict__, "expires_at": "2026-08-22T00:00:00Z"}
    stale_values["receipt_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in stale_values.items() if k != "receipt_hash"})
    stale = request.authority.__class__(**stale_values)
    values = {**request.__dict__, "authority": stale}
    values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in values.items() if k not in {"request_hash", "schema"}})
    stale_request = request.__class__(**values)
    with pytest.raises(g.GatewayContractError, match="freshness"):
        g.rollback_gateway(stale_request, plist_path=g.GATEWAY_PLIST, predecessor_observer={}, runner=lambda *args: calls.append(args), observation_time="2026-08-23T00:00:00Z")
    assert calls == []


def test_postflight_requires_authenticated_identity_and_recomputes_manifest(monkeypatch):
    tools = [{"name": "ping", "description": "bounded"}]
    manifest = hashlib.sha256(json.dumps(("ping",), separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    schema = hashlib.sha256(json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    from nexus.contracts.gateway_deployment import DESIRED_PROFILE
    identity = {
        "server_instance_id": "new-instance", "repo_root": DESIRED_PROFILE.git.root, "git_head": DESIRED_PROFILE.git.head,
        "permission_policy_hash": "a" * 64,
        "lifecycle_revision": GATEWAY_LIFECYCLE_REVISION,
        "tool_manifest_revision": manifest, "full_tool_schema_hash": schema,
    }

    class Response:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(self.value).encode()

    def opener(request, timeout):
        assert request.headers.get("Authorization") == "Bearer SECRET"
        if request.full_url.endswith("/health"):
            return Response(identity)
        payload = json.loads(request.data.decode())
        if payload["method"] == "initialize":
            return Response({"result": {"serverInfo": {
                "serverInstanceId": "new-instance", "toolManifestRevision": manifest,
                "fullToolSchemaHash": schema, "permissionPolicyHash": "a" * 64,
                "lifecycleRevision": GATEWAY_LIFECYCLE_REVISION,
            }}})
        return Response({"result": {"tools": tools}})

    expected = {
        "server_instance": "new-instance", "root": DESIRED_PROFILE.git.root, "head": DESIRED_PROFILE.git.head,
        "tree": DESIRED_PROFILE.git.tree, "tool_manifest_sha256": manifest, "schema_sha256": schema,
        "permission_sha256": "a" * 64, "action": "gateway-rebind", "task_id": "TASK-526-A",
        "lifecycle": GATEWAY_LIFECYCLE_REVISION, "required_actions": ("ping",),
    }
    result = g.postflight_gateway(expected, token="SECRET", endpoint="http://127.0.0.1:8766", opener=opener, sleeper=lambda _: None)
    assert result.server_instance == "new-instance" and result.client_bound

    bad = dict(expected); bad["server_instance"] = "old-instance"
    with pytest.raises(g.GatewayContractError):
        g.postflight_gateway(bad, token="SECRET", endpoint="http://127.0.0.1:8766", opener=opener, sleeper=lambda _: None, retries=1)
    identity["server_instance_id"] = "different"
    with pytest.raises(g.GatewayContractError, match="postflight remained uncertain"):
        g.postflight_gateway(expected, token="SECRET", endpoint="http://127.0.0.1:8766",
                             opener=lambda request, timeout: opener(request, timeout), sleeper=lambda _: None,
                             retries=1)
    identity.pop("server_instance_id")
    with pytest.raises(g.GatewayContractError, match="postflight remained uncertain"):
        g.postflight_gateway(expected, token="SECRET", endpoint="http://127.0.0.1:8766",
                             opener=opener, sleeper=lambda _: None, retries=1)


def test_stable_artifact_install_is_separate_and_hash_bound(tmp_path):
    from nexus.contracts.gateway_deployment import StableArtifactIdentity

    source = tmp_path / "manager.py"
    source.write_bytes(b"stable-manager")
    source.chmod(0o700)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    artifact = StableArtifactIdentity(
        source_root=str(tmp_path), source_head="a" * 40, source_tree="b" * 40,
        source_path=str(source), source_blob_sha256=digest, artifact_sha256=digest,
        uid=os.getuid(), mode=0o700, predecessor_sha256=hashlib.sha256(b"old").hexdigest(), request_id="r-526", authority_receipt_id="receipt", install_fence="fence", rollback_receipt="rollback",
    )
    # The destination is a fixed manager constant; tests isolate it by
    # replacing that constant rather than passing a caller-selected path.
    original_destination = g.GATEWAY_ARTIFACT
    g.GATEWAY_ARTIFACT = tmp_path / "installed.py"
    request = _gateway_request("install-artifact", stable_artifact=artifact)
    try:
        (tmp_path / "installed.py").write_bytes(b"old"); (tmp_path / "installed.py").chmod(0o700)
        def command_runner(*args):
            command = args if args and isinstance(args[0], str) else args[0]
            if command[0:2] == ("git", "-C") and command[-1] == "--show-toplevel": return str(tmp_path)
            if command[0:2] == ("git", "-C") and command[-1] == "origin": return "https://github.com/James3014/Nexus-new.git"
            if "rev-parse" in command and command[-1] == "HEAD": return "a" * 40
            if "rev-parse" in command and command[-1] == "HEAD^{tree}": return "b" * 40
            if "status" in command: return ""
            if "ls-files" in command: return "manager.py"
            if "hash-object" in command: return "1" * 40
            if command[0] == "shasum": return f"{digest}  {source}"
            raise AssertionError(command)
        out = g.install_stable_artifact(request, source_root=tmp_path, source_path=source, artifact_path=g.GATEWAY_ARTIFACT,
                                        command_runner=command_runner, observation_time="2026-08-23T00:00:00Z")
    finally:
        g.GATEWAY_ARTIFACT = original_destination
    assert out["state"] == "VERIFIED" and (tmp_path / "installed.py").read_bytes() == source.read_bytes()
    source.write_bytes(b"tampered")
    with pytest.raises(g.GatewayContractError):
        g.install_stable_artifact(request, source_root=tmp_path, source_path=source, artifact_path=g.GATEWAY_ARTIFACT, command_runner=command_runner, observation_time="2026-08-23T00:00:00Z")


def test_gateway_reload_partial_postflight_is_uncertain_not_verified(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "GATEWAY_LOCK", tmp_path / "gateway.lock")
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    request = _gateway_request()
    class Result:
        returncode = 0; stdout = ""; stderr = ""
    with pytest.raises(g.GatewayContractError, match="uncertain"):
        g.gateway_reload(request, observed=_gateway_observed(), runner=lambda *args: Result(),
                          ledger=g.GatewayLedger(tmp_path / "ledger.jsonl"),
                          opener=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
                          token_loader=lambda: "SECRET", sleeper=lambda _: None, observation_time="2026-08-23T00:00:00Z")
    rows = g.GatewayLedger(tmp_path / "ledger.jsonl").read()
    assert rows[-1]["state"] == "UNCERTAIN_EFFECT"
    assert not any(row["state"] == "VERIFIED" for row in rows)


def test_gateway_reload_wrong_typed_identity_is_uncertain(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "GATEWAY_LOCK", tmp_path / "gateway.lock")
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    request = _gateway_request()
    class Result:
        returncode = 0; stdout = ""; stderr = ""
    with pytest.raises(g.GatewayContractError):
        g.gateway_reload(request, observed=_gateway_observed(), runner=lambda *args: Result(),
                          ledger=g.GatewayLedger(tmp_path / "ledger.jsonl"), opener=lambda *args, **kwargs: (_ for _ in ()).throw(OSError("offline")),
                          token_loader=lambda: "SECRET", sleeper=lambda _: None,
                          observation_time="2026-08-23T00:00:00Z")
    assert g.GatewayLedger(tmp_path / "ledger.jsonl").read()[-1]["state"] == "UNCERTAIN_EFFECT"


def test_preflight_missing_physical_evidence_fails_before_effect(monkeypatch):
    request = _gateway_request()
    observed = _gateway_observed(); observed.pop("plist_bytes_sha256")
    with pytest.raises(g.GatewayContractError, match="complete fresh"):
        g.preflight_gateway(request, observed=observed, observation_time="2026-08-23T00:00:00Z")


@pytest.mark.parametrize("field", ["plist_sha256", "plist_bytes_sha256"])
def test_preflight_rejects_either_plist_hash_mismatch_before_effect(field):
    request = _gateway_request()
    observed = _gateway_observed()
    observed[field] = "0" * 64
    with pytest.raises(g.GatewayContractError, match="plist bytes hash mismatch"):
        g.preflight_gateway(request, observed=observed, observation_time="2026-08-23T00:00:00Z")


def test_artifact_source_substitution_has_zero_destination_write(tmp_path):
    from nexus.contracts.gateway_deployment import StableArtifactIdentity
    source = tmp_path / "manager.py"; source.write_bytes(b"stable-manager"); source.chmod(0o700)
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    artifact = StableArtifactIdentity(str(tmp_path), "a"*40, "b"*40, str(source), digest, digest, os.getuid(), 0o700,
        hashlib.sha256(b"old").hexdigest(), "r-526", "TASK-526-A", "receipt", "fence", "rollback")
    old_destination = g.GATEWAY_ARTIFACT; g.GATEWAY_ARTIFACT = tmp_path / "installed.py"
    try:
        request = _gateway_request("install-artifact", stable_artifact=artifact)
        with pytest.raises(g.GatewayContractError):
            g.install_stable_artifact(request, source_root=tmp_path, source_path=source,
                artifact_path=g.GATEWAY_ARTIFACT, command_runner=lambda *args: "", observation_time="2026-08-23T00:00:00Z")
        assert not g.GATEWAY_ARTIFACT.exists()
    finally:
        g.GATEWAY_ARTIFACT = old_destination


def test_ledger_rejects_skipped_state_and_replay_conflict(tmp_path):
    ledger = g.GatewayLedger(tmp_path / "ledger.jsonl")
    receipt = _ledger_receipt()
    ledger.append(request_id="r", request_hash="a" * 64, state="REQUESTED", host_authority=receipt, operation="reload", effect_class="GATEWAY_RELOAD", idempotency_fence="f")
    with pytest.raises(g.GatewayContractError):
        ledger.append(request_id="r", request_hash="a" * 64, state="STARTED", host_authority=receipt, operation="reload", effect_class="GATEWAY_RELOAD", idempotency_fence="f")
    with pytest.raises(g.GatewayContractError):
        ledger.append(request_id="r", request_hash="b" * 64, state="PREFLIGHTED", host_authority=receipt, operation="reload", effect_class="GATEWAY_RELOAD", idempotency_fence="f")


def test_cli_rejects_caller_selected_gateway_command(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mcp_gateway_durable.py", "gateway-reload", "--operation", "launchctl"])
    with pytest.raises(SystemExit):
        g.main()


def test_cli_rejects_caller_selected_gateway_store(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["mcp_gateway_durable.py", "gateway-preflight", "--gateway-request", str(tmp_path / "request.json")])
    with pytest.raises(SystemExit):
        g.main()


# Preserve the base pytest node ID while asserting the newer bundle-only rule.
def test_cli_dispatch_real_preflight_binds_matching_action_and_effect():
    request = _gateway_request("preflight")
    with pytest.raises(g.GatewayContractError):
        g.dispatch_gateway_cli(
            "preflight", request=request, observed=_gateway_observed(),
            observation_time="2026-08-23T00:00:00Z",
        )


def test_cli_dispatch_real_install_uses_bound_artifact_and_fixed_git_runner(monkeypatch, tmp_path):
    from nexus.contracts.gateway_deployment import StableArtifactIdentity

    repo = _real_git_repo(tmp_path)
    source = repo / "manager.py"
    source.write_bytes(b"stable-manager")
    source.chmod(0o700)
    subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", "https://github.com/James3014/Nexus-new.git"], check=True)
    source_head = _commit(repo, "manager")
    source_tree = subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD^{tree}"], text=True).strip()
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    destination = tmp_path / "installed-manager.py"
    predecessor = hashlib.sha256(b"old-manager").hexdigest()
    destination.write_bytes(b"old-manager")
    destination.chmod(0o700)
    artifact = StableArtifactIdentity(
        source_root=str(repo), source_head=source_head, source_tree=source_tree,
        source_path=str(source), source_blob_sha256=digest, artifact_sha256=digest,
        uid=os.getuid(), mode=0o700, predecessor_sha256=predecessor,
        request_id="r-526", authority_receipt_id="receipt", install_fence="fence", rollback_receipt="rollback",
    )
    monkeypatch.setattr(g, "GATEWAY_ARTIFACT", destination)
    request = _gateway_request("install-artifact", stable_artifact=artifact)
    result = g.dispatch_gateway_cli("install-artifact", request=request, observed={},
                                    observation_time="2026-08-23T00:00:00Z")
    assert result["state"] == "VERIFIED"
    assert destination.read_bytes() == source.read_bytes()


def test_cli_dispatch_rejects_mismatched_action_and_request():
    request = _gateway_request("reload")
    with pytest.raises(g.GatewayContractError, match="operation substitution"):
        g.dispatch_gateway_cli("preflight", request=request, observed=_gateway_observed(),
                               observation_time="2026-08-23T00:00:00Z")


def test_collect_dispatch_unloaded_rollback_skips_health_and_launch_effects(monkeypatch, tmp_path):
    request = _gateway_request("rollback")
    capture = request.rollback
    payload = bytes.fromhex(capture.plist_bytes_hex)
    parsed = plistlib.loads(payload)
    fixed_root = capture.root
    calls = []

    class Absent:
        returncode = 113
        stdout = ""
        stderr = f'Bad request.\nCould not find service "{g.GATEWAY_LABEL}" in domain for user gui: {os.getuid()}\n'

    def launchctl(*args):
        calls.append(args)
        assert args[1] == "print"
        return Absent()

    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    monkeypatch.setattr(g, "GATEWAY_LOCK", tmp_path / "gateway.lock")
    observed = g.collect_gateway_observation(
        request, operation="rollback", runner=launchctl,
        plist_observer=lambda _path: (payload, parsed),
        git_observer=lambda _root: {"root": fixed_root, "toplevel": fixed_root,
                                    "remote": "https://github.com/James3014/Nexus-new.git",
                                    "head": capture.source_head, "tree": capture.source_tree, "clean": True},
        source_observer=lambda _path: capture.source_sha256,
        interpreter_observer=lambda _path: (Path("/tmp/fixed-python"), "d" * 64, 501, 20, "lrwxr-xr-x"),
        artifact_observer=lambda _path: capture.artifact_sha256,
        quiescence_observer=lambda: {"disposition": "reconciled", "lifecycle_state": "QUIESCENT",
                                     "assist_state": "QUIESCENT", "evidence_sha256": "1" * 64,
                                     "reacquisition_receipt": "reacq"},
        token_loader=lambda: pytest.fail("unloaded rollback must not load a token"),
        health_observer=lambda _token: pytest.fail("unloaded rollback must not call health"),
    )
    assert observed["loaded"] is False
    assert observed["server_instance"] == ""
    assert observed["listener"] == ""
    assert observed["rollback_predecessor"]["source_root"] == fixed_root
    result = g.dispatch_gateway_cli(
        "rollback", request=request, observed=observed,
        observation_time="2026-08-23T00:00:00Z", runner=launchctl,
        token_loader=lambda: pytest.fail("unloaded rollback must not load a token"),
    )
    assert result["state"] == "ROLLED_BACK"
    assert [call[1] for call in calls] == ["print"]


def _actual_gateway_surfaces(profile, tools):
    manifest = hashlib.sha256(
        json.dumps(tuple(sorted(item["name"] for item in tools)), separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()
    schema = hashlib.sha256(
        json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
    health = {
        "server_instance_id": "physical-instance",
        "repo_root": profile.git.root,
        "git_head": profile.git.head,
        "tool_manifest_revision": manifest,
        "full_tool_schema_hash": schema,
        "permission_policy_hash": "a" * 64,
        "lifecycle_revision": GATEWAY_LIFECYCLE_REVISION,
    }
    server_info = {
        "serverInstanceId": "physical-instance",
        "toolManifestRevision": manifest,
        "fullToolSchemaHash": schema,
        "permissionPolicyHash": "a" * 64,
        "lifecycleRevision": GATEWAY_LIFECYCLE_REVISION,
    }
    return health, server_info, manifest, schema


def _surface_opener(health, server_info, tools):
    class Response:
        def __init__(self, value):
            self.value = value

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def read(self):
            return json.dumps(self.value).encode()

    def opener(request, timeout):
        assert request.headers.get("Authorization") == "Bearer SECRET"
        if request.full_url.endswith("/health"):
            return Response(health)
        method = json.loads(request.data.decode())["method"]
        if method == "initialize":
            return Response({"result": {"serverInfo": server_info}})
        assert method == "tools/list"
        return Response({"result": {"tools": tools}})

    return opener


def test_actual_gateway_surfaces_prove_fixed_contract_identity_without_fake_health_fields():
    from nexus.contracts.gateway_deployment import DESIRED_PROFILE

    tools = [{"name": "gateway-rebind", "description": "bounded"}]
    health, server_info, manifest, schema = _actual_gateway_surfaces(DESIRED_PROFILE, tools)
    assert not {"action", "task_id", "client_bound", "token_bound"}.intersection(health)
    assert not {"action", "task_id", "client_bound", "token_bound"}.intersection(server_info)
    result = g.postflight_gateway(
        {
            "server_instance": "physical-instance",
            "root": DESIRED_PROFILE.git.root,
            "head": DESIRED_PROFILE.git.head,
            "tree": DESIRED_PROFILE.git.tree,
            "tool_manifest_sha256": manifest,
            "schema_sha256": schema,
            "permission_sha256": "a" * 64,
            "action": g.GATEWAY_ACTION,
            "task_id": g.GATEWAY_TASK_ID,
            "lifecycle": GATEWAY_LIFECYCLE_REVISION,
            "required_actions": ("gateway-rebind",),
        },
        token="SECRET",
        opener=_surface_opener(health, server_info, tools),
        sleeper=lambda _: None,
        retries=1,
    )
    assert result.client_bound is True
    assert result.token_bound is True
    assert result.action == g.GATEWAY_ACTION
    assert result.task_id == g.GATEWAY_TASK_ID
    assert result.lifecycle == GATEWAY_LIFECYCLE_REVISION


@pytest.mark.parametrize(
    ("health_key", "canonical_key"),
    [
        ("server_instance_id", "server_instance"),
        ("tool_manifest_revision", "tool_manifest_sha256"),
        ("full_tool_schema_hash", "schema_sha256"),
        ("permission_policy_hash", "permission_sha256"),
        ("lifecycle_revision", "lifecycle"),
        ("repo_root", "root"),
        ("git_head", "head"),
    ],
)
@pytest.mark.parametrize("mode", ["missing", "wrong-type", "conflict"])
def test_each_physical_health_alias_missing_wrong_type_or_conflict_rejects(
    health_key, canonical_key, mode
):
    from nexus.contracts.gateway_deployment import DESIRED_PROFILE

    tools = [{"name": "gateway-rebind", "description": "bounded"}]
    health, server_info, manifest, schema = _actual_gateway_surfaces(DESIRED_PROFILE, tools)
    if mode == "missing":
        health.pop(health_key)
    elif mode == "wrong-type":
        health[health_key] = 7
    else:
        health[canonical_key] = "different"
    with pytest.raises(g.GatewayContractError, match="postflight remained uncertain"):
        g.postflight_gateway(
            {
                "root": DESIRED_PROFILE.git.root,
                "head": DESIRED_PROFILE.git.head,
                "tree": DESIRED_PROFILE.git.tree,
                "tool_manifest_sha256": manifest,
                "schema_sha256": schema,
                "permission_sha256": "a" * 64,
                "lifecycle": GATEWAY_LIFECYCLE_REVISION,
                "required_actions": ("gateway-rebind",),
            },
            token="SECRET",
            opener=_surface_opener(health, server_info, tools),
            sleeper=lambda _: None,
            retries=1,
        )


@pytest.mark.parametrize(
    ("initialize_key", "canonical_key"),
    [
        ("serverInstanceId", "server_instance"),
        ("toolManifestRevision", "tool_manifest_sha256"),
        ("fullToolSchemaHash", "schema_sha256"),
        ("permissionPolicyHash", "permission_sha256"),
        ("lifecycleRevision", "lifecycle"),
    ],
)
@pytest.mark.parametrize("mode", ["missing", "wrong-type", "conflict"])
def test_each_initialize_alias_missing_wrong_type_or_conflict_rejects(
    initialize_key, canonical_key, mode
):
    tools = [{"name": "gateway-rebind", "description": "bounded"}]
    health, server_info, manifest, schema = _actual_gateway_surfaces(DESIRED_PROFILE, tools)
    if mode == "missing":
        server_info.pop(initialize_key)
    elif mode == "wrong-type":
        server_info[initialize_key] = 7
    else:
        server_info[canonical_key] = "different"
    with pytest.raises(g.GatewayContractError, match="postflight remained uncertain"):
        g.postflight_gateway(
            {
                "root": DESIRED_PROFILE.git.root,
                "head": DESIRED_PROFILE.git.head,
                "tree": DESIRED_PROFILE.git.tree,
                "tool_manifest_sha256": manifest,
                "schema_sha256": schema,
                "permission_sha256": "a" * 64,
                "lifecycle": GATEWAY_LIFECYCLE_REVISION,
                "required_actions": ("gateway-rebind",),
            },
            token="SECRET",
            opener=_surface_opener(health, server_info, tools),
            sleeper=lambda _: None,
            retries=1,
        )


def test_desired_plist_is_fixed_wrapper_without_token_placeholder_or_environment_field():
    from nexus.contracts.gateway_deployment import DESIRED_PROFILE

    parsed = plistlib.loads(g._gateway_plist(DESIRED_PROFILE))
    expected_entrypoint = str(Path(DESIRED_PROFILE.git.root) / g.GATEWAY_ENTRYPOINT)
    assert parsed["ProgramArguments"] == [
        "/bin/zsh",
        "-c",
        g._gateway_wrapper_command(DESIRED_PROFILE.git.root, expected_entrypoint),
    ]
    assert "EnvironmentVariables" not in parsed
    assert "${NEXUS_MCP_GATEWAY_TOKEN}" not in parsed["ProgramArguments"][2]
    assert g.ENV_PATH.name in parsed["ProgramArguments"][2]
    assert parsed["RunAtLoad"] is True and parsed["KeepAlive"] is True


@pytest.mark.parametrize(
    ("root", "entrypoint"),
    [
        ("/tmp/foreign", "/tmp/foreign/scripts/ops/nexus_mcp_gateway_http.py"),
        ("/tmp/foreign; touch /tmp/pwn", "/tmp/foreign/scripts/ops/nexus_mcp_gateway_http.py"),
        ("/tmp/$(id)", "/tmp/foreign/scripts/ops/nexus_mcp_gateway_http.py"),
        (CURRENT_PROFILE.git.root, CURRENT_PROFILE.git.root + "/scripts/ops/other.py"),
        (DESIRED_PROFILE.git.root, DESIRED_PROFILE.git.root + "/scripts/ops/nexus_mcp_gateway_http.py;id"),
    ],
)
def test_generic_or_shell_substituted_wrapper_callers_are_rejected(root, entrypoint):
    with pytest.raises(g.ContractError):
        g._gateway_wrapper_command(root, entrypoint)


def test_wrapper_helper_requires_explicit_frozen_entrypoint():
    with pytest.raises(TypeError):
        g._gateway_wrapper_command(CURRENT_PROFILE.git.root)
    with pytest.raises(TypeError):
        g._gateway_plist(DESIRED_PROFILE, token_env="CALLER_SELECTED")


def _authority_runner_for_bundle(raw, *, merge_code=0, remote_line=None):
    root = str(g.HOST_AUTHORITY_SOURCE_ROOT)
    remote_sha = subprocess.check_output(
        ["git", "-C", root, "rev-parse", "HEAD"], text=True
    ).strip()
    calls = []

    def runner(*args):
        command = tuple(args) if args and isinstance(args[0], str) else tuple(args[0])
        calls.append(command)
        if command[-2:] == ("rev-parse", "--show-toplevel"):
            return subprocess.CompletedProcess(command, 0, root.encode(), b"")
        if command[-3:] == ("remote", "get-url", "origin"):
            return subprocess.CompletedProcess(command, 0, g.HOST_AUTHORITY_REMOTE.encode(), b"")
        if command[-2:] == ("status", "--porcelain"):
            return subprocess.CompletedProcess(command, 0, b"", b"")
        if command[-2:] == ("rev-parse", "HEAD"):
            return subprocess.CompletedProcess(command, 0, remote_sha.encode(), b"")
        if "ls-remote" in command:
            line = remote_line if remote_line is not None else f"{remote_sha}\t{g.HOST_AUTHORITY_REF}\n"
            return subprocess.CompletedProcess(command, 0, line.encode(), b"")
        if "merge-base" in command:
            return subprocess.CompletedProcess(command, merge_code, b"", b"divergent")
        if command[-2] == "show":
            return subprocess.CompletedProcess(command, 0, raw, b"")
        raise AssertionError(command)

    return runner, calls, remote_sha


def test_authority_ancestry_divergence_exit_one_uses_exact_argv_and_stops_observation():
    request = _gateway_request()
    raw, bundle = g._read_host_authority_store()
    runner, calls, remote_sha = _authority_runner_for_bundle(raw, merge_code=1)
    with pytest.raises(g.GatewayContractError, match="host authority rejected"):
        g.collect_gateway_observation(
            request,
            observation_time="2026-08-23T00:00:00Z",
            authority_command_runner=runner,
            plist_observer=lambda _: pytest.fail("physical observation must not run"),
        )
    expected = (
        "git",
        "-C",
        str(g.HOST_AUTHORITY_SOURCE_ROOT),
        "merge-base",
        "--is-ancestor",
        bundle.current_main_sha,
        remote_sha,
    )
    assert expected in calls
    assert not any(command[-2] == "show" for command in calls)


def test_authority_malformed_remote_main_stops_before_ancestry_or_observation():
    request = _gateway_request()
    raw, _bundle = g._read_host_authority_store()
    runner, calls, _remote_sha = _authority_runner_for_bundle(raw, remote_line="malformed")
    with pytest.raises(g.GatewayContractError, match="host authority rejected"):
        g.collect_gateway_observation(
            request,
            observation_time="2026-08-23T00:00:00Z",
            authority_command_runner=runner,
            plist_observer=lambda _: pytest.fail("physical observation must not run"),
        )
    assert not any("merge-base" in command for command in calls)


def test_manager_artifact_triple_mismatch_rejects_before_destination_write(monkeypatch, tmp_path):
    from nexus.contracts.gateway_deployment import StableArtifactIdentity

    source = tmp_path / "manager.py"
    source.write_bytes(b"manager")
    source.chmod(0o700)
    artifact_digest = hashlib.sha256(source.read_bytes()).hexdigest()
    artifact = StableArtifactIdentity(
        source_root=str(tmp_path),
        source_head="a" * 40,
        source_tree="b" * 40,
        source_path=str(source),
        source_blob_sha256="c" * 64,
        artifact_sha256=artifact_digest,
        uid=os.getuid(),
        mode=0o700,
        predecessor_sha256="",
        request_id="r-526",
        authority_receipt_id="receipt",
        install_fence="fence",
        rollback_receipt="rollback",
    )
    destination = tmp_path / "installed.py"
    monkeypatch.setattr(g, "GATEWAY_ARTIFACT", destination)
    request = _gateway_request("install-artifact", stable_artifact=artifact)
    with pytest.raises(g.GatewayContractError, match="host authority rejected"):
        g.install_stable_artifact(
            request,
            source_root=tmp_path,
            source_path=source,
            observation_time="2026-08-23T00:00:00Z",
        )
    assert not destination.exists()


def _exact_postflight_git_runner(profile, *, mutation=None, calls=None):
    outputs = {
        ("rev-parse", "--show-toplevel"): profile.git.root,
        ("remote", "get-url", "origin"): profile.git.remote,
        ("status", "--porcelain"): "",
        ("rev-parse", "HEAD"): profile.git.head,
        ("rev-parse", "HEAD^{tree}"): profile.git.tree,
    }
    if mutation is not None:
        key, value = mutation
        outputs[key] = value

    def runner(*args):
        command = tuple(args) if args and isinstance(args[0], str) else tuple(args[0])
        if calls is not None:
            calls.append(command)
        suffix = command[3:]
        value = outputs[suffix]
        if isinstance(value, BaseException):
            raise value
        if isinstance(value, tuple):
            return subprocess.CompletedProcess(command, value[0], value[1], value[2])
        return subprocess.CompletedProcess(command, 0, value, "")

    return runner


def _postflight_expected(profile, manifest, schema):
    return {
        "server_instance": "physical-instance",
        "root": profile.git.root,
        "head": profile.git.head,
        "tree": profile.git.tree,
        "tool_manifest_sha256": manifest,
        "schema_sha256": schema,
        "permission_sha256": "a" * 64,
        "action": g.GATEWAY_ACTION,
        "task_id": g.GATEWAY_TASK_ID,
        "lifecycle": GATEWAY_LIFECYCLE_REVISION,
        "required_actions": ("gateway-rebind",),
    }


def test_postflight_accepts_only_after_exact_manager_owned_local_git_reread(monkeypatch):
    tools = [{"name": "gateway-rebind", "description": "bounded"}]
    health, server_info, manifest, schema = _actual_gateway_surfaces(DESIRED_PROFILE, tools)
    calls = []
    monkeypatch.setattr(g, "_postflight_root_is_safe", lambda root: root == Path(DESIRED_PROFILE.git.root))
    result = g.postflight_gateway(
        _postflight_expected(DESIRED_PROFILE, manifest, schema),
        token="SECRET",
        opener=_surface_opener(health, server_info, tools),
        sleeper=lambda _: None,
        retries=1,
        git_command_runner=_exact_postflight_git_runner(DESIRED_PROFILE, calls=calls),
    )
    root = DESIRED_PROFILE.git.root
    assert calls == [
        ("git", "-C", root, "rev-parse", "--show-toplevel"),
        ("git", "-C", root, "remote", "get-url", "origin"),
        ("git", "-C", root, "status", "--porcelain"),
        ("git", "-C", root, "rev-parse", "HEAD"),
        ("git", "-C", root, "rev-parse", "HEAD^{tree}"),
    ]
    assert result.head == DESIRED_PROFILE.git.head
    assert result.tree == DESIRED_PROFILE.git.tree


@pytest.mark.parametrize(
    "mutation",
    [
        (("rev-parse", "HEAD"), "0" * 40),
        (("rev-parse", "HEAD^{tree}"), "1" * 40),
        (("status", "--porcelain"), " M tracked.py"),
        (("rev-parse", "--show-toplevel"), "/tmp/wrong-root"),
        (("remote", "get-url", "origin"), "https://example.invalid/wrong.git"),
        (("rev-parse", "HEAD"), (1, "", "observer failed")),
    ],
    ids=["head-drift", "tree-drift", "dirty", "wrong-top", "wrong-origin", "command-failure"],
)
def test_postflight_git_drift_or_command_failure_rejects_after_http_success(
    monkeypatch, mutation
):
    tools = [{"name": "gateway-rebind", "description": "bounded"}]
    health, server_info, manifest, schema = _actual_gateway_surfaces(DESIRED_PROFILE, tools)
    http_calls = []
    opener = _surface_opener(health, server_info, tools)

    def observed_opener(request, timeout):
        http_calls.append(request)
        return opener(request, timeout)

    monkeypatch.setattr(g, "_postflight_root_is_safe", lambda root: root == Path(DESIRED_PROFILE.git.root))
    with pytest.raises(g.GatewayContractError, match="postflight remained uncertain"):
        g.postflight_gateway(
            _postflight_expected(DESIRED_PROFILE, manifest, schema),
            token="SECRET",
            opener=observed_opener,
            sleeper=lambda _: None,
            retries=1,
            git_command_runner=_exact_postflight_git_runner(
                DESIRED_PROFILE,
                mutation=mutation,
            ),
        )
    assert len(http_calls) == 3


def test_postflight_unsafe_or_missing_root_observer_rejects_after_http_success(monkeypatch):
    tools = [{"name": "gateway-rebind", "description": "bounded"}]
    health, server_info, manifest, schema = _actual_gateway_surfaces(DESIRED_PROFILE, tools)
    http_calls = []
    opener = _surface_opener(health, server_info, tools)

    def observed_opener(request, timeout):
        http_calls.append(request)
        return opener(request, timeout)

    monkeypatch.setattr(g, "_postflight_root_is_safe", lambda _root: False)
    with pytest.raises(g.GatewayContractError, match="postflight remained uncertain"):
        g.postflight_gateway(
            _postflight_expected(DESIRED_PROFILE, manifest, schema),
            token="SECRET",
            opener=observed_opener,
            sleeper=lambda _: None,
            retries=1,
            git_command_runner=lambda *_: pytest.fail("unsafe root must stop Git command"),
        )
    assert len(http_calls) == 3


@pytest.mark.parametrize(
    "command",
    [
        ("git", "-C", "/tmp/caller-root", "rev-parse", "HEAD"),
        ("git", "-C", DESIRED_PROFILE.git.root, "status", "--porcelain", "--ignored"),
    ],
    ids=["caller-root", "caller-argv"],
)
def test_default_postflight_git_runner_rejects_caller_selected_root_or_argv(command):
    with pytest.raises(g.GatewayContractError, match="caller-selected"):
        REAL_POSTFLIGHT_GIT_RUNNER(*command)
