# ruff: noqa: E701, E702, E731
import fcntl
import hashlib
import json
import multiprocessing
import os
import plistlib
import shutil
import stat
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

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
REAL_R1_IMPORT_BUNDLE = g._r1_import_bundle
REAL_OS_LSTAT = os.lstat


def _r1b2_portable_import_bundle(bundle, heads):
    from nexus.contracts.gateway_deployment import BareStoreEvidence, InterpreterIdentity

    observed = REAL_R1_IMPORT_BUNDLE(bundle, heads)
    fixed = InterpreterIdentity()
    return BareStoreEvidence(
        **{
            **observed.__dict__,
            "owner_uid": fixed.uid,
            "owner_gid": fixed.gid,
        }
    )


def _r1b2_portable_lstat(path, *, dir_fd=None):
    from nexus.contracts.gateway_deployment import InterpreterIdentity

    observed = (
        REAL_OS_LSTAT(path)
        if dir_fd is None
        else REAL_OS_LSTAT(path, dir_fd=dir_fd)
    )
    if dir_fd is not None:
        return observed
    candidate = Path(path)
    deployments = Path(g.GATEWAY_DEPLOYMENTS_ROOT)
    if (
        candidate.name == Path(g.GATEWAY_ENTRYPOINT).name
        and deployments in candidate.parents
    ):
        values = list(observed)
        fixed = InterpreterIdentity()
        values[4] = fixed.uid
        values[5] = fixed.gid
        return os.stat_result(values)
    return observed

@pytest.fixture(autouse=True)
def _isolated_host_authority_store(monkeypatch, tmp_path):
    monkeypatch.setattr(g, "HOST_UID", os.getuid())
    monkeypatch.setattr(g, "HOST_AUTHORITY_UID", os.getuid())
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


def test_r1_stage_is_content_addressed_and_missing_rollback_has_zero_effect(monkeypatch, tmp_path):
    # R1-B removes the public one-file staging surface entirely.
    assert not hasattr(g, "stage_deployment")
    with pytest.raises(g.GatewayContractError, match="R1 recovery request rejected"):
        g.gateway_recover(request=None)


def test_r1_recovery_rejects_caller_selected_effect_surface():
    import inspect
    parameters = inspect.signature(g.gateway_recover).parameters
    stage_parameters = inspect.signature(g.stage_verified_git_store).parameters
    assert "state_root" not in parameters
    assert "desired_source" not in parameters
    assert "predecessor_source" not in parameters
    assert tuple(stage_parameters) == ("request", "receipt")
    assert g.GATEWAY_DEPLOYMENTS_ROOT == g.GATEWAY_STATE_ROOT / "deployments"


def test_r1b1_staging_does_not_accept_caller_selected_git_refs():
    import inspect
    parameters = inspect.signature(g.stage_verified_git_store).parameters
    assert tuple(parameters) == ("request", "receipt")


