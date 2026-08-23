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
        QuiescenceEvidence,
        RollbackCapture,
    )

    payload = b"<plist><dict><key>Label</key><string>com.nexus.mcp.gateway.direct</string></dict></plist>"
    rollback = RollbackCapture(
        hashlib.sha256(payload).hexdigest(), hashlib.sha256(payload).hexdigest(), payload.hex(),
        "b" * 64, "c" * 64, False,
    )
    effect = {"reload": EffectClass.GATEWAY_RELOAD, "install-artifact": EffectClass.INSTALL_ARTIFACT}[operation]
    values = {
        "request_id": "r-526", "idempotency_fence": "f-526", "operation": operation,
        "authority": AuthorityReceipt("owner", "receipt", request_id="r-526"),
        "current": CURRENT_PROFILE, "desired": DESIRED_PROFILE,
        "current_identity": IdentityEvidence(), "rollback": rollback,
        "quiescence": QuiescenceEvidence("reconciled"), "postflight": {"server_instance": "new"},
        "effect_class": effect,
    }
    if stable_artifact is not None:
        values["stable_artifact"] = stable_artifact
    values["request_hash"] = __import__("nexus.contracts.gateway_deployment", fromlist=["canonical_hash"]).canonical_hash(values)
    return GatewayDeploymentRequest(**values)


def _gateway_observed():
    return {
        "root": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "toplevel": "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe",
        "remote": "https://github.com/James3014/Nexus-new.git",
        "head": "67521fe91e990f4e140642984c743dd50a408e84",
        "tree": "f6d6c2bf0912ff4a63d3c10a089910f95eab3c12",
        "entrypoint": "scripts/ops/nexus_mcp_gateway_http.py",
        "entrypoint_sha256": "8f5fddd5c7761574da8566b5511e9107651a04687a6f656c05d5b435e9a530b1",
        "label": g.GATEWAY_LABEL, "plist": str(g.GATEWAY_PLIST), "endpoint": g.GATEWAY_ENDPOINT,
        "quiescence": {"disposition": "reconciled"},
    }


def test_gateway_preflight_requires_exact_current_identity(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    request = _gateway_request()
    assert g.preflight_gateway(request, observed=_gateway_observed())["state"] == "PREFLIGHTED"
    bad = _gateway_observed(); bad["head"] = "0" * 40
    with pytest.raises(g.GatewayContractError):
        g.preflight_gateway(request, observed=bad)


def test_gateway_ledger_chain_tamper_and_cas_fail_closed(tmp_path):
    ledger = g.GatewayLedger(tmp_path / "ledger.jsonl")
    first = ledger.append(request_id="r", request_hash="a" * 64, state="STARTED")
    with pytest.raises(g.GatewayContractError):
        ledger.append(request_id="r2", request_hash="b" * 64, state="SERVICE_OBSERVED", expected_tail="0" * 64)
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

    result = g.gateway_reload(
        request, observed=_gateway_observed(), runner=runner,
        plist_path=g.GATEWAY_PLIST, ledger=g.GatewayLedger(tmp_path / "ledger.jsonl"),
        postflight=lambda: {"server_instance": "new"},
    )
    assert result["state"] == "VERIFIED"
    assert all(g.GATEWAY_LABEL in " ".join(map(str, call)) or "gateway.plist" in " ".join(map(str, call)) for call in calls)
    assert not any("devspace" in str(call).lower() for call in calls)


def test_rollback_rejects_altered_plist_and_restores_unloaded_predecessor(monkeypatch, tmp_path):
    from nexus.contracts.gateway_deployment import RollbackCapture

    payload = plistlib.dumps({
        "Label": g.GATEWAY_LABEL,
        "ProgramArguments": ["/Users/jameschen/Workspace/Nexus-new/.venv/bin/python", "/Users/jameschen/Workspace/.devspace-chatgpt/worktrees/Nexus-new-482a79fe/scripts/ops/nexus_mcp_gateway_http.py"],
    }, fmt=plistlib.FMT_XML)
    capture = RollbackCapture(hashlib.sha256(payload).hexdigest(), hashlib.sha256(payload).hexdigest(), payload.hex(), "b" * 64, "c" * 64, False)
    monkeypatch.setattr(g, "GATEWAY_LOCK", tmp_path / "rollback.lock")
    monkeypatch.setattr(g, "GATEWAY_PLIST", tmp_path / "gateway.plist")
    out = g.rollback_gateway(capture, plist_path=g.GATEWAY_PLIST, runner=lambda *args: pytest.fail("unloaded rollback must not bootstrap"))
    assert out["state"] == "ROLLED_BACK"
    tampered = RollbackCapture("0" * 64, capture.plist_bytes_sha256, capture.plist_bytes_hex, capture.artifact_sha256, capture.source_sha256, False)
    with pytest.raises(g.GatewayContractError):
        g.rollback_gateway(tampered, plist_path=g.GATEWAY_PLIST)


def test_postflight_requires_authenticated_identity_and_recomputes_manifest(monkeypatch):
    tools = [{"name": "ping", "description": "bounded"}]
    manifest = hashlib.sha256(json.dumps(("ping",), separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    schema = hashlib.sha256(json.dumps(tools, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
    identity = {
        "server_instance": "new-instance", "repo_root": "desired-root", "git_head": "h" * 40,
        "git_tree": "t" * 40, "permission_policy_hash": "p" * 64,
        "action": "gateway-rebind", "task_id": "TASK-526-A", "lifecycle": "QUIESCENT",
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
            return Response({"result": {"serverInfo": identity}})
        return Response({"result": {"tools": tools}})

    expected = {
        "server_instance": "new-instance", "root": "desired-root", "head": "h" * 40,
        "tree": "t" * 40, "tool_manifest_sha256": manifest, "schema_sha256": schema,
        "permission_sha256": "p" * 64, "action": "gateway-rebind", "task_id": "TASK-526-A",
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
    digest = hashlib.sha256(source.read_bytes()).hexdigest()
    artifact = StableArtifactIdentity(
        source_root=str(tmp_path), source_head="a" * 40, source_tree="b" * 40,
        source_path=str(source), source_blob_sha256=digest, artifact_sha256=digest,
        uid=os.getuid(), mode=0o700, request_id="r-526",
    )
    # The destination is a fixed manager constant; tests isolate it by
    # replacing that constant rather than passing a caller-selected path.
    original_destination = g.GATEWAY_ARTIFACT
    g.GATEWAY_ARTIFACT = tmp_path / "installed.py"
    request = _gateway_request("install-artifact", stable_artifact=artifact)
    try:
        out = g.install_stable_artifact(request, source_root=tmp_path, source_path=source, artifact_path=g.GATEWAY_ARTIFACT)
    finally:
        g.GATEWAY_ARTIFACT = original_destination
    assert out["state"] == "VERIFIED" and (tmp_path / "installed.py").read_bytes() == source.read_bytes()
    source.write_bytes(b"tampered")
    with pytest.raises(g.GatewayContractError):
        g.install_stable_artifact(request, source_root=tmp_path, source_path=source, artifact_path=tmp_path / "installed-2.py")
