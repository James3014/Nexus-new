import json
import os, plistlib, hashlib, sys
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
    monkeypatch.setattr(sys, "argv", ["mcp_gateway_durable.py", "serve-devspace", "--expected-head", "head",
                                       "--devspace-root", str(expected_root), "--node-path", str(expected_node),
                                       "--devspace-hash", HASH])
    assert g.main() == 0
    assert seen == {"kind": "devspace", "expected_head": "head", "devspace_hash": HASH,
                    "devspace_root": expected_root, "node_path": expected_node}

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
        g.serve("devspace", root=tmp_path, expected_head=head, devspace_hash=pin,
                devspace_root=tmp_path, node_path=g.NODE_PATH, execve=lambda *args: None)

@pytest.mark.parametrize("kwargs", [{"dirty":" M x"}, {"branch":"wrong"}])
def test_gate_fail_closed(monkeypatch, tmp_path, kwargs):
    setup(monkeypatch, tmp_path, **kwargs)
    with pytest.raises(g.GateError): g.manage("preflight", root=tmp_path, devspace_hash=HASH)

def test_head_and_hash_required(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path, head="actual")
    with pytest.raises(g.GateError): g.manage("preflight", root=tmp_path, expected_head="expected", devspace_hash=HASH)
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
    g.serve("gateway", root=tmp_path, expected_head=head, execve=lambda *a: seen.update(argv=a[1], env=a[2]))
    assert seen["argv"][0].endswith(".venv/bin/python"); assert "SECRET" not in " ".join(seen["argv"])
    assert seen["env"]["NEXUS_CANONICAL_SOURCE_ROOT"] == str(tmp_path if False else g.CANONICAL_ROOT)

def test_serve_devspace_hash_and_token_mapping(monkeypatch, tmp_path):
    head = setup(monkeypatch, tmp_path); (tmp_path / "generated/build-identity.json").write_text("identity"); node = tmp_path / "node"; node.write_text("x"); node.chmod(0o755)
    pin = hashlib.sha256(b"identity").hexdigest(); seen = {}; g.serve("devspace", root=tmp_path, expected_head=head, devspace_hash=pin, devspace_root=tmp_path, node_path=node, execve=lambda *a: seen.update(argv=a[1], env=a[2]))
    assert seen["argv"][-1] == "serve"; assert seen["env"]["NEXUS_GATEWAY_PROXY_TOKEN"] == "SECRET"