def _r1b1_fixture(
    tmp_path, monkeypatch, *, identity_seed=None, gitlink=False,
    gitlink_path="nested-repository",
):
    from nexus.contracts.gateway_deployment import (
        RECOVERY_CARD_PATH,
        RECOVERY_CARD_SHA256,
        SOURCE_BASE_MERGE,
        SOURCE_BASE_TREE,
        EffectClass,
        GatewayRecoveryRequest,
        InterpreterIdentity,
        RecoveryAuthorityReceipt,
        RecoveryEntrypointIdentity,
        RecoverySourceSet,
        canonical_hash,
        derive_deployment_manifest,
    )

    seed = identity_seed or hashlib.sha256(str(tmp_path).encode()).hexdigest()[:12]
    monkeypatch.setattr(g, "INTERPRETER", sys.executable)
    monkeypatch.setattr(
        g,
        "_r1_interpreter_identity",
        lambda: InterpreterIdentity(),
    )
    monkeypatch.setattr(
        g,
        "_r1_import_bundle",
        _r1b2_portable_import_bundle,
    )
    monkeypatch.setattr(g.os, "lstat", _r1b2_portable_lstat)

    mirror = tmp_path / "authority"
    subprocess.run(["git", "init", "-q", "-b", "main", str(mirror)], check=True)
    subprocess.run(["git", "-C", str(mirror), "config", "user.email", "b1@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(mirror), "config", "user.name", "b1"], check=True)
    subprocess.run(["git", "-C", str(mirror), "remote", "add", "origin", str(mirror)], check=True)
    entrypoint = mirror / "scripts/ops/nexus_mcp_gateway_http.py"
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text(f"ROLE = 'base'\nSEED = '{seed}'\n")
    entrypoint.chmod(0o644)
    package = mirror / "nexus/orchestrator"
    package.mkdir(parents=True)
    (mirror / "nexus/__init__.py").write_text("")
    (package / "__init__.py").write_text("")
    tool_names = (f"tool-{seed}-a", f"tool-{seed}-b")
    tool_manifest = hashlib.sha256(
        json.dumps(tuple(sorted(tool_names)), separators=(",", ":")).encode()
    ).hexdigest()
    schema_hash = hashlib.sha256(f"schema-{seed}".encode()).hexdigest()
    permission_hash = hashlib.sha256(f"permission-{seed}".encode()).hexdigest()
    (package / "unified_mcp_gateway.py").write_text(
        "PUBLIC_TOOL_NAMES = " + repr(tool_names) + "\n"
        + f"TOOL_MANIFEST_REVISION = '{tool_manifest}'\n"
        + f"FULL_TOOL_SCHEMA_HASH = '{schema_hash}'\n"
        + f"PERMISSION_POLICY_HASH = '{permission_hash}'\n"
        + "LIFECYCLE_REVISION = 'nexus.lifecycle.gateway.v2'\n"
    )
    subprocess.run(["git", "-C", str(mirror), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(mirror), "commit", "-q", "-m", "b1-base"], check=True)
    base = subprocess.check_output(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(["git", "-C", str(mirror), "switch", "-q", "-c", "predecessor-side"], check=True)
    entrypoint.write_text(f"ROLE = 'predecessor'\nSEED = '{seed}'\n")
    subprocess.run(["git", "-C", str(mirror), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(mirror), "commit", "-q", "-m", "b1-predecessor"], check=True)
    predecessor = subprocess.check_output(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"], text=True
    ).strip()
    subprocess.run(
        ["git", "-C", str(mirror), "update-ref", "refs/nexus-r1/predecessor-artifact", predecessor],
        check=True,
    )
    subprocess.run(["git", "-C", str(mirror), "switch", "-q", "main"], check=True)
    subprocess.run(["git", "-C", str(mirror), "reset", "--hard", "-q", base], check=True)
    entrypoint.write_text(f"ROLE = 'desired'\nSEED = '{seed}'\n")
    subprocess.run(["git", "-C", str(mirror), "add", "-A"], check=True)
    if gitlink:
        subprocess.run(
            [
                "git", "-C", str(mirror), "update-index", "--add", "--cacheinfo",
                f"160000,{predecessor},{gitlink_path}",
            ],
            check=True,
        )
    subprocess.run(["git", "-C", str(mirror), "commit", "-q", "-m", "b1-desired"], check=True)
    desired = subprocess.check_output(["git", "-C", str(mirror), "rev-parse", "HEAD"], text=True).strip()
    entrypoint.write_text(f"ROLE = 'accepted'\nSEED = '{seed}'\n")
    subprocess.run(["git", "-C", str(mirror), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(mirror), "commit", "-q", "-m", "b1-accepted"], check=True)
    accepted = subprocess.check_output(
        ["git", "-C", str(mirror), "rev-parse", "HEAD"], text=True
    ).strip()

    monkeypatch.setattr(g, "HOST_AUTHORITY_SOURCE_ROOT", mirror)
    monkeypatch.setattr(g, "HOST_AUTHORITY_REMOTE", str(mirror))
    monkeypatch.setattr(g, "HOST_AUTHORITY_UID", os.getuid())
    monkeypatch.setattr(g, "HOST_UID", os.getuid())
    monkeypatch.setattr(g, "HOST_GID", os.getgid())
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    state.chmod(0o700)
    monkeypatch.setattr(g, "GATEWAY_STATE_ROOT", state)
    monkeypatch.setattr(g, "GATEWAY_SOURCE_BUNDLES_ROOT", state / "source-bundles")
    monkeypatch.setattr(g, "GATEWAY_PREDECESSOR_ARTIFACT_ROOT", state / "predecessor-artifacts")
    monkeypatch.setattr(g, "GATEWAY_REPOSITORY", state / "repository.git")
    monkeypatch.setattr(g, "GATEWAY_DEPLOYMENTS_ROOT", state / "deployments")
    monkeypatch.setattr(g, "GATEWAY_RECOVERY_AUTHORITY_STORE", state / "recovery-authority.json")
    monkeypatch.setattr(g, "GATEWAY_LOCK", state / "ledger.lock")

    def tree(commit):
        return subprocess.check_output(
            ["git", "-C", str(mirror), "rev-parse", f"{commit}^{{tree}}"], text=True
        ).strip()

    def entry_identity(commit):
        row = subprocess.check_output(
            ["git", "-C", str(mirror), "ls-tree", commit, "--", g.GATEWAY_ENTRYPOINT],
            text=True,
        ).strip()
        metadata, path = row.split("\t", 1)
        mode, kind, blob = metadata.split()
        assert (mode, kind, path) == ("100644", "blob", g.GATEWAY_ENTRYPOINT)
        payload = subprocess.check_output(
            ["git", "-C", str(mirror), "cat-file", "blob", blob]
        )
        return RecoveryEntrypointIdentity(
            path=path,
            blob_oid=blob,
            sha256=hashlib.sha256(payload).hexdigest(),
            tracked_mode=mode,
        )

    source_values = {
        "repository": "James3014/Nexus-new",
        "accepted_commit": accepted,
        "accepted_tree": tree(accepted),
        "accepted_entrypoint": entry_identity(accepted),
        "desired_commit": desired,
        "desired_tree": tree(desired),
        "desired_entrypoint": entry_identity(desired),
        "predecessor_commit": predecessor,
        "predecessor_tree": tree(predecessor),
        "predecessor_entrypoint": entry_identity(predecessor),
        "interpreter": InterpreterIdentity(),
    }
    source_set = RecoverySourceSet(
        **source_values, source_set_sha256=canonical_hash(source_values)
    )
    desired_manifest = derive_deployment_manifest(source_set, role="desired")
    predecessor_manifest = derive_deployment_manifest(source_set, role="predecessor")
    artifact_root = g.GATEWAY_PREDECESSOR_ARTIFACT_ROOT
    artifact_root.mkdir(mode=0o700)
    artifact_candidate = artifact_root / "candidate.bundle"
    subprocess.run(
        [
            "git", "-C", str(mirror), "bundle", "create", str(artifact_candidate),
            "refs/nexus-r1/predecessor-artifact",
        ],
        check=True,
    )
    artifact_candidate.chmod(0o600)
    artifact_bytes = artifact_candidate.read_bytes()
    artifact_sha256 = hashlib.sha256(artifact_bytes).hexdigest()
    artifact = artifact_root / f"{artifact_sha256}.bundle"
    artifact_candidate.rename(artifact)
    receipt_values = {
        "schema": RecoveryAuthorityReceipt.SCHEMA,
        "receipt_version": 2,
        "receipt_id": "receipt-1",
        "card_sha256": RECOVERY_CARD_SHA256,
        "source_base_merge": SOURCE_BASE_MERGE,
        "source_base_tree": SOURCE_BASE_TREE,
        "current_main_sha": accepted,
        "operation": "gateway-recover",
        "effect_class": EffectClass.GATEWAY_DURABLE_RECOVERY,
        "service_label": g.GATEWAY_LABEL,
        "plist_path": str(g.GATEWAY_PLIST),
        "endpoint": g.GATEWAY_ENDPOINT,
        "desired_manifest_id": desired_manifest.deployment_id,
        "desired_manifest_sha256": desired_manifest.manifest_sha256,
        "predecessor_manifest_id": predecessor_manifest.deployment_id,
        "predecessor_manifest_sha256": predecessor_manifest.manifest_sha256,
        "request_id": "request-1",
        "idempotency_fence": "fence-1",
        "issued_at": "2020-01-01T00:00:00Z",
        "expires_at": "2099-01-01T00:00:00Z",
        "revocation_state": "NOT_REVOKED",
        "revoked_at": None,
        "revocation_reason": None,
        "issuer_id": "owner-james",
        "coordinator_id": "coordinator-codex",
        "authorized_actor_id": "coordinator-codex",
        "owner_activation_id": "OWNER_ISSUE526_FUTURE_TRACKED_20260902",
        "owner_activation_sha256": "9" * 64,
        "source_thread": "ops-r1-fixture-future-thread",
        "standing_grant_id": "OWNER_STANDING_COORDINATOR_20260818_DURABLE_GITHUB_WORKFLOW",
        "standing_grant_receipt_sha256": "3b8895f093692257d6225fbb8150b34f520e667d250c7817ad120cefd42751d5",
        "repository": "James3014/Nexus-new",
        "host_card_path": RECOVERY_CARD_PATH,
        "accepted_source_merge": accepted,
        "accepted_source_tree": tree(accepted),
        "final_manager_sha256": hashlib.sha256(Path(g.__file__).read_bytes()).hexdigest(),
        "independent_acceptance_receipt_hash": "a" * 64,
        "authority_floor_commit": accepted,
        "authority_floor_tree": tree(accepted),
        "desired_commit": desired,
        "desired_tree": tree(desired),
        "predecessor_commit": predecessor,
        "predecessor_tree": tree(predecessor),
        "predecessor_artifact_format": "git-bundle-self-contained-v1",
        "predecessor_artifact_sha256": artifact_sha256,
        "predecessor_artifact_size": len(artifact_bytes),
        "source_set": source_set,
        "desired_manifest": desired_manifest,
        "predecessor_manifest": predecessor_manifest,
    }
    receipt = RecoveryAuthorityReceipt(
        **receipt_values, receipt_hash=canonical_hash(receipt_values)
    )
    request_values = {
        "request_id": receipt.request_id,
        "idempotency_fence": receipt.idempotency_fence,
        "operation": receipt.operation,
        "effect_class": receipt.effect_class,
        "recovery_authority_id": receipt.receipt_id,
        "recovery_authority_hash": receipt.receipt_hash,
        "desired_manifest_id": desired_manifest.deployment_id,
        "desired_manifest_hash": desired_manifest.manifest_sha256,
        "predecessor_manifest_id": predecessor_manifest.deployment_id,
        "predecessor_manifest_hash": predecessor_manifest.manifest_sha256,
    }
    request = GatewayRecoveryRequest(
        **request_values, request_hash=canonical_hash(request_values)
    )
    raw = json.dumps(receipt.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    tracked = mirror / g.RECOVERY_AUTHORITY_SOURCE_PATH
    tracked.parent.mkdir(parents=True)
    tracked.write_bytes(raw)
    subprocess.run(["git", "-C", str(mirror), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(mirror), "commit", "-q", "-m", "receipt"], check=True)
    g.GATEWAY_RECOVERY_AUTHORITY_STORE.write_bytes(raw)
    g.GATEWAY_RECOVERY_AUTHORITY_STORE.chmod(0o600)
    return {
        "mirror": mirror,
        "state": state,
        "receipt": receipt,
        "request": request,
        "desired": desired,
        "predecessor": predecessor,
        "desired_manifest": desired_manifest,
        "predecessor_manifest": predecessor_manifest,
        "predecessor_artifact": artifact,
    }


def test_r1b1_real_git_bundle_bare_store_and_two_detached_worktrees(tmp_path, monkeypatch):
    """The public B1 checkpoint stages two full paths and starts no host effect."""
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    calls = []
    monkeypatch.setattr(
        g, "_launchctl_observation", lambda *args, **kwargs: calls.append((args, kwargs))
    )
    outcome = g.gateway_recover(fixture["request"])
    assert outcome.result == "BLOCKED"
    assert outcome.effect_started is False
    assert outcome.physical_observation["readiness"] == ["TARGET_READY", "ROLLBACK_READY"]
    assert calls == []
    desired_path = Path(outcome.physical_observation["desired_path"])
    predecessor_path = Path(outcome.physical_observation["predecessor_path"])
    assert desired_path.is_dir() and predecessor_path.is_dir()
    assert g.GATEWAY_REPOSITORY.is_dir()
    assert subprocess.run(
        [
            "git", "-C", str(fixture["mirror"]), "merge-base", "--is-ancestor",
            fixture["predecessor"], "main",
        ],
        check=False,
    ).returncode == 1
    shutil.rmtree(fixture["mirror"])
    for worktree, commit, manifest in (
        (desired_path, fixture["desired"], fixture["desired_manifest"]),
        (predecessor_path, fixture["predecessor"], fixture["predecessor_manifest"]),
    ):
        assert subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip() == commit
        assert not (worktree / ".git").is_symlink()
        assert g._r1_verify_worktree(worktree, manifest) == worktree


def test_r1b1_local_typed_receipt_mismatch_fails_before_bundle(tmp_path, monkeypatch):
    from nexus.contracts.gateway_deployment import canonical_hash

    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    receipt = fixture["receipt"]
    values = {**receipt.__dict__, "independent_acceptance_receipt_hash": "d" * 64}
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    altered = receipt.__class__(**values)
    request = fixture["request"]
    request_values = {**request.__dict__, "recovery_authority_hash": altered.receipt_hash}
    request_values["request_hash"] = canonical_hash({
        key: value for key, value in request_values.items()
        if key not in {"request_hash", "schema"}
    })
    altered_request = request.__class__(**request_values)
    with pytest.raises(g.GatewayContractError, match="differs from fixed local"):
        g.stage_verified_git_store(altered_request, altered)
    assert not g.GATEWAY_SOURCE_BUNDLES_ROOT.exists()


def test_r1_historical_activation_cannot_authorize_new_target_at_manager(tmp_path, monkeypatch):
    """Hostile: a fully rehashed receipt reusing the historical 2026-08-23
    activation lineage against a new target fails closed at the manager with
    zero bundle/staging effect (legacy activations stay exact-target-bound)."""
    from nexus.contracts.gateway_deployment import canonical_hash

    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    receipt = fixture["receipt"]
    values = {
        **receipt.__dict__,
        "owner_activation_id": "OWNER_ISSUE526_CONTINUE_20260823",
        "owner_activation_sha256": (
            "f0ed77ffe3872b083ef0b6d66526524a7091a8e3125322c84ba632f3c64ba322"
        ),
        "source_thread": "01a02a17-691c-7a20-ad0f-9166456416dc",
    }
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    historical_receipt = receipt.__class__(**values)
    request_values = {
        **fixture["request"].__dict__,
        "recovery_authority_id": historical_receipt.receipt_id,
        "recovery_authority_hash": historical_receipt.receipt_hash,
    }
    request_values["request_hash"] = canonical_hash({
        key: value for key, value in request_values.items()
        if key not in {"request_hash", "schema"}
    })
    historical_request = fixture["request"].__class__(**request_values)
    # Even if the attacker fully controls the fixed local store, the manager
    # rejects the historical lineage before any bundle or physical effect.
    g.GATEWAY_RECOVERY_AUTHORITY_STORE.write_bytes(
        json.dumps(historical_receipt.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    )
    g.GATEWAY_RECOVERY_AUTHORITY_STORE.chmod(0o600)
    with pytest.raises(g.GatewayContractError, match="source authority rejected") as excinfo:
        g.stage_verified_git_store(historical_request, historical_receipt)
    assert excinfo.value.__cause__ is not None
    assert "historical activation" in str(excinfo.value.__cause__)
    assert not g.GATEWAY_SOURCE_BUNDLES_ROOT.exists()


def test_r1_local_receipt_not_tracked_on_fresh_main_has_zero_effect(tmp_path, monkeypatch):
    """Hostile: a locally self-issued receipt with valid schema/hash that is NOT
    byte-identical to the fixed tracked receipt on fresh main has zero effect."""
    from nexus.contracts.gateway_deployment import canonical_hash

    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    receipt = fixture["receipt"]
    values = {
        **receipt.__dict__,
        "independent_acceptance_receipt_hash": "b" * 64,
    }
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    forged = receipt.__class__(**values)
    request_values = {
        **fixture["request"].__dict__,
        "recovery_authority_id": forged.receipt_id,
        "recovery_authority_hash": forged.receipt_hash,
    }
    request_values["request_hash"] = canonical_hash({
        key: value for key, value in request_values.items()
        if key not in {"request_hash", "schema"}
    })
    forged_request = fixture["request"].__class__(**request_values)
    # The forged receipt replaces the fixed local store, but the tracked bytes
    # on fresh main still hold the original receipt: the manager must fail
    # closed on byte identity before any bundle or Gateway effect.
    g.GATEWAY_RECOVERY_AUTHORITY_STORE.write_bytes(
        json.dumps(forged.model_dump(), sort_keys=True, separators=(",", ":")).encode()
    )
    g.GATEWAY_RECOVERY_AUTHORITY_STORE.chmod(0o600)
    with pytest.raises(
        g.GatewayContractError,
        match="remote/local byte mismatch|differs from fixed local",
    ):
        g.stage_verified_git_store(forged_request, forged)
    assert not g.GATEWAY_SOURCE_BUNDLES_ROOT.exists()


def test_r1b1_safe_ancestry_and_existing_bare_identity_fail_closed(tmp_path, monkeypatch):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    state.chmod(0o700)
    monkeypatch.setattr(g, "GATEWAY_STATE_ROOT", state)
    monkeypatch.setattr(g, "HOST_UID", os.getuid())
    monkeypatch.setattr(g, "HOST_GID", os.getgid())
    unsafe = state / "unsafe"
    outside = tmp_path / "outside"
    outside.mkdir()
    unsafe.symlink_to(outside, target_is_directory=True)
    with pytest.raises(g.GatewayContractError, match="ownership/mode"):
        g._r1_safe_directory(unsafe)
    unsafe.unlink()
    state.chmod(0o755)
    with pytest.raises(g.GatewayContractError, match="ownership/mode"):
        g._r1_safe_directory(state / "child")
    state.chmod(0o700)

    repository = state / "repository.git"
    repository.mkdir(mode=0o700)
    repository.chmod(0o700)
    monkeypatch.setattr(g, "GATEWAY_REPOSITORY", repository)
    with pytest.raises(g.GatewayContractError, match="not bare"):
        g._r1_verify_bare_repository()
    shutil.rmtree(repository)
    subprocess.run(["git", "init", "-q", "--bare", str(repository)], check=True)
    repository.chmod(0o755)
    with pytest.raises(g.GatewayContractError, match="ownership/mode"):
        g._r1_verify_bare_repository()
    repository.chmod(0o700)
    subprocess.run(
        ["git", "--git-dir", str(repository), "remote", "add", "origin", "wrong"],
        check=True,
    )
    with pytest.raises(g.GatewayContractError, match="origin"):
        g._r1_verify_bare_repository()


def test_r1b1_wrong_owner_and_accepted_tree_mismatch_fail_closed(tmp_path, monkeypatch):
    from types import SimpleNamespace

    from nexus.contracts.gateway_deployment import (
        RecoverySourceSet,
        canonical_hash,
        derive_deployment_manifest,
    )

    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    state.chmod(0o700)
    monkeypatch.setattr(g, "GATEWAY_STATE_ROOT", state)
    monkeypatch.setattr(g, "HOST_UID", os.getuid())
    monkeypatch.setattr(g, "HOST_GID", os.getgid())
    actual_lstat = g.os.lstat
    def wrong_owner(path):
        info = actual_lstat(path)
        if Path(path) == state:
            values = {
                name: getattr(info, name)
                for name in dir(info)
                if name.startswith("st_")
            }
            values["st_uid"] = os.getuid() + 1
            return SimpleNamespace(**values)
        return info
    monkeypatch.setattr(g.os, "lstat", wrong_owner)
    with pytest.raises(g.GatewayContractError, match="ownership/mode"):
        g._r1_safe_directory(state)
    monkeypatch.setattr(g.os, "lstat", actual_lstat)

    physical = tmp_path / "physical"
    physical.mkdir()
    fixture = _r1b1_fixture(physical, monkeypatch)
    receipt = fixture["receipt"]
    source_values = {
        **receipt.source_set.__dict__,
        "accepted_tree": "f" * 40,
    }
    source_values["source_set_sha256"] = canonical_hash({
        key: value for key, value in source_values.items()
        if key != "source_set_sha256"
    })
    source_set = RecoverySourceSet(**source_values)
    altered_values = {
        **receipt.__dict__,
        "accepted_source_tree": "f" * 40,
        "authority_floor_tree": "f" * 40,
        "source_set": source_set,
        "desired_manifest": derive_deployment_manifest(source_set, role="desired"),
        "predecessor_manifest": derive_deployment_manifest(
            source_set, role="predecessor"
        ),
    }
    altered = receipt.__class__(**altered_values)
    artifact_scratch, predecessor_store = g._r1_verify_predecessor_artifact(receipt)
    try:
        with pytest.raises(g.GatewayContractError, match="commit/tree"):
            g._r1_derive_source_set(altered, predecessor_store)
    finally:
        shutil.rmtree(artifact_scratch, ignore_errors=True)


def test_r1b1_reuse_tamper_common_dir_and_bundle_tamper_block(tmp_path, monkeypatch):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    staged = g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    desired = staged.desired_path
    entrypoint = desired / g.GATEWAY_ENTRYPOINT
    entrypoint.chmod(0o755)
    with pytest.raises(g.GatewayContractError, match="commit/tree/clean|physical identity"):
        g._r1_verify_worktree(desired, fixture["desired_manifest"])
    entrypoint.chmod(0o644)
    git_file = desired / ".git"
    original_git_file = git_file.read_bytes()
    git_file.write_text(f"gitdir: {fixture['mirror'] / '.git'}\n")
    with pytest.raises(g.GatewayContractError, match="common-dir"):
        g._r1_verify_worktree(desired, fixture["desired_manifest"])
    git_file.write_bytes(original_git_file)
    entrypoint.write_text("tampered\n")
    with pytest.raises(g.GatewayContractError, match="commit/tree/clean"):
        g._r1_verify_worktree(desired, fixture["desired_manifest"])
    subprocess.run(["git", "-C", str(desired), "checkout", "-q", "--", "."], check=True)
    bundle = (
        g.GATEWAY_SOURCE_BUNDLES_ROOT / f"{fixture['receipt'].receipt_hash}.bundle"
    )
    original_bundle = bundle.read_bytes()
    bundle.write_bytes(original_bundle + b"\ntampered")
    bundle.chmod(0o600)
    with pytest.raises(g.GatewayContractError):
        g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    bundle.write_bytes(original_bundle)
    bundle.chmod(0o600)
    bundle.chmod(0o644)
    with pytest.raises(g.GatewayContractError, match="bundle identity"):
        g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    bundle.chmod(0o600)
    outside_bundle = tmp_path / "outside.bundle"
    outside_bundle.write_bytes(original_bundle)
    outside_bundle.chmod(0o600)
    bundle.unlink()
    bundle.symlink_to(outside_bundle)
    with pytest.raises(g.GatewayContractError, match="bundle identity"):
        g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    bundle.unlink()
    bundle.write_bytes(original_bundle)
    bundle.chmod(0o600)
    assert g._r1_verify_worktree(desired, fixture["desired_manifest"]) == desired


def test_r1b1_strict_evidence_seam_precedes_worktree_promotion(tmp_path, monkeypatch):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    events = []
    import_bundle = g._r1_import_bundle
    bundle_evidence = g._r1_bundle_evidence
    materialize = g._r1_materialize_worktree

    def observed_import(*args, **kwargs):
        result = import_bundle(*args, **kwargs)
        events.append("bare-verified")
        return result

    def observed_evidence(*args, **kwargs):
        assert events == ["bare-verified"]
        result = bundle_evidence(*args, **kwargs)
        events.append("evidence-validated")
        return result

    def observed_materialize(*args, **kwargs):
        assert events[:2] == ["bare-verified", "evidence-validated"]
        events.append("worktree")
        return materialize(*args, **kwargs)

    monkeypatch.setattr(g, "_r1_import_bundle", observed_import)
    monkeypatch.setattr(g, "_r1_bundle_evidence", observed_evidence)
    monkeypatch.setattr(g, "_r1_materialize_worktree", observed_materialize)
    staged = g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    assert staged.bundle_evidence.evidence_hash
    assert events == [
        "bare-verified", "evidence-validated", "worktree", "worktree"
    ]


def test_r1b1_named_role_swap_extra_refs_and_valid_bundle_encodings(tmp_path, monkeypatch):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    source = tmp_path / "bundle-source.git"
    subprocess.run(["git", "init", "-q", "--bare", str(source)], check=True)
    fresh = subprocess.check_output(
        ["git", "-C", str(fixture["mirror"]), "rev-parse", "HEAD"], text=True
    ).strip()
    mappings = (
        ("refs/nexus-r1/fresh-main", fresh),
        ("refs/nexus-r1/desired", fixture["predecessor"]),
        ("refs/nexus-r1/predecessor", fixture["desired"]),
        ("refs/nexus-r1/extra", fixture["receipt"].accepted_source_merge),
    )
    for ref, commit in mappings:
        subprocess.run(
            [
                "git", "--git-dir", str(source), "fetch", "-q", "--no-tags",
                str(fixture["mirror"]), f"+{commit}:{ref}",
            ],
            check=True,
        )
    extra_bundle = tmp_path / "extra.bundle"
    subprocess.run(
        [
            "git", "--git-dir", str(source), "bundle", "create", str(extra_bundle),
            *(ref for ref, _ in mappings),
        ],
        check=True,
    )
    with pytest.raises(g.GatewayContractError, match="refs"):
        g._r1_bundle_heads(extra_bundle)
    swapped_bundle = tmp_path / "swapped.bundle"
    subprocess.run(
        [
            "git", "--git-dir", str(source), "bundle", "create", str(swapped_bundle),
            *(ref for ref, _ in mappings[:3]),
        ],
        check=True,
    )
    g.GATEWAY_SOURCE_BUNDLES_ROOT.mkdir(mode=0o700)
    g.GATEWAY_SOURCE_BUNDLES_ROOT.chmod(0o700)
    persisted = (
        g.GATEWAY_SOURCE_BUNDLES_ROOT / f"{fixture['receipt'].receipt_hash}.bundle"
    )
    persisted.write_bytes(swapped_bundle.read_bytes())
    persisted.chmod(0o600)
    with pytest.raises(g.GatewayContractError, match="bundle bytes|role/commit"):
        g.stage_verified_git_store(fixture["request"], fixture["receipt"])

    correct_source = tmp_path / "correct-source.git"
    subprocess.run(["git", "init", "-q", "--bare", str(correct_source)], check=True)
    correct = (
        ("refs/nexus-r1/fresh-main", fresh),
        ("refs/nexus-r1/desired", fixture["desired"]),
        ("refs/nexus-r1/predecessor", fixture["predecessor"]),
    )
    for ref, commit in correct:
        subprocess.run(
            [
                "git", "--git-dir", str(correct_source), "fetch", "-q", "--no-tags",
                str(fixture["mirror"]), f"+{commit}:{ref}",
            ],
            check=True,
        )
    encoded = []
    for version in ("2", "3"):
        path = tmp_path / f"bundle-v{version}"
        subprocess.run(
            [
                "git", "--git-dir", str(correct_source), "bundle", "create",
                f"--version={version}", str(path), *(ref for ref, _ in correct),
            ],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(fixture["mirror"]), "bundle", "verify", str(path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        encoded.append(hashlib.sha256(path.read_bytes()).hexdigest())
    assert encoded[0] != encoded[1]
    assert fixture["desired_manifest"].deployment_id == fixture["receipt"].desired_manifest_id


def test_r1b1_bounded_subprocess_import_failure_is_rejected(tmp_path, monkeypatch):
    monkeypatch.setattr(g, "INTERPRETER", sys.executable)
    root = tmp_path / "checkout"
    entrypoint = root / g.GATEWAY_ENTRYPOINT
    entrypoint.parent.mkdir(parents=True)
    entrypoint.write_text("import module_that_does_not_exist_r1b1\n")
    with pytest.raises(g.GatewayContractError, match="bounded repository import"):
        g._r1_import_witness(root)


def test_g20_exact_tree_gitlink_stages_inert_without_recursive_git_commands(tmp_path, monkeypatch):
    fixture = _r1b1_fixture(tmp_path, monkeypatch, gitlink=True)
    commands = []
    real_run = g._r1_run

    def recording_run(*command, **kwargs):
        commands.append(command)
        return real_run(*command, **kwargs)

    monkeypatch.setattr(g, "_r1_run", recording_run)
    staged = g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    for deployment in (staged.desired_path,):
        gitlink = deployment / "nested-repository"
        assert not gitlink.exists() or (gitlink.is_dir() and not any(gitlink.iterdir()))
        assert g._r1_verify_worktree(deployment, fixture["desired_manifest"]) == deployment
    flattened = [part for command in commands for part in command]
    assert "submodule" not in flattened
    assert not any("recurse-submodules" in part for part in flattened)


def test_r1b1_fresh_main_gitlink_is_rejected(tmp_path, monkeypatch):
    # Under G20 Settled Contract A, fresh tree gitlinks remain inert metadata without recursive execution.
    fixture = _r1b1_fixture(tmp_path, monkeypatch, gitlink=True)
    staged = g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    assert staged is not None


def test_g20_nested_gitlink_path_is_recursively_enumerated_and_fails_closed(
    tmp_path, monkeypatch
):
    fixture = _r1b1_fixture(
        tmp_path, monkeypatch, gitlink=True, gitlink_path="packages/core"
    )
    staged = g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    assert Path("packages/core") in g._r1_gitlink_paths(fixture["desired"])
    gitlink = staged.desired_path / "packages/core"
    if gitlink.exists():
        shutil.rmtree(gitlink)
    gitlink.mkdir(parents=True)
    (gitlink / "payload").write_text("substituted")
    with pytest.raises(g.GatewayContractError, match="Gitlink"):
        g._r1_verify_worktree(staged.desired_path, fixture["desired_manifest"])


@pytest.mark.parametrize("substitution", ["file", "symlink", "populated", "nested-git"])
def test_g20_populated_or_substituted_gitlink_path_fails_closed(
    tmp_path, monkeypatch, substitution
):
    fixture = _r1b1_fixture(tmp_path, monkeypatch, gitlink=True)
    staged = g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    gitlink = staged.desired_path / "nested-repository"
    if gitlink.exists():
        shutil.rmtree(gitlink)
    if substitution == "file":
        gitlink.write_text("substituted")
    elif substitution == "symlink":
        gitlink.symlink_to(staged.desired_path / g.GATEWAY_ENTRYPOINT)
    else:
        gitlink.mkdir()
        (gitlink / (".git" if substitution == "nested-git" else "payload")).write_text("x")
    with pytest.raises(g.GatewayContractError, match="Gitlink"):
        g._r1_verify_worktree(staged.desired_path, fixture["desired_manifest"])


@pytest.mark.parametrize("tamper", ["missing", "mode"])
def test_g20_predecessor_artifact_tamper_blocks_before_promotion(
    tmp_path, monkeypatch, tamper
):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    artifact = fixture["predecessor_artifact"]
    if tamper == "missing":
        artifact.unlink()
    else:
        artifact.chmod(0o644)
    with pytest.raises(g.GatewayContractError, match="artifact"):
        g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    assert not g.GATEWAY_DEPLOYMENTS_ROOT.exists()


@pytest.mark.parametrize("identity_field", ["st_uid", "st_gid"])
def test_g20_predecessor_artifact_wrong_owner_identity_fails_before_promotion(
    tmp_path, monkeypatch, identity_field
):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    artifact = fixture["predecessor_artifact"]
    actual_lstat = g.os.lstat

    def wrong_identity(path):
        info = actual_lstat(path)
        if Path(path) != artifact:
            return info
        values = {
            name: getattr(info, name)
            for name in dir(info)
            if name.startswith("st_")
        }
        values[identity_field] = getattr(info, identity_field) + 1
        return SimpleNamespace(**values)

    monkeypatch.setattr(g.os, "lstat", wrong_identity)
    with pytest.raises(
        g.GatewayContractError,
        match="R1 predecessor artifact identity invalid",
    ):
        g._r1_verify_predecessor_artifact(fixture["receipt"])
    assert not g.GATEWAY_DEPLOYMENTS_ROOT.exists()


def test_g20_predecessor_artifact_wrong_size_fails_before_promotion(
    tmp_path, monkeypatch
):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    artifact = fixture["predecessor_artifact"]
    artifact.write_bytes(artifact.read_bytes() + b"tamper")
    with pytest.raises(
        g.GatewayContractError,
        match="R1 predecessor artifact identity invalid",
    ):
        g._r1_verify_predecessor_artifact(fixture["receipt"])
    assert not g.GATEWAY_DEPLOYMENTS_ROOT.exists()


def test_g20_predecessor_artifact_same_size_wrong_sha_fails_before_promotion(
    tmp_path, monkeypatch
):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    artifact = fixture["predecessor_artifact"]
    payload = artifact.read_bytes()
    artifact.write_bytes(bytes([payload[0] ^ 1]) + payload[1:])
    with pytest.raises(
        g.GatewayContractError,
        match="R1 predecessor artifact hash mismatch",
    ):
        g._r1_verify_predecessor_artifact(fixture["receipt"])
    assert artifact.stat().st_size == fixture["receipt"].predecessor_artifact_size
    assert not g.GATEWAY_DEPLOYMENTS_ROOT.exists()


def test_g20_predecessor_artifact_tree_mismatch_fails_before_promotion(
    tmp_path, monkeypatch
):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    receipt = fixture["receipt"]
    altered = receipt.__class__(**{**receipt.__dict__, "predecessor_tree": "f" * 40})
    with pytest.raises(
        g.GatewayContractError,
        match="R1 predecessor artifact tree mismatch",
    ):
        g._r1_verify_predecessor_artifact(altered)
    assert not g.GATEWAY_DEPLOYMENTS_ROOT.exists()


@pytest.mark.parametrize(
    ("identity_field", "wrong_value"),
    [
        ("blob_oid", "f" * 40),
        ("sha256", "f" * 64),
        ("tracked_mode", "100755"),
    ],
)
def test_g20_predecessor_artifact_entrypoint_identity_mismatch_fails_before_promotion(
    tmp_path, monkeypatch, identity_field, wrong_value
):
    from nexus.contracts.gateway_deployment import (
        RecoveryEntrypointIdentity,
        RecoverySourceSet,
    )

    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    receipt = fixture["receipt"]
    entrypoint = receipt.source_set.predecessor_entrypoint
    altered_entrypoint = RecoveryEntrypointIdentity(
        **{**entrypoint.__dict__, identity_field: wrong_value}
    )
    source_set = RecoverySourceSet(
        **{
            **receipt.source_set.__dict__,
            "predecessor_entrypoint": altered_entrypoint,
        }
    )
    altered = receipt.__class__(**{**receipt.__dict__, "source_set": source_set})
    with pytest.raises(
        g.GatewayContractError,
        match="R1 predecessor artifact entrypoint mismatch",
    ):
        g._r1_verify_predecessor_artifact(altered)
    assert not g.GATEWAY_DEPLOYMENTS_ROOT.exists()


@pytest.mark.parametrize("variant", ["wrong-ref", "prerequisite-dependent"])
def test_g20_predecessor_artifact_transport_substitution_fails_closed(
    tmp_path, monkeypatch, variant
):
    from nexus.contracts.gateway_deployment import canonical_hash

    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    mirror = fixture["mirror"]
    predecessor = fixture["predecessor"]
    artifact_root = g.GATEWAY_PREDECESSOR_ARTIFACT_ROOT
    candidate = artifact_root / f"{variant}.bundle"
    if variant == "wrong-ref":
        wrong_ref = "refs/nexus-r1/wrong-predecessor"
        subprocess.run(
            ["git", "-C", str(mirror), "update-ref", wrong_ref, predecessor],
            check=True,
        )
        revs = [wrong_ref]
    else:
        base = subprocess.check_output(
            ["git", "-C", str(mirror), "rev-parse", f"{predecessor}^"],
            text=True,
        ).strip()
        revs = ["refs/nexus-r1/predecessor-artifact", f"^{base}"]
    subprocess.run(
        ["git", "-C", str(mirror), "bundle", "create", str(candidate), *revs],
        check=True,
    )
    candidate.chmod(0o600)
    payload = candidate.read_bytes()
    artifact_sha256 = hashlib.sha256(payload).hexdigest()
    bound = artifact_root / f"{artifact_sha256}.bundle"
    candidate.rename(bound)
    receipt = fixture["receipt"]
    values = {
        **receipt.__dict__,
        "predecessor_artifact_sha256": artifact_sha256,
        "predecessor_artifact_size": len(payload),
    }
    values["receipt_hash"] = canonical_hash({
        key: value for key, value in values.items() if key != "receipt_hash"
    })
    substituted = receipt.__class__(**values)
    with pytest.raises(g.GatewayContractError, match="artifact|fixed subprocess"):
        g._r1_verify_predecessor_artifact(substituted)
    assert not g.GATEWAY_DEPLOYMENTS_ROOT.exists()


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


def test_main_install_artifact_skips_current_gateway_observation(monkeypatch, tmp_path):
    request = _gateway_request("install-artifact")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request.model_dump(), default=str))
    request_path.chmod(0o600)
    monkeypatch.setattr(g, "GATEWAY_REQUEST_STORE", request_path)
    seen = {}
    monkeypatch.setattr(g, "collect_gateway_observation", lambda *args, **kwargs: pytest.fail(
        "install-artifact must not observe the current Gateway"
    ))
    monkeypatch.setattr(g, "dispatch_gateway_cli", lambda action, **kwargs: seen.update(
        action=action, observed=kwargs["observed"]
    ) or {"state": "VERIFIED"})
    monkeypatch.setattr(sys, "argv", [
        "mcp_gateway_durable.py", "gateway-install-artifact", "--gateway-request", str(request_path)
    ])

    assert g.main() == 0
    assert seen == {"action": "install-artifact", "observed": {}}


def test_main_reload_still_collects_current_gateway_observation(monkeypatch, tmp_path):
    request = _gateway_request("reload")
    request_path = tmp_path / "request.json"
    request_path.write_text(json.dumps(request.model_dump(), default=str))
    request_path.chmod(0o600)
    monkeypatch.setattr(g, "GATEWAY_REQUEST_STORE", request_path)
    seen = {}
    physical = {"loaded": True}
    monkeypatch.setattr(g, "collect_gateway_observation", lambda *args, **kwargs: physical)
    monkeypatch.setattr(g, "dispatch_gateway_cli", lambda action, **kwargs: seen.update(
        action=action, observed=kwargs["observed"]
    ) or {"state": "VERIFIED"})
    monkeypatch.setattr(sys, "argv", [
        "mcp_gateway_durable.py", "gateway-reload", "--gateway-request", str(request_path)
    ])

    assert g.main() == 0
    assert seen == {"action": "reload", "observed": physical}


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
        observation_time="2026-08-23T00:00:00Z",
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


def test_authority_source_root_owned_sticky_ancestor_is_allowed():
    info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o1777, st_uid=0)
    g._validate_authority_source_directory(info, leaf=False)


def test_authority_source_nonsticky_group_or_world_writable_ancestor_is_rejected():
    info = SimpleNamespace(st_mode=stat.S_IFDIR | 0o0777, st_uid=0)
    with pytest.raises(g.GatewayContractError, match="ancestry unsafe"):
        g._validate_authority_source_directory(info, leaf=False)


@pytest.mark.parametrize(
    "info",
    [
        SimpleNamespace(st_mode=stat.S_IFDIR | 0o0755, st_uid=12345),
        SimpleNamespace(st_mode=stat.S_IFLNK | 0o0777, st_uid=os.getuid()),
    ],
    ids=["wrong-owner", "symlink"],
)
def test_authority_source_wrong_owner_or_symlink_ancestor_is_rejected(info):
    with pytest.raises(g.GatewayContractError, match="ancestry unsafe"):
        g._validate_authority_source_directory(info, leaf=False)


def _r1b2_record(fixture, staged, state, sequence, parent_hash):
    from nexus.contracts.gateway_deployment import RecoveryLedgerRecord, canonical_hash

    request = fixture["request"]
    receipt = fixture["receipt"]
    values = {
        "schema": "nexus.gateway.ledger.v2",
        "request_id": request.request_id,
        "request_hash": request.request_hash,
        "state": state,
        "sequence": sequence,
        "parent_hash": parent_hash,
        "authority_schema": receipt.schema,
        "receipt_id": receipt.receipt_id,
        "receipt_hash": receipt.receipt_hash,
        "card_sha256": receipt.card_sha256,
        "accepted_source_merge": receipt.accepted_source_merge,
        "accepted_source_tree": receipt.accepted_source_tree,
        "final_manager_sha256": receipt.final_manager_sha256,
        "independent_acceptance_receipt_hash": (
            receipt.independent_acceptance_receipt_hash
        ),
        "source_set_sha256": receipt.source_set.source_set_sha256,
        "desired_manifest_id": receipt.desired_manifest_id,
        "desired_manifest_hash": receipt.desired_manifest_sha256,
        "predecessor_manifest_id": receipt.predecessor_manifest_id,
        "predecessor_manifest_hash": receipt.predecessor_manifest_sha256,
        "source_bundle_evidence_hash": (
            None if state == "REQUESTED" else staged.bundle_evidence.evidence_hash
        ),
        "operation": request.operation,
        "effect_class": request.effect_class,
        "idempotency_fence": request.idempotency_fence,
        "pre_effect_identity": {},
        "observed_identity": {},
    }
    values["record_hash"] = canonical_hash(values)
    return RecoveryLedgerRecord.model_validate(values)


def _r1b2_prepared_fixture(tmp_path, monkeypatch):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    staged = g.stage_verified_git_store(fixture["request"], fixture["receipt"])
    fixture["staged"] = staged
    fixture["ledger_path"] = fixture["state"] / "ledger.jsonl"
    fixture["lock_path"] = fixture["state"] / "ledger.lock"
    return fixture


def test_r1b2_ledger_v2_exact_jsonl_fsync_mixed_chain_and_v1_bytes(
    tmp_path, monkeypatch
):
    fixture = _r1b2_prepared_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    v1 = ledger.append(
        request_id="legacy-request",
        request_hash="a" * 64,
        state="REQUESTED",
        host_authority=_ledger_receipt("legacy-request", "legacy-fence"),
        operation="reload",
        effect_class="GATEWAY_RELOAD",
        idempotency_fence="legacy-fence",
    )
    v1_bytes = fixture["ledger_path"].read_bytes()
    fsync_calls = []
    real_fsync = g.os.fsync
    monkeypatch.setattr(
        g.os, "fsync",
        lambda fd: (fsync_calls.append(fd), real_fsync(fd))[1],
    )
    record = _r1b2_record(
        fixture, fixture["staged"], "REQUESTED", 2, v1["record_hash"]
    )
    appended = ledger.append_recovery(
        record,
        expected_tail=v1["record_hash"],
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    )
    expected_v2 = (
        json.dumps(
            appended.model_dump(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
        + b"\n"
    )
    raw = fixture["ledger_path"].read_bytes()
    assert raw == v1_bytes + expected_v2
    assert raw.startswith(v1_bytes)
    assert fsync_calls
    rows = ledger.read()
    assert [row["sequence"] for row in rows] == [1, 2]
    assert rows[1]["parent_hash"] == rows[0]["record_hash"]
    assert rows[0]["schema"] == "nexus.gateway.ledger.v1"
    assert rows[1]["schema"] == "nexus.gateway.ledger.v2"
    assert set(rows[0]).isdisjoint({
        "authority_schema", "receipt_id", "source_set_sha256",
        "source_bundle_evidence_hash",
    })
    assert set(rows[1]).isdisjoint({
        "host_receipt_hash", "source_base_merge", "source_base_tree",
        "host_card_sha256",
    })
    recovery = ledger.recovery_rows(
        fixture["request"].request_id,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=fixture["staged"].bundle_evidence,
    )
    assert [row.state for row in recovery] == ["REQUESTED"]
    assert ledger.current_recovery_state(
        fixture["request"].request_id,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=fixture["staged"].bundle_evidence,
    ) == "REQUESTED"


def test_r1b2_ledger_v2_tamper_truncate_reorder_and_self_rehash_rejected(
    tmp_path, monkeypatch
):
    from nexus.contracts.gateway_deployment import canonical_hash

    fixture = _r1b2_prepared_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    first = _r1b2_record(fixture, fixture["staged"], "REQUESTED", 1, "")
    first = ledger.append_recovery(
        first,
        expected_tail="",
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    )
    second = _r1b2_record(
        fixture, fixture["staged"], "PREFLIGHTED", 2, first.record_hash
    )
    ledger.append_recovery(
        second,
        expected_tail=first.record_hash,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=fixture["staged"].bundle_evidence,
    )
    valid = fixture["ledger_path"].read_bytes()
    lines = valid.splitlines(keepends=True)
    corruptions = {
        "truncate": valid[:-1],
        "reorder": lines[1] + lines[0],
        "tamper": valid.replace(b'"state":"PREFLIGHTED"', b'"state":"VERIFIED"'),
    }
    for name, raw in corruptions.items():
        path = fixture["state"] / f"{name}.jsonl"
        path.write_bytes(raw)
        path.chmod(0o600)
        with pytest.raises(g.LedgerCorruption):
            g.GatewayLedger(path).read()
    substituted = json.loads(lines[1])
    substituted["receipt_hash"] = "f" * 64
    substituted["record_hash"] = canonical_hash({
        key: value for key, value in substituted.items() if key != "record_hash"
    })
    substitution_path = fixture["state"] / "substitution.jsonl"
    substitution_path.write_bytes(
        lines[0]
        + json.dumps(
            substituted, sort_keys=True, separators=(",", ":")
        ).encode()
        + b"\n"
    )
    substitution_path.chmod(0o600)
    substituted_ledger = g.GatewayLedger(substitution_path)
    with pytest.raises((g.LedgerCorruption, g.GatewayContractError)):
        substituted_ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=fixture["staged"].bundle_evidence,
        )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("request_hash", "0" * 64),
        ("idempotency_fence", "substituted-fence"),
        ("authority_schema", "nexus.gateway.other_authority.v1"),
        ("receipt_id", "substituted-receipt"),
        ("receipt_hash", "1" * 64),
        ("card_sha256", "2" * 64),
        ("accepted_source_merge", "3" * 40),
        ("accepted_source_tree", "4" * 40),
        ("final_manager_sha256", "5" * 64),
        ("independent_acceptance_receipt_hash", "6" * 64),
        ("source_set_sha256", "7" * 64),
        ("desired_manifest_id", "r1-substituted-desired"),
        ("desired_manifest_hash", "8" * 64),
        ("predecessor_manifest_id", "r1-substituted-predecessor"),
        ("predecessor_manifest_hash", "9" * 64),
        ("source_bundle_evidence_hash", "a" * 64),
    ],
)
def test_r1b2_ledger_v2_self_rehashed_suffix_substitution_rejected_by_trusted_context(
    tmp_path, monkeypatch, field, replacement
):
    from nexus.contracts.gateway_deployment import canonical_hash

    assert hasattr(g.GatewayLedger, "append_recovery")
    fixture = _r1b2_prepared_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    requested = _r1b2_record(
        fixture, fixture["staged"], "REQUESTED", 1, ""
    )
    requested = ledger.append_recovery(
        requested,
        expected_tail="",
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    )
    preflighted = _r1b2_record(
        fixture, fixture["staged"], "PREFLIGHTED", 2, requested.record_hash
    )
    preflighted = ledger.append_recovery(
        preflighted,
        expected_tail=requested.record_hash,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=fixture["staged"].bundle_evidence,
    )
    target = _r1b2_record(
        fixture, fixture["staged"], "TARGET_READY", 3, preflighted.record_hash
    )
    ledger.append_recovery(
        target,
        expected_tail=preflighted.record_hash,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=fixture["staged"].bundle_evidence,
    )
    rows = ledger.read()
    rows[1][field] = replacement
    rows[1]["record_hash"] = canonical_hash({
        key: value for key, value in rows[1].items() if key != "record_hash"
    })
    rows[2]["parent_hash"] = rows[1]["record_hash"]
    rows[2]["record_hash"] = canonical_hash({
        key: value for key, value in rows[2].items() if key != "record_hash"
    })
    fixture["ledger_path"].write_bytes(
        b"".join(
            json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
            for row in rows
        )
    )
    with pytest.raises((g.GatewayContractError, g.LedgerCorruption)):
        ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=fixture["staged"].bundle_evidence,
        )


def test_r1b2_recovery_cas_tail_request_and_fence_conflicts_fail_closed(
    tmp_path, monkeypatch
):
    fixture = _r1b2_prepared_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    first = _r1b2_record(fixture, fixture["staged"], "REQUESTED", 1, "")
    first = ledger.append_recovery(
        first,
        expected_tail="",
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    )
    second = _r1b2_record(
        fixture, fixture["staged"], "PREFLIGHTED", 2, first.record_hash
    )
    for mutation, expected_tail in (
        ({"request_hash": "f" * 64}, first.record_hash),
        ({"idempotency_fence": "other-fence"}, first.record_hash),
        ({"request_id": "other-request"}, first.record_hash),
        ({}, "e" * 64),
    ):
        values = {**second.__dict__, **mutation}
        values["record_hash"] = __import__(
            "nexus.contracts.gateway_deployment",
            fromlist=["canonical_hash"],
        ).canonical_hash({
            key: value for key, value in values.items() if key != "record_hash"
        })
        with pytest.raises((g.GatewayContractError, g.LedgerCorruption)):
            ledger.append_recovery(
                second.__class__(**values),
                expected_tail=expected_tail,
                request=fixture["request"],
                receipt=fixture["receipt"],
                source_bundle_evidence=fixture["staged"].bundle_evidence,
            )
    assert len(ledger.read()) == 1


class _R1B2Crash(BaseException):
    pass


def _r1b2_runtime_fixture(tmp_path, monkeypatch):
    fixture = _r1b1_fixture(tmp_path, monkeypatch)
    fixture["ledger_path"] = fixture["state"] / "ledger.jsonl"
    fixture["lock_path"] = fixture["state"] / "ledger.lock"
    return fixture


def _production_health_opener(server_instance="pre-effect"):
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
        assert request.full_url.endswith("/health")
        return Response({"server_instance_id": server_instance})

    return opener


def test_r1_live_production_wrapper_and_plist_are_fixed_and_secret_free(
    tmp_path, monkeypatch
):
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(g, "INTERPRETER", "/Users/jameschen/Workspace/Nexus-new/.venv/bin/python")
    plan = g._recovery_plan(fixture["request"], fixture["receipt"])

    payload = plistlib.loads(g._recovery_expected_plist_bytes(plan.desired_root))
    assert payload["Label"] == g.GATEWAY_LABEL
    assert payload["ProgramArguments"] == [
        "/bin/zsh",
        "-c",
        g._recovery_wrapper_command(plan.desired_root),
    ]
    assert payload["WorkingDirectory"] == plan.desired_root
    assert "EnvironmentVariables" not in payload
    wrapper = payload["ProgramArguments"][2]
    assert "SECRET" not in wrapper
    assert "${NEXUS_MCP_GATEWAY_TOKEN}" not in wrapper
    assert "NEXUS_MCP_GATEWAY_TOKEN=" not in wrapper
    assert "devspace" not in wrapper.lower()
    assert g.GATEWAY_LABEL not in {g.LABELS.get("devspace"), "com.nexus.devspace"}

    with pytest.raises(g.GatewayContractError, match="root substitution"):
        g._recovery_expected_plist_bytes("/tmp/caller-selected")


def test_r1_live_production_effect_uses_only_fixed_gateway_launchctl_surface(
    tmp_path, monkeypatch
):
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    plan = g._recovery_plan(fixture["request"], fixture["receipt"])
    plist_path = tmp_path / "host" / "gateway.plist"
    plist_path.parent.mkdir(mode=0o700)
    monkeypatch.setattr(g, "GATEWAY_PLIST", plist_path)
    predecessor_bytes = g._recovery_expected_plist_bytes(plan.predecessor_root)
    desired_bytes = g._recovery_expected_plist_bytes(plan.desired_root)
    plist_path.write_bytes(predecessor_bytes)
    plist_path.chmod(0o600)
    calls = []

    def runner(*args):
        command = tuple(args)
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    adapters = g._production_recovery_adapters(
        fixture["receipt"],
        runner=runner,
        opener=_production_health_opener(),
        token_loader=lambda: "SECRET",
        sleeper=lambda _: None,
    )
    ack = adapters.effect(plan)

    assert ack.acknowledged is True
    assert ack.applied is True
    assert ack.already_desired is False
    assert calls == [
        ("launchctl", "bootout", f"{g.UID_TARGET}/{g.GATEWAY_LABEL}"),
        ("launchctl", "bootstrap", g.UID_TARGET, str(plist_path)),
    ]
    assert all("devspace" not in " ".join(call).lower() for call in calls)
    assert plist_path.read_bytes() == desired_bytes


def test_r1_live_production_bootstrap_failure_restores_exact_predecessor_only(
    tmp_path, monkeypatch
):
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    plan = g._recovery_plan(fixture["request"], fixture["receipt"])
    plist_path = tmp_path / "host" / "gateway.plist"
    plist_path.parent.mkdir(mode=0o700)
    monkeypatch.setattr(g, "GATEWAY_PLIST", plist_path)
    predecessor_bytes = g._recovery_expected_plist_bytes(plan.predecessor_root)
    desired_bytes = g._recovery_expected_plist_bytes(plan.desired_root)
    plist_path.write_bytes(predecessor_bytes)
    plist_path.chmod(0o600)
    calls = []
    bootstrap_payloads = []

    def runner(*args):
        command = tuple(args)
        calls.append(command)
        if command[:2] == ("launchctl", "bootstrap"):
            bootstrap_payloads.append(plist_path.read_bytes())
            return subprocess.CompletedProcess(
                command,
                1 if len(bootstrap_payloads) == 1 else 0,
                "",
                "desired bootstrap failed" if len(bootstrap_payloads) == 1 else "",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    adapters = g._production_recovery_adapters(
        fixture["receipt"],
        runner=runner,
        opener=_production_health_opener(),
        token_loader=lambda: "SECRET",
        sleeper=lambda _: None,
    )
    with pytest.raises(
        g.GatewayContractError,
        match="desired bootstrap failed; exact predecessor restoration attempted",
    ):
        adapters.effect(plan)

    assert calls == [
        ("launchctl", "bootout", f"{g.UID_TARGET}/{g.GATEWAY_LABEL}"),
        ("launchctl", "bootstrap", g.UID_TARGET, str(plist_path)),
        ("launchctl", "bootstrap", g.UID_TARGET, str(plist_path)),
    ]
    assert bootstrap_payloads == [desired_bytes, predecessor_bytes]
    assert plist_path.read_bytes() == predecessor_bytes


def test_r1_live_production_observation_rejects_unknown_plist_before_health(
    tmp_path, monkeypatch
):
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    plan = g._recovery_plan(fixture["request"], fixture["receipt"])
    plist_path = tmp_path / "host" / "gateway.plist"
    plist_path.parent.mkdir()
    plist_path.write_bytes(b"not-an-authorized-plist")
    monkeypatch.setattr(g, "GATEWAY_PLIST", plist_path)
    monkeypatch.setattr(
        g,
        "_launchctl_observation",
        lambda **_kwargs: {"loaded": True, "pid": 4321},
    )

    with pytest.raises(
        g.GatewayContractError, match="physical observation remained uncertain"
    ):
        g._recovery_observe_physical(
            plan,
            fixture["receipt"],
            runner=lambda *args: pytest.fail(f"unexpected runner call: {args}"),
            opener=lambda *_args, **_kwargs: pytest.fail("health must not run"),
            token_loader=lambda: "SECRET",
            sleeper=lambda _: None,
            retries=1,
        )


def test_r1_live_production_postflight_requires_changed_server_instance(
    tmp_path, monkeypatch
):
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    plan = g._recovery_plan(fixture["request"], fixture["receipt"])
    physical = _r1b2_physical_identity(
        fixture, "desired", server_instance="server-new"
    )
    tools = [
        {"name": "tool-a", "inputSchema": {"type": "object"}},
        {"name": "tool-b", "inputSchema": {"type": "object"}},
    ]
    manifest = hashlib.sha256(
        json.dumps(
            tuple(sorted(item["name"] for item in tools)),
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode()
    ).hexdigest()
    schema = hashlib.sha256(
        json.dumps(
            tools,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    expected = {
        "tool_manifest_sha256": manifest,
        "schema_sha256": schema,
        "permission_sha256": "a" * 64,
        "lifecycle": "nexus.lifecycle.gateway.v2",
        "tool_count": len(tools),
    }
    monkeypatch.setattr(g, "_recovery_expected_postflight", lambda _receipt: expected)
    health = {
        "server_instance_id": physical.server_instance,
        "repo_root": physical.root,
        "git_head": physical.head,
        "git_tree": physical.tree,
        "tool_manifest_revision": manifest,
        "full_tool_schema_hash": schema,
        "permission_policy_hash": expected["permission_sha256"],
        "lifecycle_revision": expected["lifecycle"],
    }
    server_info = {
        "serverInstanceId": physical.server_instance,
        "toolManifestRevision": manifest,
        "fullToolSchemaHash": schema,
        "permissionPolicyHash": expected["permission_sha256"],
        "lifecycleRevision": expected["lifecycle"],
    }
    postflight = g._recovery_live_postflight(
        plan,
        physical,
        fixture["receipt"],
        previous_server_instance=physical.server_instance,
        applied=True,
        opener=_surface_opener(health, server_info, tools),
        token_loader=lambda: "SECRET",
    )
    with pytest.raises(
        g.GatewayContractError, match="server instance did not change"
    ):
        g._validate_recovery_postflight(
            postflight, physical, fixture["receipt"]
        )


def _r1b2_physical_identity(fixture, role="desired", **changes):
    from nexus.contracts.gateway_deployment import (
        RecoveryPhysicalIdentity,
        canonical_hash,
    )

    receipt = fixture["receipt"]
    if role == "desired":
        manifest = receipt.desired_manifest
    elif role == "predecessor":
        manifest = receipt.predecessor_manifest
    elif role == "unknown":
        manifest = receipt.desired_manifest.__class__(**{
            **receipt.desired_manifest.__dict__,
            "deployment_id": "r1-" + "d" * 40,
            "commit": "e" * 40,
            "tree": "f" * 40,
        })
    else:
        raise AssertionError(role)
    root = str(g.GATEWAY_DEPLOYMENTS_ROOT / manifest.deployment_id)
    values = {
        "loaded": True,
        "service_label": g.GATEWAY_LABEL,
        "pid": 4321,
        "start_identity": "pid-4321-start-1",
        "listener": g.GATEWAY_ENDPOINT,
        "plist_sha256": g._recovery_expected_plist_sha256(root),
        "deployment_id": manifest.deployment_id,
        "root": root,
        "head": manifest.commit,
        "tree": manifest.tree,
        "server_instance": f"server-{role}",
        "observed_at": "2026-08-25T00:00:00Z",
        **changes,
    }
    return RecoveryPhysicalIdentity(
        **values, evidence_hash=canonical_hash(values)
    )


def _r1b2_postflight(fixture, physical, **changes):
    receipt = fixture["receipt"]
    expected = g._recovery_expected_postflight(receipt)
    canonical_surface = {
        "root": physical.root,
        "head": physical.head,
        "tree": physical.tree,
        "server_instance": physical.server_instance,
        "tool_manifest_sha256": expected["tool_manifest_sha256"],
        "schema_sha256": expected["schema_sha256"],
        "permission_sha256": expected["permission_sha256"],
        "lifecycle": expected["lifecycle"],
    }
    values = {
        "authenticated": True,
        "health": dict(canonical_surface),
        "initialize": dict(canonical_surface),
        "tools_list": {
            "tool_manifest_sha256": expected["tool_manifest_sha256"],
            "schema_sha256": expected["schema_sha256"],
            "tool_count": expected["tool_count"],
            "actions": tuple(f"tool-{index}" for index in range(expected["tool_count"])),
        },
        "previous_server_instance": None,
        "applied": False,
        **changes,
    }
    return values


def test_r1b2_expected_recovery_identities_are_derived_not_fixture_literals(
    tmp_path, monkeypatch
):
    first_root = tmp_path / "first"
    second_root = tmp_path / "second"
    first_root.mkdir()
    second_root.mkdir()
    first = _r1b1_fixture(first_root, monkeypatch, identity_seed="first")
    g.stage_verified_git_store(first["request"], first["receipt"])
    first_expected = g._recovery_expected_postflight(first["receipt"])
    first_root_path = str(
        Path(first["state"]) / "deployments" / first["receipt"].desired_manifest_id
    )
    first_plist_sha256 = g._recovery_expected_plist_sha256(first_root_path)

    second = _r1b1_fixture(second_root, monkeypatch, identity_seed="second")
    g.stage_verified_git_store(second["request"], second["receipt"])
    second_expected = g._recovery_expected_postflight(second["receipt"])
    second_root_path = str(
        Path(second["state"]) / "deployments" / second["receipt"].desired_manifest_id
    )

    assert first_expected != second_expected
    assert first_expected["permission_sha256"] != "2" * 64
    assert first_expected["schema_sha256"] != "3" * 64
    assert first_expected["lifecycle"] == "nexus.lifecycle.gateway.v2"
    assert first_expected["tool_count"] == 2
    assert first_plist_sha256 != "1" * 64
    assert first_plist_sha256 != g._recovery_expected_plist_sha256(second_root_path)


def _r1b2_durable_count(path, increment=0):
    path = Path(path)
    if not path.exists():
        path.write_text("0")
    with path.open("r+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        current = int(stream.read() or "0")
        if increment:
            current += increment
            stream.seek(0)
            stream.truncate()
            stream.write(str(current))
            stream.flush()
            os.fsync(stream.fileno())
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
    return current


def _r1b2_adapters(
    fixture,
    ledger,
    *,
    observe_role="desired",
    physical_changes=None,
    postflight_changes=None,
    already_desired=False,
    lost_ack=False,
    crash_point=None,
    effect_calls=None,
    external_calls=None,
    effect_count_path=None,
    external_count_path=None,
):
    from nexus.contracts.gateway_deployment import (
        RecoveryEffectAck,
        canonical_hash,
    )

    effect_calls = effect_calls if effect_calls is not None else []
    external_calls = external_calls if external_calls is not None else []
    physical = _r1b2_physical_identity(
        fixture, observe_role, **(physical_changes or {})
    )

    def observe(plan):
        assert plan.request_id == fixture["request"].request_id
        return physical

    def effect(plan):
        rows = g.GatewayLedger(
            ledger.path, lock_path=ledger.lock_path
        ).recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=None,
        )
        assert rows[-1].state == "EFFECT_STARTED"
        effect_calls.append(plan.plan_hash)
        if effect_count_path is not None:
            _r1b2_durable_count(effect_count_path, 1)
        if not already_desired:
            external_calls.append("fixed-effect")
            if external_count_path is not None:
                _r1b2_durable_count(external_count_path, 1)
        if lost_ack:
            raise TimeoutError("effect applied but acknowledgement was lost")
        ack_values = {
            "plan_hash": plan.plan_hash,
            "acknowledged": True,
            "applied": not already_desired,
            "already_desired": already_desired,
            "effect_kind": "GATEWAY_DURABLE_RECOVERY",
        }
        return RecoveryEffectAck(
            **ack_values, evidence_hash=canonical_hash(ack_values)
        )

    def postflight(plan, identity):
        assert plan.request_id == fixture["request"].request_id
        assert identity == physical
        return _r1b2_postflight(
            fixture, physical, **(postflight_changes or {})
        )

    def crash_hook(point):
        if point == crash_point:
            raise _R1B2Crash(point)

    return g._RecoveryAdapters(
        observe=observe,
        effect=effect,
        postflight=postflight,
        clock=lambda: "2026-08-25T00:00:00Z",
        crash_hook=crash_hook,
    )


@pytest.mark.parametrize(
    ("crash_point", "expected_state"),
    [
        ("after_bundle_evidence", "PREFLIGHTED"),
        ("after_target_ready", "TARGET_READY"),
        ("after_rollback_ready", "ROLLBACK_READY"),
        ("after_effect_started_before_call", "EFFECT_STARTED"),
        ("after_effect_call_before_ack", "EFFECT_STARTED"),
        ("after_effect_success_before_observation", "EFFECT_STARTED"),
        ("after_service_observed", "SERVICE_OBSERVED"),
        ("after_identity_verified", "IDENTITY_VERIFIED"),
        ("after_client_bound", "CLIENT_BOUND"),
    ],
)
def test_r1b2_crash_points_leave_only_complete_durable_rows(
    tmp_path, monkeypatch, crash_point, expected_state
):
    assert hasattr(g, "_RecoveryAdapters")
    assert hasattr(g, "_gateway_recover_with_adapters")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    effect_count = tmp_path / "durable-effect-count"
    external_count = tmp_path / "durable-external-count"
    adapters = _r1b2_adapters(
        fixture,
        ledger,
        crash_point=crash_point,
        effect_count_path=effect_count,
        external_count_path=external_count,
    )
    with pytest.raises(_R1B2Crash):
        g._gateway_recover_with_adapters(
            fixture["request"], adapters=adapters, ledger=ledger
        )
    raw = fixture["ledger_path"].read_bytes()
    assert raw.endswith(b"\n")
    rows = ledger.recovery_rows(
        fixture["request"].request_id,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    )
    assert rows[-1].state == expected_state
    readiness_points = {
        "after_bundle_evidence",
        "after_target_ready",
        "after_rollback_ready",
    }
    pre_call_points = {
        *readiness_points,
        "after_effect_started_before_call",
    }
    initial_calls = 0 if crash_point in pre_call_points else 1
    assert _r1b2_durable_count(effect_count) == initial_calls
    assert _r1b2_durable_count(external_count) == initial_calls
    if crash_point == "after_bundle_evidence":
        assert rows[-1].source_bundle_evidence_hash
        assert not g.GATEWAY_DEPLOYMENTS_ROOT.exists()
    prefix = fixture["ledger_path"].read_bytes()
    row_count = len(rows)
    replay = _r1b2_adapters(
        fixture,
        ledger,
        already_desired=True,
        effect_count_path=effect_count,
        external_count_path=external_count,
    )
    if crash_point not in readiness_points:
        replay = replay.__class__(
            observe=replay.observe,
            effect=lambda _plan: pytest.fail(
                "EFFECT_STARTED-or-later replay cannot invoke an effect seam"
            ),
            postflight=replay.postflight,
            clock=replay.clock,
            crash_hook=replay.crash_hook,
        )
    outcome = g._gateway_recover_with_adapters(
        fixture["request"], adapters=replay, ledger=ledger
    )
    assert outcome.result == "VERIFIED"
    assert fixture["ledger_path"].read_bytes().startswith(prefix)
    replay_rows = ledger.recovery_rows(
        fixture["request"].request_id,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    )
    assert replay_rows[:row_count] == rows
    assert replay_rows[-1].state == "VERIFIED"
    terminal_path = [
        "PREFLIGHTED",
        "TARGET_READY",
        "ROLLBACK_READY",
        "EFFECT_STARTED",
        "SERVICE_OBSERVED",
        "IDENTITY_VERIFIED",
        "CLIENT_BOUND",
        "VERIFIED",
    ]
    expected_suffix = terminal_path[
        terminal_path.index(expected_state) + 1:
    ]
    assert [row.state for row in replay_rows[row_count:]] == expected_suffix
    assert sum(row.state == "EFFECT_STARTED" for row in replay_rows) == 1
    if crash_point in readiness_points:
        assert _r1b2_durable_count(effect_count) == 1
        assert _r1b2_durable_count(external_count) == 0
    elif crash_point == "after_effect_started_before_call":
        assert _r1b2_durable_count(effect_count) == 0
        assert _r1b2_durable_count(external_count) == 0
    else:
        assert _r1b2_durable_count(effect_count) == 1
        assert _r1b2_durable_count(external_count) == 1
    expected_evidence_hash = next(
        row.source_bundle_evidence_hash
        for row in replay_rows
        if row.source_bundle_evidence_hash is not None
    )
    revalidated = g._revalidate_recovery_artifacts(
        fixture["request"],
        fixture["receipt"],
        expected_bundle_evidence_hash=expected_evidence_hash,
    )
    assert revalidated.bundle_evidence.evidence_hash == expected_evidence_hash
    for path, manifest in (
        (
            g.GATEWAY_DEPLOYMENTS_ROOT / fixture["receipt"].desired_manifest_id,
            fixture["receipt"].desired_manifest,
        ),
        (
            g.GATEWAY_DEPLOYMENTS_ROOT / fixture["receipt"].predecessor_manifest_id,
            fixture["receipt"].predecessor_manifest,
        ),
    ):
        assert g._r1_verify_worktree(path, manifest) == path


def test_r1b2_crash_partial_append_is_corruption_not_a_replayable_state(
    tmp_path, monkeypatch
):
    assert hasattr(g.GatewayLedger, "append_recovery")
    fixture = _r1b2_prepared_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    first = _r1b2_record(fixture, fixture["staged"], "REQUESTED", 1, "")
    ledger.append_recovery(
        first,
        expected_tail="",
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    )
    with fixture["ledger_path"].open("ab") as stream:
        stream.write(b'{"schema":"nexus.gateway.ledger.v2"')
        stream.flush()
        os.fsync(stream.fileno())
    with pytest.raises(g.LedgerCorruption):
        ledger.read()


def test_r1b2_recovery_cas_persists_bundle_evidence_before_promotion_and_missing_predecessor(
    tmp_path, monkeypatch
):
    assert hasattr(g, "_gateway_recover_with_adapters")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    materialize = g._r1_materialize_worktree
    effects = []

    def missing_predecessor(manifest):
        rows = ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=None,
        )
        assert rows[-1].source_bundle_evidence_hash
        if manifest.role == "predecessor":
            raise g.GatewayContractError("predecessor bytes missing")
        return materialize(manifest)

    monkeypatch.setattr(g, "_r1_materialize_worktree", missing_predecessor)
    adapters = _r1b2_adapters(
        fixture, ledger, effect_calls=effects
    )
    result = g._gateway_recover_with_adapters(
        fixture["request"], adapters=adapters, ledger=ledger
    )
    assert result.result == "BLOCKED"
    assert result.effect_started is False
    assert effects == []
    states = [
        row.state
        for row in ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=None,
        )
    ]
    assert states[-3:] == [
        "TARGET_READY", "ROLLBACK_UNAVAILABLE", "BLOCKED"
    ]


def test_r1b2_lost_ack_reopens_durable_effect_started_and_never_reapplies(
    tmp_path, monkeypatch
):
    assert hasattr(g, "_gateway_recover_with_adapters")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    effect_calls = []
    external_calls = []
    lost = _r1b2_adapters(
        fixture,
        ledger,
        lost_ack=True,
        effect_calls=effect_calls,
        external_calls=external_calls,
    )
    first = g._gateway_recover_with_adapters(
        fixture["request"], adapters=lost, ledger=ledger
    )
    assert first.result == "UNCERTAIN_EFFECT"
    assert len(effect_calls) == 1
    assert external_calls == ["fixed-effect"]
    assert ledger.current_recovery_state(
        fixture["request"].request_id,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    ) == "UNCERTAIN_EFFECT"

    def no_second_effect(_plan):
        pytest.fail("UNCERTAIN_EFFECT replay must never invoke a second effect")

    recovered = _r1b2_adapters(fixture, ledger)
    recovered = recovered.__class__(
        observe=recovered.observe,
        effect=no_second_effect,
        postflight=recovered.postflight,
        clock=recovered.clock,
        crash_hook=recovered.crash_hook,
    )
    second = g._gateway_recover_with_adapters(
        fixture["request"], adapters=recovered, ledger=ledger
    )
    assert second.result == "VERIFIED"
    states = [
        row.state
        for row in ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=None,
        )
    ]
    assert states.count("EFFECT_STARTED") == 1
    assert len(effect_calls) == 1
    assert external_calls == ["fixed-effect"]


@pytest.mark.parametrize(
    ("role", "changes", "postflight_changes", "expected"),
    [
        ("desired", {}, {}, "VERIFIED"),
        ("predecessor", {}, {}, "ROLLED_BACK"),
        ("unknown", {}, {}, "BLOCKED"),
        ("desired", {"loaded": False}, {}, "BLOCKED"),
        ("desired", {"service_label": "com.example.wrong"}, {}, "BLOCKED"),
        ("desired", {"pid": None}, {}, "BLOCKED"),
        ("desired", {"start_identity": ""}, {}, "BLOCKED"),
        ("desired", {"listener": "http://127.0.0.1:9999"}, {}, "BLOCKED"),
        (
            "desired",
            {"listener": {"endpoint": g.GATEWAY_ENDPOINT, "owner_pid": 9999}},
            {},
            "BLOCKED",
        ),
        (
            "desired",
            {"listener": [g.GATEWAY_ENDPOINT, "http://127.0.0.1:9999"]},
            {},
            "BLOCKED",
        ),
        ("desired", {"plist_sha256": "f" * 64}, {}, "BLOCKED"),
        ("desired", {"root": "/tmp/wrong-root"}, {}, "BLOCKED"),
        ("desired", {"head": "e" * 40}, {}, "BLOCKED"),
        ("desired", {"tree": "f" * 40}, {}, "BLOCKED"),
        ("desired", {"deployment_id": "r1-wrong-manifest"}, {}, "BLOCKED"),
        (
            "desired",
            {"server_instance": "wrong-server"},
            {"initialize": {"session_id": "recovery-session-1", "server_instance": "different-server"}},
            "BLOCKED",
        ),
        (
            "desired",
            {},
            {
                "tools_list": {
                    "session_id": "recovery-session-1",
                    "actions": ["gateway-rebind"],
                    "schema_hash": "f" * 64,
                }
            },
            "BLOCKED",
        ),
    ],
)
def test_r1b2_uncertain_reconcile_physical_matrix_never_reenters_effect(
    tmp_path, monkeypatch, role, changes, postflight_changes, expected
):
    assert hasattr(g, "_gateway_recover_with_adapters")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    effect_calls = []
    first = _r1b2_adapters(
        fixture, ledger, lost_ack=True, effect_calls=effect_calls
    )
    assert g._gateway_recover_with_adapters(
        fixture["request"], adapters=first, ledger=ledger
    ).result == "UNCERTAIN_EFFECT"

    retry = _r1b2_adapters(
        fixture,
        ledger,
        observe_role=role,
        physical_changes=changes,
        postflight_changes=postflight_changes,
    )
    retry = retry.__class__(
        observe=retry.observe,
        effect=lambda _plan: pytest.fail("reconcile cannot invoke effect"),
        postflight=retry.postflight,
        clock=retry.clock,
        crash_hook=retry.crash_hook,
    )
    outcome = g._gateway_recover_with_adapters(
        fixture["request"], adapters=retry, ledger=ledger
    )
    assert outcome.result == expected
    states = [
        row.state
        for row in ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=None,
        )
    ]
    assert states.count("EFFECT_STARTED") == 1
    assert len(effect_calls) == 1
    if expected != "VERIFIED":
        assert "VERIFIED" not in states
        assert states[-1] != "CLIENT_BOUND"


def test_r1b2_uncertain_ambiguous_identity_stays_blocked_without_effect(
    tmp_path, monkeypatch
):
    assert hasattr(g, "_gateway_reconcile_physical")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    desired = _r1b2_physical_identity(fixture, "desired")
    predecessor = _r1b2_physical_identity(fixture, "predecessor")
    with pytest.raises(g.GatewayContractError, match="ambiguous"):
        g._gateway_reconcile_physical(
            fixture["request"],
            fixture["receipt"],
            (desired, predecessor),
        )


def test_r1b2_already_desired_enters_durable_seam_with_zero_external_calls(
    tmp_path, monkeypatch
):
    assert hasattr(g, "_gateway_recover_with_adapters")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    seam_calls = []
    external_calls = []
    adapters = _r1b2_adapters(
        fixture,
        ledger,
        already_desired=True,
        effect_calls=seam_calls,
        external_calls=external_calls,
    )
    result = g._gateway_recover_with_adapters(
        fixture["request"], adapters=adapters, ledger=ledger
    )
    assert result.result == "VERIFIED"
    assert result.effect_started is True
    assert len(seam_calls) == 1
    assert external_calls == []
    rows = ledger.recovery_rows(
        fixture["request"].request_id,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    )
    assert [row.state for row in rows][-5:] == [
        "EFFECT_STARTED",
        "SERVICE_OBSERVED",
        "IDENTITY_VERIFIED",
        "CLIENT_BOUND",
        "VERIFIED",
    ]
    assert rows[-1].observed_identity["ack"] == {
        "acknowledged": True,
        "applied": False,
        "already_desired": True,
    }
    first_raw = fixture["ledger_path"].read_bytes()
    first_rows = tuple(rows)
    first_seam_count = len(seam_calls)
    repeat_adapters = _r1b2_adapters(
        fixture,
        ledger,
        already_desired=True,
        effect_calls=seam_calls,
        external_calls=external_calls,
    )
    repeat_adapters = repeat_adapters.__class__(
        observe=repeat_adapters.observe,
        effect=lambda _plan: pytest.fail(
            "terminal already-desired replay cannot enter the seam"
        ),
        postflight=repeat_adapters.postflight,
        clock=repeat_adapters.clock,
        crash_hook=repeat_adapters.crash_hook,
    )
    repeated = g._gateway_recover_with_adapters(
        fixture["request"], adapters=repeat_adapters, ledger=ledger
    )
    assert repeated == result
    assert repeated.evidence_hash == result.evidence_hash
    assert fixture["ledger_path"].read_bytes() == first_raw
    assert tuple(
        ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=None,
        )
    ) == first_rows
    assert len(seam_calls) == first_seam_count == 1
    assert external_calls == []


@pytest.mark.parametrize(
    "postflight_changes",
    [
        {"authenticated": False},
        {"health": {"deployment_id": "wrong"}},
        {"initialize": {"session_id": "other-session"}},
        {"tools_list": {"session_id": "other-session", "actions": ["gateway-rebind"]}},
        {"tools_list": {"session_id": "recovery-session-1", "actions": []}},
        {"tools_list": {"session_id": "recovery-session-1", "actions": ["gateway-rebind"], "schema_hash": "f" * 64}},
        {"initialize": {"session_id": "recovery-session-1", "permission_policy_hash": "f" * 64}},
    ],
    ids=[
        "unauthenticated",
        "health-identity",
        "initialize-session",
        "tools-session",
        "action-set",
        "schema",
        "permission",
    ],
)
def test_r1b2_authenticated_recovery_requires_health_initialize_tools_list_identity(
    tmp_path, monkeypatch, postflight_changes
):
    assert hasattr(g, "_gateway_recover_with_adapters")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    effect_count = tmp_path / "effect-count"
    external_count = tmp_path / "external-count"
    forbidden_calls = []
    for name in (
        "_provider_recovery_effect",
        "_devspace_recovery_effect",
        "_fallback_recovery_effect",
    ):
        monkeypatch.setattr(
            g,
            name,
            lambda *args, _name=name, **kwargs: forbidden_calls.append(_name),
            raising=False,
        )
    adapters = _r1b2_adapters(
        fixture,
        ledger,
        postflight_changes=postflight_changes,
        effect_count_path=effect_count,
        external_count_path=external_count,
    )
    outcome = g._gateway_recover_with_adapters(
        fixture["request"], adapters=adapters, ledger=ledger
    )
    assert outcome.result == "UNCERTAIN_EFFECT"
    assert _r1b2_durable_count(effect_count) <= 1
    assert _r1b2_durable_count(external_count) <= 1
    before_effect = _r1b2_durable_count(effect_count)
    before_external = _r1b2_durable_count(external_count)
    retry = _r1b2_adapters(
        fixture,
        ledger,
        postflight_changes=postflight_changes,
        effect_count_path=effect_count,
        external_count_path=external_count,
    )
    retry = retry.__class__(
        observe=retry.observe,
        effect=lambda _plan: pytest.fail(
            "authenticated reconciliation cannot invoke another effect"
        ),
        postflight=retry.postflight,
        clock=retry.clock,
        crash_hook=retry.crash_hook,
    )
    repeated = g._gateway_recover_with_adapters(
        fixture["request"], adapters=retry, ledger=ledger
    )
    assert repeated.result == "UNCERTAIN_EFFECT"
    assert _r1b2_durable_count(effect_count) == before_effect
    assert _r1b2_durable_count(external_count) == before_external
    assert forbidden_calls == []
    states = [
        row.state
        for row in ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=None,
        )
    ]
    assert "VERIFIED" not in states
    assert "CLIENT_BOUND" not in states
    assert states.count("EFFECT_STARTED") <= 1


