# ruff: noqa: E701, E702, E731
import hashlib
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.ops import mcp_gateway_durable as g

HASH = hashlib.sha256(b"identity").hexdigest()

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
        AuthorityReceipt,
        EffectClass,
        GatewayDeploymentRequest,
        IdentityEvidence,
        PostflightIdentity,
        QuiescenceEvidence,
        RollbackCapture,
    )

    payload = plistlib.dumps({"Label": g.GATEWAY_LABEL, "ProgramArguments": ["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", CURRENT_PROFILE.git.root + "/scripts/ops/nexus_mcp_gateway_http.py"], "WorkingDirectory": CURRENT_PROFILE.git.root, "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log", "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log", "EnvironmentVariables": {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}}, fmt=plistlib.FMT_XML)
    rollback = RollbackCapture(
        hashlib.sha256(payload).hexdigest(), hashlib.sha256(payload).hexdigest(), payload.hex(),
        "b" * 64, "c" * 64, False, server_instance="old", source_root=CURRENT_PROFILE.git.root,
        source_head=CURRENT_PROFILE.git.head, source_tree=CURRENT_PROFILE.git.tree, root=CURRENT_PROFILE.git.root,
        program_arguments_hash=__import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", CURRENT_PROFILE.git.root + "/scripts/ops/nexus_mcp_gateway_http.py"]),
        environment_hash=__import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}),
    )
    effect = {"preflight": EffectClass.PREFLIGHT, "reload": EffectClass.GATEWAY_RELOAD,
              "install-artifact": EffectClass.INSTALL_ARTIFACT, "rollback": EffectClass.GATEWAY_ROLLBACK}[operation]
    values = {
        "request_id": "r-526", "idempotency_fence": "f-526", "operation": operation,
        "authority": AuthorityReceipt("owner", "receipt", issued_at="2026-08-22T00:00:00Z", expires_at="2026-08-24T00:00:00Z", request_id="r-526"),
        "current": CURRENT_PROFILE, "desired": DESIRED_PROFILE,
        "current_identity": IdentityEvidence(plist_sha256=hashlib.sha256(payload).hexdigest(), plist_bytes_sha256=hashlib.sha256(payload).hexdigest(), pid=123, server_instance="old", root=CURRENT_PROFILE.git.root, head=CURRENT_PROFILE.git.head, tree=CURRENT_PROFILE.git.tree, source_sha256="b"*64, tool_manifest_sha256="c"*64, schema_sha256="d"*64, permission_sha256="e"*64, action="gateway-rebind", task_id="TASK-526-A", lifecycle="QUIESCENT", loaded=True, client_bound=True), "rollback": rollback,
        "quiescence": QuiescenceEvidence("reconciled", "QUIESCENT", "QUIESCENT", "1"*64, (), "reacq"), "postflight": PostflightIdentity("new", DESIRED_PROFILE.git.root, DESIRED_PROFILE.git.head, DESIRED_PROFILE.git.tree, "f"*64, "a"*64, "b"*64, "gateway-rebind", "TASK-526-A", "QUIESCENT", True, ("gateway-rebind",), ("gateway-rebind",), True),
        "effect_class": effect,
        "stable_artifact": stable_artifact,
    }
    receipt = values["authority"]
    values["authority"] = AuthorityReceipt(**{**receipt.__dict__, "receipt_hash": __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in receipt.__dict__.items() if k != "receipt_hash"})})
    if stable_artifact is not None:
        values["stable_artifact"] = stable_artifact
    values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(values)
    return GatewayDeploymentRequest(**values)


def _gateway_observed():
    predecessor_payload = plistlib.dumps({"Label": g.GATEWAY_LABEL, "ProgramArguments": ["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe/scripts/ops/nexus_mcp_gateway_http.py"], "WorkingDirectory": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe", "StandardOutPath": "/Users/jameschen/Library/Logs/Nexus/gateway.log", "StandardErrorPath": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log", "EnvironmentVariables": {"NEXUS_MCP_GATEWAY_TOKEN": "${NEXUS_MCP_GATEWAY_TOKEN}"}}, fmt=plistlib.FMT_XML)
    predecessor_hash = hashlib.sha256(predecessor_payload).hexdigest()
    return {
        "root": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "toplevel": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "remote": "https://github.com/James3014/Nexus-new.git",
        "head": "67521fe91e990f4e140642984c743dd50a408e84",
        "tree": "f6d6c2bf0912ff4a63d3c10a089910f95eab3c12",
        "entrypoint": "scripts/ops/nexus_mcp_gateway_http.py",
        "entrypoint_sha256": "8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1",
        "clean": True, "interpreter_path": "/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", "interpreter_resolved_path": "/Users/jameschen/.local/share/uv/python/cpython-3.14.0-macos-aarch64-none/bin/python3.14", "interpreter_sha256": "c89af0b037c601180919ca5fd8a936bd2568cbb4976f91a208c10f54c17a1b78", "interpreter_uid": 501, "interpreter_gid": 20, "interpreter_mode": "lrwxr-xr-x", "trust_class": "ROLLBACK_ONLY_OBSERVED_CURRENT", "repository": "James3014/Nexus-new", "stdout": "/Users/jameschen/Library/Logs/Nexus/gateway.log", "stderr": "/Users/jameschen/Library/Logs/Nexus/gateway.err.log", "label": g.GATEWAY_LABEL, "plist": "/Users/jameschen/Library/LaunchAgents/com.nexus.mcp.gateway.direct.plist", "endpoint": g.GATEWAY_ENDPOINT,
        "plist_sha256": predecessor_hash, "plist_bytes_sha256": predecessor_hash, "plist_bytes_hex": predecessor_payload.hex(), "loaded": True, "pid": 123, "server_instance": "old", "source_sha256": "b"*64, "tool_manifest_sha256": "c"*64, "schema_sha256": "d"*64, "permission_sha256": "e"*64, "action": "gateway-rebind", "task_id": "TASK-526-A", "lifecycle": "QUIESCENT", "stable_artifact": {"artifact_sha256": "f"*64}, "rollback_predecessor": {"plist_sha256": predecessor_hash, "artifact_sha256": "b"*64, "source_sha256": "c"*64}, "listener": g.GATEWAY_ENDPOINT, "services": [g.GATEWAY_LABEL],
        "quiescence": {"disposition": "reconciled", "lifecycle_state": "QUIESCENT", "assist_state": "QUIESCENT", "evidence_sha256": "1"*64, "reacquisition_receipt": "reacq"},
    }


