"""Fail-closed regression for single ownership of critical Nexus effects (#947).

This is test-only architecture evidence, never runtime routing/authority.  It
scans all production Python under nexus/** and scripts/ops/**, binds exact
caller/sink identities, and detects effect primitives even when a duplicate is
placed in a new file under a different function name.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal

Label = Literal["CANONICAL", "COMPATIBILITY_ONLY", "RETIRED"]


@dataclass(frozen=True)
class Ref:
    path: str
    cls: str | None
    fn: str
    label: Label = "CANONICAL"

    @property
    def id(self) -> str:
        return f"{self.path}:{self.cls + '.' if self.cls else ''}{self.fn}"


@dataclass(frozen=True)
class Record:
    path: str
    cls: str | None
    fn: str
    node: ast.FunctionDef | ast.AsyncFunctionDef

    @property
    def id(self) -> str:
        return f"{self.path}:{self.cls + '.' if self.cls else ''}{self.fn}"


MERGE_PORT = Ref("nexus/orchestrator/github_completion_loop.py", "GitHubCompletionPort", "cas_merge")
MERGE_LOOP = Ref("nexus/orchestrator/github_completion_loop.py", None, "run_github_completion_loop")
CANDIDATE_FACADE = Ref("nexus/orchestrator/self_hosted_task_service.py", "SelfHostedTaskService", "integrate_approved")
CANDIDATE_SINK = Ref("nexus/orchestrator/governed_integration.py", "ControlledIntegrationManager", "integrate_authorized_task_state")
LEGACY_INTEGRATION = Ref("nexus/orchestrator/governed_integration.py", "ControlledIntegrationManager", "integrate_task_state", "RETIRED")
UNIFIED_CALLER = Ref("nexus/orchestrator/unified_mcp_gateway.py", "UnifiedMCPGateway", "_candidate_integrate", "COMPATIBILITY_ONLY")
SELF_HOSTED_CALLER = Ref("nexus/orchestrator/self_hosted_mcp.py", "NexusSelfHostedMCPServer", "_call_tool", "COMPATIBILITY_ONLY")
GATEWAY_MODULE = "scripts/ops/mcp_gateway_durable.py"
GATEWAY_MANAGER = Ref(GATEWAY_MODULE, None, "manage")
TRANSITION_SINK = Ref("nexus/orchestrator/standing_grant_store.py", None, "_write_transition_file")
SWITCH_CALLER = Ref("nexus/orchestrator/standing_grant_store.py", None, "switch_task_card_authority", "COMPATIBILITY_ONLY")
RESTORE_CALLER = Ref("nexus/orchestrator/standing_grant_store.py", None, "restore_task_card_authority", "COMPATIBILITY_ONLY")

DECLARED = (
    MERGE_PORT,
    MERGE_LOOP,
    CANDIDATE_FACADE,
    CANDIDATE_SINK,
    LEGACY_INTEGRATION,
    UNIFIED_CALLER,
    SELF_HOSTED_CALLER,
    GATEWAY_MANAGER,
    TRANSITION_SINK,
    SWITCH_CALLER,
    RESTORE_CALLER,
)

EDGES = (
    (MERGE_LOOP, "port.cas_merge"),
    (UNIFIED_CALLER, "self.service.integrate_approved"),
    (SELF_HOSTED_CALLER, "self.service.integrate_approved"),
    (CANDIDATE_FACADE, "ControlledIntegrationManager().integrate_authorized_task_state"),
    (SWITCH_CALLER, "_write_transition_file"),
    (RESTORE_CALLER, "_write_transition_file"),
)


def _files(root: Path) -> tuple[Path, ...]:
    found: list[Path] = []
    for rel in (Path("nexus"), Path("scripts/ops")):
        base = root / rel
        if not base.is_dir():
            raise AssertionError(f"PRODUCTION_SCAN_ROOT_MISSING:{rel.as_posix()}")
        found.extend(p for p in base.rglob("*.py") if not any(x in {".git", ".venv", "__pycache__", "node_modules"} for x in p.parts))
    return tuple(sorted(found, key=lambda p: p.relative_to(root).as_posix()))


def _parse(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise AssertionError(f"SOURCE_UNPARSEABLE:{path}:{exc}") from exc


def _records(path: Path, root: Path | None) -> tuple[Record, ...]:
    rel = path.relative_to(root).as_posix() if root is not None else str(path)
    out: list[Record] = []
    for node in _parse(path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(Record(rel, None, node.name, node))
        elif isinstance(node, ast.ClassDef):
            out.extend(Record(rel, node.name, x.name, x) for x in node.body if isinstance(x, (ast.FunctionDef, ast.AsyncFunctionDef)))
    return tuple(out)


def _all(root: Path, extra: Iterable[Path] = ()) -> tuple[Record, ...]:
    out = [r for p in _files(root) for r in _records(p, root)]
    out.extend(r for p in extra for r in _records(p, None))
    return tuple(out)


def _get(root: Path, ref: Ref) -> Record:
    path = root / ref.path
    if not path.is_file():
        raise AssertionError(f"DECLARED_SYMBOL_FILE_MISSING:{ref.id}")
    for record in _records(path, root):
        if (record.cls, record.fn) == (ref.cls, ref.fn):
            return record
    raise AssertionError(f"DECLARED_SYMBOL_MISSING:{ref.id}")


def _expr(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = _expr(node.value)
        return f"{base}.{node.attr}" if base else node.attr
    if isinstance(node, ast.Call):
        base = _expr(node.func)
        return f"{base}()" if base else None
    return None


def _calls(record: Record) -> tuple[str, ...]:
    return tuple(x for n in ast.walk(record.node) if isinstance(n, ast.Call) and (x := _expr(n.func)))


def _tail(call: str) -> str:
    return call.rsplit(".", 1)[-1].removesuffix("()")


def _strings(record: Record) -> frozenset[str]:
    return frozenset(n.value for n in ast.walk(record.node) if isinstance(n, ast.Constant) and isinstance(n.value, str))


def _raise(effect: str, reason: str, rows: Iterable[Record]) -> None:
    ids = sorted({r.id for r in rows})
    if ids:
        raise AssertionError(f"DUPLICATE_EFFECT_IMPLEMENTATION:{effect}:{reason}:" + ",".join(ids))


def verify(root: Path, *, extra: Iterable[Path] = ()) -> dict[str, object]:
    root = root.resolve()
    for ref in DECLARED:
        _get(root, ref)
    for caller, expected in EDGES:
        row = _get(root, caller)
        if expected not in _calls(row):
            raise AssertionError(f"DELEGATION_EDGE_MISSING:{caller.id}->{expected};observed={sorted(_calls(row))}")

    rows = _all(root, extra)

    # Retired legacy Candidate integration code may remain for compatibility,
    # but production code must not call it.
    _raise(
        "candidate_integration",
        f"RETIRED_SYMBOL_CALLED:{LEGACY_INTEGRATION.id}",
        (r for r in rows if r.id != LEGACY_INTEGRATION.id and any(_tail(c) == "integrate_task_state" for c in _calls(r))),
    )

    # GitHub merge: one in-repo CAS boundary.  Different names that bypass it
    # through direct merge connector primitives are rejected too.
    _raise(
        "protected_github_merge",
        "DIRECT_OR_SECOND_CAS_MERGE",
        (
            r
            for r in rows
            if (
                any(_tail(c) == "cas_merge" for c in _calls(r))
                and r.id != MERGE_LOOP.id
            )
            or any(_tail(c) in {"merge_pull_request", "git_merge_pull_request"} for c in _calls(r))
        ),
    )

    # Candidate integration: the façade alone may invoke the physical manager;
    # raw Git apply primitives may live only in the canonical physical sink or
    # the explicitly RETIRED legacy seam.
    allowed_git_apply = {CANDIDATE_SINK.id, LEGACY_INTEGRATION.id}
    candidate_conflicts: list[Record] = []
    for r in rows:
        tails = {_tail(c) for c in _calls(r)}
        strings = _strings(r)
        if "integrate_authorized_task_state" in tails and r.id != CANDIDATE_FACADE.id:
            candidate_conflicts.append(r)
        elif "integrate_task_state" in tails:
            candidate_conflicts.append(r)
        elif (
            "update-ref" in strings
            or "--ff-only" in strings
            or ("--no-ff" in strings and "--no-edit" in strings)
        ) and r.id not in allowed_git_apply:
            candidate_conflicts.append(r)
    _raise("candidate_integration", "SECOND_GIT_APPLY_PRIMITIVE", candidate_conflicts)

    # Gateway durable host effect is module-owned.  A newly named function in a
    # new file cannot silently gain LaunchAgent mutation authority.
    _raise(
        "gateway_durable_deployment_recovery",
        "LAUNCHCTL_OUTSIDE_DURABLE_MANAGER_MODULE",
        (r for r in rows if r.path != GATEWAY_MODULE and "launchctl" in _strings(r)),
    )

    # Standing-grant transition writer: cross-module sink calls and copied
    # durable-writer primitives both fail closed.
    transition_conflicts: list[Record] = []
    for r in rows:
        calls = _calls(r)
        tails = {_tail(c) for c in calls}
        strings = _strings(r)
        if "_write_transition_file" in tails and r.path != TRANSITION_SINK.path:
            transition_conflicts.append(r)
        elif (
            ".trans-" in strings
            and "tempfile.mkstemp" in calls
            and "os.replace" in calls
            and r.id != TRANSITION_SINK.id
        ):
            transition_conflicts.append(r)
    _raise("standing_grant_transition", "SECOND_TRANSITION_WRITER", transition_conflicts)

    return {
        "schema": "nexus.architecture_effect_owner_inventory.v2",
        "classification": "SINGLE_EFFECT_OWNER",
        "effects": {
            "protected_github_merge": {"boundary": MERGE_PORT.id, "physical_sink": "EXTERNAL_PORT_EFFECT"},
            "candidate_integration": {"boundary": CANDIDATE_FACADE.id, "physical_sink": CANDIDATE_SINK.id, "retired": LEGACY_INTEGRATION.id},
            "gateway_durable_deployment_recovery": {"boundary": GATEWAY_MANAGER.id, "physical_sink": GATEWAY_MODULE},
            "standing_grant_transition": {"boundary": TRANSITION_SINK.id, "physical_sink": TRANSITION_SINK.id},
        },
    }


def inventory() -> dict[str, object]:
    allowed = {"CANONICAL", "COMPATIBILITY_ONLY", "RETIRED"}
    entries = [{"target": r.id, "label": r.label} for r in DECLARED]
    assert all(e["label"] in allowed for e in entries)
    return {"schema": "nexus.architecture_effect_owner_inventory.v2", "classification": "SINGLE_EFFECT_OWNER", "entries": entries}


def _expect_extra_failure(tmp_path: Path, name: str, code: str, expected_effect: str) -> None:
    rogue = tmp_path / name
    rogue.write_text(code, encoding="utf-8")
    try:
        verify(Path(__file__).resolve().parents[2], extra=(rogue,))
    except AssertionError as exc:
        assert f"DUPLICATE_EFFECT_IMPLEMENTATION:{expected_effect}" in str(exc)
        return
    raise AssertionError(f"hostile control did not fail: {name}")


def test_current_source_has_single_effect_owners():
    result = verify(Path(__file__).resolve().parents[2])
    assert result["classification"] == "SINGLE_EFFECT_OWNER"
    assert len(result["effects"]) == 4


def test_recursive_scan_discovers_new_source_file(tmp_path):
    (tmp_path / "nexus/x").mkdir(parents=True)
    (tmp_path / "scripts/ops").mkdir(parents=True)
    rogue = tmp_path / "nexus/x/brand_new.py"
    rogue.write_text("def x():\n    return 1\n", encoding="utf-8")
    assert "nexus/x/brand_new.py" in {p.relative_to(tmp_path).as_posix() for p in _files(tmp_path)}


def test_new_different_named_direct_merge_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_merge.py",
        "def publish(client):\n    return client.git_merge_pull_request('repo', 1)\n",
        "protected_github_merge",
    )


def test_new_different_named_git_apply_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_apply.py",
        "import subprocess\ndef apply(ref, sha, old):\n    return subprocess.run(['git','update-ref',ref,sha,old])\n",
        "candidate_integration",
    )


def test_new_different_named_gateway_effect_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_gateway.py",
        "import subprocess\ndef restart():\n    return subprocess.run(['launchctl','kickstart','gui/501/com.nexus.mcp.gateway'])\n",
        "gateway_durable_deployment_recovery",
    )


def test_new_different_named_transition_writer_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_transition.py",
        "import os,tempfile\ndef persist(path):\n    fd,tmp=tempfile.mkstemp(prefix='.trans-',dir=path.parent)\n    os.close(fd)\n    os.replace(tmp,path)\n",
        "standing_grant_transition",
    )


def test_fake_receiver_with_cas_merge_name_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "fake_receiver.py",
        "def x(fake):\n    return fake.cas_merge(repository='x',pull_request_number=1)\n",
        "protected_github_merge",
    )


def test_missing_declared_symbol_fails_loudly():
    missing = Ref("nexus/orchestrator/not_real.py", None, "missing")
    try:
        _get(Path(__file__).resolve().parents[2], missing)
    except AssertionError as exc:
        assert "DECLARED_SYMBOL_FILE_MISSING" in str(exc)
        return
    raise AssertionError("missing symbol was silently ignored")


def test_inventory_labels_are_strict_and_retired_is_explicit():
    report = inventory()
    labels = {e["label"] for e in report["entries"]}
    assert labels <= {"CANONICAL", "COMPATIBILITY_ONLY", "RETIRED"}
    assert "RETIRED" in labels