def test_r1b2_authenticated_recovery_positive_binds_all_three_calls(
    tmp_path, monkeypatch
):
    assert hasattr(g, "_gateway_recover_with_adapters")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    adapters = _r1b2_adapters(fixture, ledger)
    outcome = g._gateway_recover_with_adapters(
        fixture["request"], adapters=adapters, ledger=ledger
    )
    assert outcome.result == "VERIFIED"
    assert ledger.current_recovery_state(
        fixture["request"].request_id,
        request=fixture["request"],
        receipt=fixture["receipt"],
        source_bundle_evidence=None,
    ) == "VERIFIED"


@pytest.mark.parametrize("target", ["bundle", "worktree", "evidence"])
def test_r1b2_uncertain_replay_tampered_artifacts_block_without_second_effect(
    tmp_path, monkeypatch, target
):
    assert hasattr(g, "_gateway_recover_with_adapters")
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    effect_calls = []
    first = _r1b2_adapters(
        fixture, ledger, lost_ack=True, effect_calls=effect_calls
    )
    assert g._gateway_recover_with_adapters(
        fixture["request"], adapters=first, ledger=ledger
    ).result == "UNCERTAIN_EFFECT"
    if target == "bundle":
        bundle = next(g.GATEWAY_SOURCE_BUNDLES_ROOT.glob("*.bundle"))
        bundle.write_bytes(bundle.read_bytes() + b"tamper")
    elif target == "worktree":
        desired = g.GATEWAY_DEPLOYMENTS_ROOT / fixture["receipt"].desired_manifest_id
        (desired / g.GATEWAY_ENTRYPOINT).write_text("tamper\n")
    else:
        rows = ledger.read()
        for row in reversed(rows):
            if row["schema"] == "nexus.gateway.ledger.v2":
                row["source_bundle_evidence_hash"] = "f" * 64
                row["record_hash"] = g._record_hash(row)
                break
        fixture["ledger_path"].write_bytes(
            b"".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")).encode() + b"\n"
                for row in rows
            )
        )
    retry = _r1b2_adapters(fixture, ledger)
    retry = retry.__class__(
        observe=retry.observe,
        effect=lambda _plan: pytest.fail("tampered replay cannot invoke effect"),
        postflight=retry.postflight,
        clock=retry.clock,
        crash_hook=retry.crash_hook,
    )
    with pytest.raises((g.GatewayContractError, g.LedgerCorruption)):
        g._gateway_recover_with_adapters(
            fixture["request"], adapters=retry, ledger=ledger
        )
    assert len(effect_calls) == 1