def test_gateway_preflight_requires_exact_current_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    request = _gateway_request()
    assert g.preflight_gateway(request, observed=_gateway_observed(), observation_time="2026-08-23T00:00:00Z")["state"] == "PREFLIGHTED"
    bad = _gateway_observed(); bad["head"] = "0" * 40
    with pytest.raises(g.GatewayContractError):
        g.preflight_gateway(request, observed=bad, observation_time="2026-08-23T00:00:00Z")


def test_gateway_ledger_chain_tamper_and_cas_fail_closed(tmp_path):
    ledger = g.GatewayLedger(tmp_path / "ledger.jsonl")
    first = ledger.append(request_id="r", request_hash="a" * 64, state="REQUESTED")
    with pytest.raises(g.GatewayContractError):
        ledger.append(request_id="r2", request_hash="b" * 64, state="REQUESTED", expected_tail="0" * 64)
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
        manifest, schema, "b" * 64, "gateway-rebind", "TASK-526-A", "QUIESCENT", True,
        ("gateway-rebind",), ("gateway-rebind",), True)
    values = {**request.__dict__, "postflight": post}
    values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash({k: v for k, v in values.items() if k not in {"request_hash", "schema"}})
    request = request.__class__(**values)
    identity = {"server_instance": "new", "repo_root": request.desired.git.root, "git_head": request.desired.git.head, "git_tree": request.desired.git.tree,
                "permission_policy_hash": "b" * 64, "action": "gateway-rebind", "task_id": "TASK-526-A", "lifecycle": "QUIESCENT",
                "tool_manifest_revision": manifest, "full_tool_schema_hash": schema, "client_bound": True, "token_bound": True}
    class Response:
        def __init__(self, value): self.value = value
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self): return json.dumps(self.value).encode()
    def opener(req, timeout):
        if req.full_url.endswith("/health"): return Response(identity)
        body = json.loads(req.data.decode())
        return Response({"result": {"serverInfo": identity}} if body["method"] == "initialize" else {"result": {"tools": tools}})
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
        "server_instance": "new-instance", "repo_root": DESIRED_PROFILE.git.root, "git_head": DESIRED_PROFILE.git.head,
        "git_tree": DESIRED_PROFILE.git.tree, "permission_policy_hash": "a" * 64,
        "action": "gateway-rebind", "task_id": "TASK-526-A", "lifecycle": "QUIESCENT",
        "tool_manifest_revision": manifest, "full_tool_schema_hash": schema, "client_bound": True, "token_bound": True,
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
            return Response({"result": {"serverInfo": identity}})
        return Response({"result": {"tools": tools}})

    expected = {
        "server_instance": "new-instance", "root": DESIRED_PROFILE.git.root, "head": DESIRED_PROFILE.git.head,
        "tree": DESIRED_PROFILE.git.tree, "tool_manifest_sha256": manifest, "schema_sha256": schema,
        "permission_sha256": "a" * 64, "action": "gateway-rebind", "task_id": "TASK-526-A",
        "lifecycle": "QUIESCENT", "required_actions": ("ping",),
    }
    result = g.postflight_gateway(expected, token="SECRET", endpoint="http://127.0.0.1:8766", opener=opener, sleeper=lambda _: None)
    assert result.server_instance == "new-instance" and result.client_bound

    bad = dict(expected); bad["server_instance"] = "old-instance"
    with pytest.raises(g.GatewayContractError):
        g.postflight_gateway(bad, token="SECRET", endpoint="http://127.0.0.1:8766", opener=opener, sleeper=lambda _: None, retries=1)


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
        (tmp_path / "installed.py").write_bytes(b"old"); (tmp_path / "installed.py").chmod(0o600)
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
    ledger.append(request_id="r", request_hash="a" * 64, state="REQUESTED")
    with pytest.raises(g.GatewayContractError):
        ledger.append(request_id="r", request_hash="a" * 64, state="STARTED")
    with pytest.raises(g.GatewayContractError):
        ledger.append(request_id="r", request_hash="b" * 64, state="PREFLIGHTED")


def test_cli_rejects_caller_selected_gateway_command(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["mcp_gateway_durable.py", "gateway-reload", "--operation", "launchctl"])
    with pytest.raises(SystemExit):
        g.main()


def test_cli_rejects_caller_selected_gateway_store(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["mcp_gateway_durable.py", "gateway-preflight", "--gateway-request", str(tmp_path / "request.json")])
    with pytest.raises(SystemExit):
        g.main()


def test_cli_dispatch_real_preflight_binds_matching_action_and_effect():
    request = _gateway_request("preflight")
    result = g.dispatch_gateway_cli("preflight", request=request, observed=_gateway_observed(),
                                    observation_time="2026-08-23T00:00:00Z")
    assert result["state"] == "PREFLIGHTED"
    assert result["request_hash"] == request.request_hash


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