def test_r1b2_public_gateway_recover_remains_noninjectable_and_live_effect_unreachable(
    tmp_path, monkeypatch
):
    import inspect

    assert tuple(inspect.signature(g.gateway_recover).parameters) == ("request",)
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    forbidden_calls = []
    launchctl_calls = []
    plist = Path(g.GATEWAY_PLIST)
    plist_existed = plist.exists()
    plist_snapshot = plist.read_bytes() if plist_existed else None
    real_run = g.subprocess.run

    def guarded_subprocess(command, *args, **kwargs):
        executable = str(command[0]) if command else ""
        if Path(executable).name == "launchctl":
            launchctl_calls.append(tuple(command))
            raise AssertionError("public recovery cannot call launchctl")
        return real_run(command, *args, **kwargs)

    monkeypatch.setattr(g.subprocess, "run", guarded_subprocess)
    monkeypatch.setattr(
        g.os,
        "execve",
        lambda *args, **kwargs: pytest.fail("public recovery cannot exec"),
    )
    monkeypatch.setattr(
        g,
        "_default_recovery_effect",
        lambda *_args, **_kwargs: forbidden_calls.append("default-effect"),
        raising=False,
    )
    for name in (
        "_provider_recovery_effect",
        "_devspace_recovery_effect",
        "_fallback_recovery_effect",
    ):
        monkeypatch.setattr(
            g,
            name,
            lambda *args, _name=name, **kwargs: forbidden_calls.append(_name),
            raising=False,
        )
    outcome = g.gateway_recover(fixture["request"])
    assert outcome.result == "BLOCKED"
    assert outcome.effect_started is False
    assert forbidden_calls == []
    assert launchctl_calls == []
    assert plist.exists() is plist_existed
    if plist_existed:
        assert plist.read_bytes() == plist_snapshot


def test_r1b2_strict_ack_spoof_cannot_bypass_physical_and_postflight(
    tmp_path, monkeypatch
):
    from nexus.contracts.gateway_deployment import RecoveryEffectAck, canonical_hash

    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    adapters = _r1b2_adapters(fixture, ledger, observe_role="unknown")

    def spoofed_ack(plan):
        values = {
            "plan_hash": plan.plan_hash,
            "acknowledged": True,
            "applied": True,
            "already_desired": False,
            "effect_kind": "GATEWAY_DURABLE_RECOVERY",
        }
        return RecoveryEffectAck(
            **values, evidence_hash=canonical_hash(values)
        )

    adapters = adapters.__class__(
        observe=adapters.observe,
        effect=spoofed_ack,
        postflight=lambda *_args: pytest.fail("unknown identity cannot postflight"),
        clock=adapters.clock,
        crash_hook=adapters.crash_hook,
    )
    outcome = g._gateway_recover_with_adapters(
        fixture["request"], adapters=adapters, ledger=ledger
    )
    assert outcome.result == "BLOCKED"
    assert "VERIFIED" not in [
        row.state
        for row in ledger.recovery_rows(
            fixture["request"].request_id,
            request=fixture["request"],
            receipt=fixture["receipt"],
            source_bundle_evidence=None,
        )
    ]


@pytest.mark.parametrize(
    "drift",
    ["bundle", "worktree", "evidence", "physical", "postflight"],
)
def test_r1b2_verified_terminal_replay_revalidates_all_artifacts(
    tmp_path, monkeypatch, drift
):
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    adapters = _r1b2_adapters(fixture, ledger)
    terminal = g._gateway_recover_with_adapters(
        fixture["request"], adapters=adapters, ledger=ledger
    )
    assert terminal.result == "VERIFIED"
    if drift == "bundle":
        bundle = next(g.GATEWAY_SOURCE_BUNDLES_ROOT.glob("*.bundle"))
        bundle.write_bytes(bundle.read_bytes() + b"drift")
    elif drift == "worktree":
        entrypoint = (
            g.GATEWAY_DEPLOYMENTS_ROOT
            / fixture["receipt"].desired_manifest_id
            / g.GATEWAY_ENTRYPOINT
        )
        entrypoint.write_text("drift\n")
    elif drift == "evidence":
        rows = ledger.read()
        rows[-1]["source_bundle_evidence_hash"] = "f" * 64
        rows[-1]["record_hash"] = g._record_hash(rows[-1])
        fixture["ledger_path"].write_bytes(
            b"".join(
                json.dumps(row, sort_keys=True, separators=(",", ":")).encode()
                + b"\n"
                for row in rows
            )
        )
    replay = _r1b2_adapters(
        fixture,
        ledger,
        physical_changes={"root": "/tmp/drift"} if drift == "physical" else None,
        postflight_changes=(
            {"authenticated": False} if drift == "postflight" else None
        ),
    )
    replay = replay.__class__(
        observe=replay.observe,
        effect=lambda _plan: pytest.fail("terminal replay cannot invoke effect"),
        postflight=replay.postflight,
        clock=replay.clock,
        crash_hook=replay.crash_hook,
    )
    with pytest.raises((g.GatewayContractError, g.LedgerCorruption)):
        g._gateway_recover_with_adapters(
            fixture["request"], adapters=replay, ledger=ledger
        )


def test_r1b2_rolled_back_terminal_revalidates_predecessor(tmp_path, monkeypatch):
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    lost = _r1b2_adapters(fixture, ledger, lost_ack=True)
    assert g._gateway_recover_with_adapters(
        fixture["request"], adapters=lost, ledger=ledger
    ).result == "UNCERTAIN_EFFECT"
    predecessor = _r1b2_adapters(
        fixture, ledger, observe_role="predecessor"
    )
    predecessor = predecessor.__class__(
        observe=predecessor.observe,
        effect=lambda _plan: pytest.fail("rollback reconcile cannot effect"),
        postflight=predecessor.postflight,
        clock=predecessor.clock,
        crash_hook=predecessor.crash_hook,
    )
    terminal = g._gateway_recover_with_adapters(
        fixture["request"], adapters=predecessor, ledger=ledger
    )
    assert terminal.result == "ROLLED_BACK"
    entrypoint = (
        g.GATEWAY_DEPLOYMENTS_ROOT
        / fixture["receipt"].predecessor_manifest_id
        / g.GATEWAY_ENTRYPOINT
    )
    entrypoint.write_text("drift\n")
    with pytest.raises(g.GatewayContractError):
        g._gateway_recover_with_adapters(
            fixture["request"], adapters=predecessor, ledger=ledger
        )


def test_r1b2_blocked_terminal_does_not_reenter_physical_or_effect(
    tmp_path, monkeypatch
):
    fixture = _r1b2_runtime_fixture(tmp_path, monkeypatch)
    ledger = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    )
    materialize = g._r1_materialize_worktree

    def missing_predecessor(manifest):
        if manifest.role == "predecessor":
            raise g.GatewayContractError("missing predecessor")
        return materialize(manifest)

    monkeypatch.setattr(g, "_r1_materialize_worktree", missing_predecessor)
    adapters = _r1b2_adapters(fixture, ledger)
    terminal = g._gateway_recover_with_adapters(
        fixture["request"], adapters=adapters, ledger=ledger
    )
    assert terminal.result == "BLOCKED"
    bundle = next(g.GATEWAY_SOURCE_BUNDLES_ROOT.glob("*.bundle"))
    bundle.write_bytes(bundle.read_bytes() + b"drift")
    blocked_replay = adapters.__class__(
        observe=lambda _plan: pytest.fail("BLOCKED replay cannot observe"),
        effect=lambda _plan: pytest.fail("BLOCKED replay cannot effect"),
        postflight=lambda *_args: pytest.fail("BLOCKED replay cannot postflight"),
        clock=adapters.clock,
        crash_hook=adapters.crash_hook,
    )
    assert g._gateway_recover_with_adapters(
        fixture["request"], adapters=blocked_replay, ledger=ledger
    ) == terminal


def _r1b2_runtime_payload(fixture):
    return {
        "INTERPRETER": sys.executable,
        "HOST_AUTHORITY_SOURCE_ROOT": str(fixture["mirror"]),
        "HOST_AUTHORITY_REMOTE": str(fixture["mirror"]),
        "HOST_AUTHORITY_UID": os.getuid(),
        "HOST_UID": os.getuid(),
        "HOST_GID": os.getgid(),
        "GATEWAY_STATE_ROOT": str(fixture["state"]),
        "GATEWAY_SOURCE_BUNDLES_ROOT": str(
            fixture["state"] / "source-bundles"
        ),
        "GATEWAY_PREDECESSOR_ARTIFACT_ROOT": str(
            fixture["state"] / "predecessor-artifacts"
        ),
        "GATEWAY_REPOSITORY": str(fixture["state"] / "repository.git"),
        "GATEWAY_DEPLOYMENTS_ROOT": str(fixture["state"] / "deployments"),
        "GATEWAY_RECOVERY_AUTHORITY_STORE": str(
            fixture["state"] / "recovery-authority.json"
        ),
        "GATEWAY_LOCK": str(fixture["lock_path"]),
    }


def _r1b2_apply_runtime_payload(payload):
    from nexus.contracts.gateway_deployment import InterpreterIdentity

    path_names = {
        "HOST_AUTHORITY_SOURCE_ROOT",
        "GATEWAY_STATE_ROOT",
        "GATEWAY_SOURCE_BUNDLES_ROOT",
        "GATEWAY_PREDECESSOR_ARTIFACT_ROOT",
        "GATEWAY_REPOSITORY",
        "GATEWAY_DEPLOYMENTS_ROOT",
        "GATEWAY_RECOVERY_AUTHORITY_STORE",
        "GATEWAY_LOCK",
    }
    for name, value in payload.items():
        setattr(g, name, Path(value) if name in path_names else value)
    g._r1_interpreter_identity = lambda: InterpreterIdentity()
    g._r1_import_bundle = _r1b2_portable_import_bundle
    g.os.lstat = _r1b2_portable_lstat


def _r1b2_mp_recovery_worker(
    request,
    receipt,
    ledger_path,
    lock_path,
    runtime_payload,
    barrier,
    effect_count_path,
    effect_delay,
    physical,
    postflight,
    result_queue,
):
    from nexus.contracts.gateway_deployment import RecoveryEffectAck, canonical_hash

    _r1b2_apply_runtime_payload(runtime_payload)
    ledger = g.GatewayLedger(Path(ledger_path), lock_path=Path(lock_path))

    def observe(_plan):
        return physical

    def effect(plan):
        reopened = g.GatewayLedger(Path(ledger_path), lock_path=Path(lock_path))
        rows = reopened.recovery_rows(
            request.request_id,
            request=request,
            receipt=receipt,
            source_bundle_evidence=None,
        )
        assert rows[-1].state == "EFFECT_STARTED"
        with Path(effect_count_path).open("r+") as stream:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
            current = int(stream.read() or "0")
            stream.seek(0)
            stream.truncate()
            stream.write(str(current + 1))
            stream.flush()
            os.fsync(stream.fileno())
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
        if effect_delay:
            time.sleep(effect_delay)
        values = {
            "plan_hash": plan.plan_hash,
            "acknowledged": True,
            "applied": True,
            "already_desired": False,
            "effect_kind": "GATEWAY_DURABLE_RECOVERY",
        }
        return RecoveryEffectAck(
            **values, evidence_hash=canonical_hash(values)
        )

    adapters = g._RecoveryAdapters(
        observe=observe,
        effect=effect,
        postflight=lambda _plan, _identity: postflight,
        clock=lambda: "2026-08-25T00:00:00Z",
        crash_hook=lambda _point: None,
    )
    barrier.wait(timeout=10)
    try:
        outcome = g._gateway_recover_with_adapters(
            request, adapters=adapters, ledger=ledger
        )
        result_queue.put(("ok", outcome.result, outcome.evidence_hash))
    except BaseException as exc:
        result_queue.put(("error", type(exc).__name__, str(exc)))


def _r1b2_mp_append_worker(
    record,
    request,
    receipt,
    evidence,
    runtime_payload,
    ledger_path,
    lock_path,
    barrier,
    result_queue,
):
    _r1b2_apply_runtime_payload(runtime_payload)
    ledger = g.GatewayLedger(Path(ledger_path), lock_path=Path(lock_path))
    barrier.wait(timeout=10)
    try:
        ledger.append_recovery(
            record,
            expected_tail="",
            request=request,
            receipt=receipt,
            source_bundle_evidence=evidence,
        )
        result_queue.put("winner")
    except (g.GatewayContractError, g.LedgerCorruption):
        result_queue.put("blocked")


def _r1b2_fork_lock_worker(lock_path, result_queue):
    try:
        with g.InterProcessLock(Path(lock_path), timeout=0.1):
            result_queue.put("acquired")
    except g.GatewayContractError:
        result_queue.put("blocked")


def _r1b2_slow_owner_worker(
    request,
    receipt,
    ledger_path,
    lock_path,
    runtime_payload,
    physical,
    postflight,
    entered,
    effect_count_path,
    result_queue,
):
    from nexus.contracts.gateway_deployment import RecoveryEffectAck, canonical_hash

    _r1b2_apply_runtime_payload(runtime_payload)
    ledger = g.GatewayLedger(Path(ledger_path), lock_path=Path(lock_path))

    def effect(plan):
        _r1b2_durable_count(effect_count_path, 1)
        entered.set()
        time.sleep(g.RECOVERY_OWNER_COMPLETION_SECONDS + 5)
        values = {
            "plan_hash": plan.plan_hash,
            "acknowledged": True,
            "applied": True,
            "already_desired": False,
            "effect_kind": "GATEWAY_DURABLE_RECOVERY",
        }
        return RecoveryEffectAck(
            **values, evidence_hash=canonical_hash(values)
        )

    adapters = g._RecoveryAdapters(
        observe=lambda _plan: physical,
        effect=effect,
        postflight=lambda _plan, _identity: postflight,
        clock=lambda: "2026-08-25T00:00:00Z",
        crash_hook=lambda _point: None,
    )
    outcome = g._gateway_recover_with_adapters(
        request, adapters=adapters, ledger=ledger
    )
    result_queue.put((outcome.result, outcome.evidence_hash))


def _r1b2_slow_contender_worker(
    request,
    receipt,
    ledger_path,
    lock_path,
    runtime_payload,
    physical,
    postflight,
    contender_effect_count_path,
    result_queue,
):
    _r1b2_apply_runtime_payload(runtime_payload)
    ledger = g.GatewayLedger(Path(ledger_path), lock_path=Path(lock_path))

    def forbidden_effect(_plan):
        _r1b2_durable_count(contender_effect_count_path, 1)
        raise AssertionError("live-owner contender cannot invoke effect")

    adapters = g._RecoveryAdapters(
        observe=lambda _plan: physical,
        effect=forbidden_effect,
        postflight=lambda _plan, _identity: postflight,
        clock=lambda: "2026-08-25T00:00:00Z",
        crash_hook=lambda _point: None,
    )
    outcome = g._gateway_recover_with_adapters(
        request, adapters=adapters, ledger=ledger
    )
    result_queue.put((outcome.result, outcome.evidence_hash))


def test_r1b2_recovery_concurrent_real_multiprocessing_exactly_one_effect_repeat_three(
    tmp_path, monkeypatch
):
    assert hasattr(g, "_RecoveryAdapters")
    assert hasattr(g, "_gateway_recover_with_adapters")
    context = multiprocessing.get_context("spawn")
    for repeat in range(5):
        repeat_root = tmp_path / f"repeat-{repeat}"
        repeat_root.mkdir()
        fixture = _r1b2_prepared_fixture(repeat_root, monkeypatch)
        physical = _r1b2_physical_identity(fixture, "desired")
        postflight = _r1b2_postflight(fixture, physical)
        runtime_payload = _r1b2_runtime_payload(fixture)
        effect_count = repeat_root / "effect-count"
        effect_count.write_text("0")
        barrier = context.Barrier(2)
        result_queue = context.Queue()
        processes = [
            context.Process(
                target=_r1b2_mp_recovery_worker,
                args=(
                    fixture["request"],
                    fixture["receipt"],
                    str(fixture["ledger_path"]),
                    str(fixture["lock_path"]),
                    runtime_payload,
                    barrier,
                    str(effect_count),
                    0.75,
                    physical,
                    postflight,
                    result_queue,
                ),
            )
            for _ in range(2)
        ]
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
        results = [result_queue.get(timeout=2) for _ in processes]
        assert {item[0] for item in results} == {"ok"}, results
        assert {item[1] for item in results} == {"VERIFIED"}
        assert len({item[2] for item in results}) == 1
        assert effect_count.read_text() == "1"
        ledger = g.GatewayLedger(
            fixture["ledger_path"], lock_path=fixture["lock_path"]
        )
        states = [
            row.state
            for row in ledger.recovery_rows(
                fixture["request"].request_id,
                request=fixture["request"],
                receipt=fixture["receipt"],
                source_bundle_evidence=None,
            )
        ]
        assert states.count("EFFECT_STARTED") == 1
        assert states[-1] == "VERIFIED"


def _r1b2_conflicting_context(fixture):
    from nexus.contracts.gateway_deployment import canonical_hash

    receipt = fixture["receipt"]
    receipt_values = {
        **receipt.__dict__,
        "receipt_id": "receipt-conflict",
        "request_id": "request-conflict",
    }
    receipt_values["receipt_hash"] = canonical_hash({
        key: value for key, value in receipt_values.items() if key != "receipt_hash"
    })
    conflicting_receipt = receipt.__class__(**receipt_values)
    request = fixture["request"]
    request_values = {
        **request.__dict__,
        "request_id": conflicting_receipt.request_id,
        "recovery_authority_id": conflicting_receipt.receipt_id,
        "recovery_authority_hash": conflicting_receipt.receipt_hash,
    }
    request_values["request_hash"] = canonical_hash({
        key: value for key, value in request_values.items()
        if key not in {"request_hash", "schema"}
    })
    conflicting_request = request.__class__(**request_values)
    evidence = fixture["staged"].bundle_evidence
    evidence_values = {
        **evidence.__dict__,
        "request_id": conflicting_request.request_id,
        "request_hash": conflicting_request.request_hash,
        "receipt_id": conflicting_receipt.receipt_id,
        "receipt_hash": conflicting_receipt.receipt_hash,
    }
    evidence_values["evidence_hash"] = canonical_hash({
        key: value for key, value in evidence_values.items() if key != "evidence_hash"
    })
    conflicting_evidence = evidence.__class__(**evidence_values)
    return conflicting_request, conflicting_receipt, conflicting_evidence


def test_r1b2_recovery_concurrent_conflicting_fence_has_one_winner(
    tmp_path, monkeypatch
):
    assert hasattr(g.GatewayLedger, "append_recovery")
    fixture = _r1b2_prepared_fixture(tmp_path, monkeypatch)
    other_request, other_receipt, other_evidence = _r1b2_conflicting_context(fixture)
    first = _r1b2_record(
        fixture, fixture["staged"], "REQUESTED", 1, ""
    )
    other_fixture = {
        **fixture,
        "request": other_request,
        "receipt": other_receipt,
    }
    other_staged = SimpleNamespace(bundle_evidence=other_evidence)
    second = _r1b2_record(
        other_fixture, other_staged, "REQUESTED", 1, ""
    )
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    result_queue = context.Queue()
    inputs = (
        (
            first, fixture["request"], fixture["receipt"], None,
        ),
        (second, other_request, other_receipt, None),
    )
    processes = [
        context.Process(
            target=_r1b2_mp_append_worker,
            args=(
                record,
                request,
                receipt,
                evidence,
                _r1b2_runtime_payload(fixture),
                str(fixture["ledger_path"]),
                str(fixture["lock_path"]),
                barrier,
                result_queue,
            ),
        )
        for record, request, receipt, evidence in inputs
    ]
    for process in processes:
        process.start()
    for process in processes:
        process.join(timeout=20)
        assert process.exitcode == 0
    assert sorted(result_queue.get(timeout=2) for _ in processes) == [
        "blocked", "winner"
    ]
    rows = g.GatewayLedger(
        fixture["ledger_path"], lock_path=fixture["lock_path"]
    ).read()
    assert len(rows) == 1
    assert rows[0]["schema"] == "nexus.gateway.ledger.v2"
    assert rows[0]["state"] == "REQUESTED"
    assert rows[0]["sequence"] == 1
    assert rows[0]["parent_hash"] == ""
    assert rows[0]["source_bundle_evidence_hash"] is None
    assert rows[0]["request_id"] in {
        fixture["request"].request_id, other_request.request_id,
    }
    assert rows[0]["idempotency_fence"] == fixture["request"].idempotency_fence


def test_r1b2_interprocess_lock_reentry_is_context_local_and_threads_block(
    tmp_path, monkeypatch
):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    state.chmod(0o700)
    monkeypatch.setattr(g, "HOST_UID", os.getuid())
    lock_path = state / "lock"
    flock_calls = []
    real_flock = g.fcntl.flock

    def observed_flock(fd, operation):
        flock_calls.append(operation)
        return real_flock(fd, operation)

    monkeypatch.setattr(g.fcntl, "flock", observed_flock)
    barrier = threading.Barrier(2)
    result = []
    with g.InterProcessLock(lock_path):
        with g.InterProcessLock(lock_path):
            assert sum(
                bool(operation & fcntl.LOCK_EX) for operation in flock_calls
            ) == 1

        def contender():
            barrier.wait(timeout=2)
            try:
                with g.InterProcessLock(lock_path, timeout=0.1):
                    result.append("acquired")
            except g.GatewayContractError:
                result.append("blocked")

        thread = threading.Thread(target=contender)
        thread.start()
        barrier.wait(timeout=2)
        thread.join(timeout=2)
    assert result == ["blocked"]


@pytest.mark.filterwarnings("ignore:lance is not fork-safe")
@pytest.mark.filterwarnings("ignore:This process .*multi-threaded.*:DeprecationWarning")
def test_r1b2_interprocess_lock_fork_child_resets_inherited_reentry(
    tmp_path, monkeypatch
):
    state = tmp_path / "state"
    state.mkdir(mode=0o700)
    state.chmod(0o700)
    monkeypatch.setattr(g, "HOST_UID", os.getuid())
    lock_path = state / "lock"
    context = multiprocessing.get_context("fork")
    result_queue = context.Queue()
    with g.InterProcessLock(lock_path):
        process = context.Process(
            target=_r1b2_fork_lock_worker,
            args=(str(lock_path), result_queue),
        )
        process.start()
        process.join(timeout=5)
        assert process.exitcode == 0
        assert result_queue.get(timeout=2) == "blocked"


def test_r1b2_live_effect_owner_timeout_returns_uncertain_without_contender_effect(
    tmp_path, monkeypatch
):
    context = multiprocessing.get_context("spawn")
    fixture = _r1b2_prepared_fixture(tmp_path, monkeypatch)
    payload = _r1b2_runtime_payload(fixture)
    physical = _r1b2_physical_identity(fixture, "desired")
    postflight = _r1b2_postflight(fixture, physical)
    owner_effect_count = tmp_path / "owner-effect-count"
    contender_effect_count = tmp_path / "contender-effect-count"
    owner_effect_count.write_text("0")
    contender_effect_count.write_text("0")
    entered = context.Event()
    owner_results = context.Queue()
    contender_results = context.Queue()
    owner = context.Process(
        target=_r1b2_slow_owner_worker,
        args=(
            fixture["request"],
            fixture["receipt"],
            str(fixture["ledger_path"]),
            str(fixture["lock_path"]),
            payload,
            physical,
            postflight,
            entered,
            str(owner_effect_count),
            owner_results,
        ),
    )
    owner.start()
    assert entered.wait(timeout=20)
    safe_rows = len(g.GatewayLedger(fixture["ledger_path"]).read())
    contender = context.Process(
        target=_r1b2_slow_contender_worker,
        args=(
            fixture["request"],
            fixture["receipt"],
            str(fixture["ledger_path"]),
            str(fixture["lock_path"]),
            payload,
            physical,
            postflight,
            str(contender_effect_count),
            contender_results,
        ),
    )
    contender_started = time.monotonic()
    contender.start()
    contender.join(timeout=10)
    contender_elapsed = time.monotonic() - contender_started
    assert contender.exitcode == 0
    assert contender_results.get(timeout=2)[0] == "UNCERTAIN_EFFECT"
    assert contender_elapsed < g.RECOVERY_OWNER_COMPLETION_SECONDS + 4
    assert _r1b2_durable_count(contender_effect_count) == 0
    assert len(g.GatewayLedger(fixture["ledger_path"]).read()) == safe_rows
    owner.join(timeout=20)
    assert owner.exitcode == 0
    assert owner_results.get(timeout=2)[0] == "VERIFIED"
    assert _r1b2_durable_count(owner_effect_count) == 1
    terminal_results = context.Queue()
    terminal_reopen = context.Process(
        target=_r1b2_slow_contender_worker,
        args=(
            fixture["request"],
            fixture["receipt"],
            str(fixture["ledger_path"]),
            str(fixture["lock_path"]),
            payload,
            physical,
            postflight,
            str(contender_effect_count),
            terminal_results,
        ),
    )
    terminal_reopen.start()
    terminal_reopen.join(timeout=20)
    assert terminal_reopen.exitcode == 0
    assert terminal_results.get(timeout=2)[0] == "VERIFIED"
    assert _r1b2_durable_count(contender_effect_count) == 0
