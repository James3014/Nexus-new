"""Fail-closed regression for single ownership of critical Nexus effects (#947).

This is test-only architecture evidence, never runtime routing or authority. It
recursively scans production Python, binds exact caller/sink identities, and
fails when a new physical implementation appears outside the admitted seams.
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


MERGE_PORT = Ref(
    "nexus/orchestrator/github_completion_loop.py",
    "GitHubCompletionPort",
    "cas_merge",
)
MERGE_LOOP = Ref(
    "nexus/orchestrator/github_completion_loop.py",
    None,
    "run_github_completion_loop",
)
CANDIDATE_FACADE = Ref(
    "nexus/orchestrator/self_hosted_task_service.py",
    "SelfHostedTaskService",
    "integrate_approved",
)
CANDIDATE_SINK = Ref(
    "nexus/orchestrator/governed_integration.py",
    "ControlledIntegrationManager",
    "integrate_authorized_task_state",
)
TARGET_LIFECYCLE_CALLER = Ref(
    "nexus/orchestrator/target_integration_lifecycle.py",
    "TargetIntegrationLifecycle",
    "transactional_integration",
    "COMPATIBILITY_ONLY",
)
COMPETITION_SINK = Ref(
    "nexus/orchestrator/governed_integration.py",
    "ControlledIntegrationManager",
    "integrate_task_state",
    "COMPATIBILITY_ONLY",
)
COMPETITION_CALLER = Ref(
    "nexus/orchestrator/worker_competition.py",
    "WorkerCompetitionCoordinator",
    "integrate_winner",
    "COMPATIBILITY_ONLY",
)
UNIFIED_CALLER = Ref(
    "nexus/orchestrator/unified_mcp_gateway.py",
    "UnifiedMCPGateway",
    "_candidate_integrate",
    "COMPATIBILITY_ONLY",
)
SELF_HOSTED_CALLER = Ref(
    "nexus/orchestrator/self_hosted_mcp.py",
    "NexusSelfHostedMCPServer",
    "_call_tool",
    "COMPATIBILITY_ONLY",
)
GATEWAY_MODULE = "scripts/ops/mcp_gateway_durable.py"
GATEWAY_MANAGER = Ref(GATEWAY_MODULE, None, "manage")
TRANSITION_SINK = Ref(
    "nexus/orchestrator/standing_grant_store.py",
    None,
    "_write_transition_file",
)
SWITCH_CALLER = Ref(
    "nexus/orchestrator/standing_grant_store.py",
    None,
    "switch_task_card_authority",
    "COMPATIBILITY_ONLY",
)
RESTORE_CALLER = Ref(
    "nexus/orchestrator/standing_grant_store.py",
    None,
    "restore_task_card_authority",
    "COMPATIBILITY_ONLY",
)

# These exact symbols own other Git effects (salvage/durable-ref/deletion-anchor
# maintenance). They are not Candidate integration implementations. Keeping the
# exclusions symbol-exact preserves fail-closed behavior for any new raw Git
# writer while avoiding a category error that treats every update-ref as
# integration authority.
NON_CANDIDATE_GIT_WRITERS = frozenset({
    "nexus/orchestrator/worktree_manager.py:WorktreeManager.create_salvage_snapshot",
    "nexus/orchestrator/worktree_manager.py:WorktreeManager.protect_candidate",
    "nexus/orchestrator/worktree_manager.py:WorktreeManager.protect_salvage_head",
    "nexus/orchestrator/worktree_manager.py:WorktreeManager.restore_task_branch_for_retry",
    "scripts/ops/trusted_deletion_anchor.py:_create_git_bundle",
    "scripts/ops/trusted_deletion_anchor.py:_prepare_executor_git_context",
})

DECLARED = (
    MERGE_PORT,
    MERGE_LOOP,
    CANDIDATE_FACADE,
    CANDIDATE_SINK,
    TARGET_LIFECYCLE_CALLER,
    COMPETITION_SINK,
    COMPETITION_CALLER,
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
    (TARGET_LIFECYCLE_CALLER, "manager.integrate_authorized_task_state"),
    (COMPETITION_CALLER, "ControlledIntegrationManager().integrate_task_state"),
    (SWITCH_CALLER, "_write_transition_file"),
    (RESTORE_CALLER, "_write_transition_file"),
)


def _files(root: Path) -> tuple[Path, ...]:
    found: list[Path] = []
    for rel in (Path("nexus"), Path("scripts/ops")):
        base = root / rel
        if not base.is_dir():
            raise AssertionError(f"PRODUCTION_SCAN_ROOT_MISSING:{rel.as_posix()}")
        found.extend(
            path
            for path in base.rglob("*.py")
            if not any(
                part in {".git", ".venv", "__pycache__", "node_modules"} for part in path.parts
            )
        )
    return tuple(sorted(found, key=lambda path: path.relative_to(root).as_posix()))


def _parse(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, SyntaxError, UnicodeError) as exc:
        raise AssertionError(f"SOURCE_UNPARSEABLE:{path}:{exc}") from exc


def _records(path: Path, root: Path | None) -> tuple[Record, ...]:
    rel = path.relative_to(root).as_posix() if root is not None else str(path)
    records: list[Record] = []
    for node in _parse(path).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            records.append(Record(rel, None, node.name, node))
        elif isinstance(node, ast.ClassDef):
            records.extend(
                Record(rel, node.name, child.name, child)
                for child in node.body
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
            )
    return tuple(records)


def _all(root: Path, extra: Iterable[Path] = ()) -> tuple[Record, ...]:
    records = [record for path in _files(root) for record in _records(path, root)]
    records.extend(record for path in extra for record in _records(path, None))
    return tuple(records)


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
    return tuple(
        expression
        for node in ast.walk(record.node)
        if isinstance(node, ast.Call) and (expression := _expr(node.func)) is not None
    )


def _tail(call: str) -> str:
    return call.rsplit(".", 1)[-1].removesuffix("()")


def _strings(record: Record) -> frozenset[str]:
    return frozenset(
        node.value
        for node in ast.walk(record.node)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    )


def _raise(effect: str, reason: str, rows: Iterable[Record]) -> None:
    ids = sorted({row.id for row in rows})
    if ids:
        raise AssertionError(f"DUPLICATE_EFFECT_IMPLEMENTATION:{effect}:{reason}:" + ",".join(ids))


def verify(root: Path, *, extra: Iterable[Path] = ()) -> dict[str, object]:
    root = root.resolve()

    for ref in DECLARED:
        _get(root, ref)

    for caller, expected in EDGES:
        row = _get(root, caller)
        observed = _calls(row)
        if expected not in observed:
            raise AssertionError(
                f"DELEGATION_EDGE_MISSING:{caller.id}->{expected};observed={sorted(observed)}"
            )

    rows = _all(root, extra)

    _raise(
        "protected_github_merge",
        "DIRECT_OR_SECOND_CAS_MERGE",
        (
            row
            for row in rows
            if (any(_tail(call) == "cas_merge" for call in _calls(row)) and row.id != MERGE_LOOP.id)
            or any(
                _tail(call) in {"merge_pull_request", "git_merge_pull_request"}
                for call in _calls(row)
            )
        ),
    )

    allowed_candidate_callers = {CANDIDATE_FACADE.id, TARGET_LIFECYCLE_CALLER.id}
    allowed_git_apply = {CANDIDATE_SINK.id, COMPETITION_SINK.id}
    candidate_conflicts: list[Record] = []
    for row in rows:
        tails = {_tail(call) for call in _calls(row)}
        strings = _strings(row)
        if "integrate_authorized_task_state" in tails and row.id not in allowed_candidate_callers:
            candidate_conflicts.append(row)
        elif "integrate_task_state" in tails and row.id != COMPETITION_CALLER.id:
            candidate_conflicts.append(row)
        elif (
            "update-ref" in strings
            or "--ff-only" in strings
            or ("--no-ff" in strings and "--no-edit" in strings)
        ) and row.id not in allowed_git_apply | NON_CANDIDATE_GIT_WRITERS:
            candidate_conflicts.append(row)
    _raise("candidate_integration", "SECOND_GIT_APPLY_PRIMITIVE", candidate_conflicts)

    _raise(
        "gateway_durable_deployment_recovery",
        "LAUNCHCTL_OUTSIDE_DURABLE_MANAGER_MODULE",
        (row for row in rows if row.path != GATEWAY_MODULE and "launchctl" in _strings(row)),
    )

    transition_conflicts: list[Record] = []
    for row in rows:
        calls = _calls(row)
        tails = {_tail(call) for call in calls}
        strings = _strings(row)
        if "_write_transition_file" in tails and row.path != TRANSITION_SINK.path:
            transition_conflicts.append(row)
        elif (
            ".trans-" in strings
            and "tempfile.mkstemp" in calls
            and "os.replace" in calls
            and row.id != TRANSITION_SINK.id
        ):
            transition_conflicts.append(row)
    _raise("standing_grant_transition", "SECOND_TRANSITION_WRITER", transition_conflicts)

    return {
        "schema": "nexus.architecture_effect_owner_inventory.v3",
        "classification": "SINGLE_EFFECT_OWNER",
        "effects": {
            "protected_github_merge": {
                "boundary": MERGE_PORT.id,
                "physical_sink": "EXTERNAL_PORT_EFFECT",
            },
            "candidate_integration": {
                "authority_facade": CANDIDATE_FACADE.id,
                "physical_sink": CANDIDATE_SINK.id,
                "effect_owner_class": (
                    "nexus/orchestrator/governed_integration.py:ControlledIntegrationManager"
                ),
                "compatibility_callers": [TARGET_LIFECYCLE_CALLER.id],
                "compatibility_domain": {
                    "name": "competition_winner_integration",
                    "caller": COMPETITION_CALLER.id,
                    "physical_sink": COMPETITION_SINK.id,
                    "classification": "COMPATIBILITY_ONLY",
                },
            },
            "gateway_durable_deployment_recovery": {
                "boundary": GATEWAY_MANAGER.id,
                "physical_sink": GATEWAY_MODULE,
            },
            "standing_grant_transition": {
                "boundary": TRANSITION_SINK.id,
                "physical_sink": TRANSITION_SINK.id,
            },
        },
    }


def inventory() -> dict[str, object]:
    allowed = {"CANONICAL", "COMPATIBILITY_ONLY", "RETIRED"}
    entries = [{"target": ref.id, "label": ref.label} for ref in DECLARED]
    assert all(entry["label"] in allowed for entry in entries)
    return {
        "schema": "nexus.architecture_effect_owner_inventory.v3",
        "classification": "SINGLE_EFFECT_OWNER",
        "entries": entries,
    }


def _expect_extra_failure(
    tmp_path: Path,
    name: str,
    code: str,
    expected_effect: str,
) -> None:
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


def test_competition_integration_is_explicit_compatibility_domain():
    result = verify(Path(__file__).resolve().parents[2])
    candidate = result["effects"]["candidate_integration"]
    compatibility = candidate["compatibility_domain"]
    assert compatibility["classification"] == "COMPATIBILITY_ONLY"
    assert compatibility["caller"] == COMPETITION_CALLER.id
    assert compatibility["physical_sink"] == COMPETITION_SINK.id
    assert TARGET_LIFECYCLE_CALLER.id in candidate["compatibility_callers"]


def test_recursive_scan_discovers_new_source_file(tmp_path):
    (tmp_path / "nexus/x").mkdir(parents=True)
    (tmp_path / "scripts/ops").mkdir(parents=True)
    rogue = tmp_path / "nexus/x/brand_new.py"
    rogue.write_text("def x():\n    return 1\n", encoding="utf-8")
    discovered = {path.relative_to(tmp_path).as_posix() for path in _files(tmp_path)}
    assert "nexus/x/brand_new.py" in discovered


def test_new_different_named_direct_merge_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_merge.py",
        "def publish(client):\n    return client.git_merge_pull_request('repo', 1)\n",
        "protected_github_merge",
    )


def test_fake_receiver_with_cas_merge_name_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "fake_receiver.py",
        "def x(fake):\n    return fake.cas_merge(repository='x',pull_request_number=1)\n",
        "protected_github_merge",
    )


def test_new_different_named_git_apply_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_apply.py",
        (
            "import subprocess\n"
            "def apply(ref, sha, old):\n"
            "    return subprocess.run(['git','update-ref',ref,sha,old])\n"
        ),
        "candidate_integration",
    )


def test_unknown_caller_to_candidate_sink_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_candidate_apply.py",
        "def apply(manager, state):\n    return manager.integrate_authorized_task_state(state)\n",
        "candidate_integration",
    )


def test_unknown_caller_to_competition_sink_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_competition_apply.py",
        "def apply(manager, state):\n    return manager.integrate_task_state(state)\n",
        "candidate_integration",
    )


def test_new_different_named_gateway_effect_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_gateway.py",
        (
            "import subprocess\n"
            "def restart():\n"
            "    return subprocess.run(['launchctl','kickstart',"
            "'gui/501/com.nexus.mcp.gateway'])\n"
        ),
        "gateway_durable_deployment_recovery",
    )


def test_new_different_named_transition_writer_fails(tmp_path):
    _expect_extra_failure(
        tmp_path,
        "new_transition.py",
        (
            "import os,tempfile\n"
            "def persist(path):\n"
            "    fd,tmp=tempfile.mkstemp(prefix='.trans-',dir=path.parent)\n"
            "    os.close(fd)\n"
            "    os.replace(tmp,path)\n"
        ),
        "standing_grant_transition",
    )


def test_missing_declared_symbol_fails_loudly():
    missing = Ref("nexus/orchestrator/not_real.py", None, "missing")
    try:
        _get(Path(__file__).resolve().parents[2], missing)
    except AssertionError as exc:
        assert "DECLARED_SYMBOL_FILE_MISSING" in str(exc)
        return
    raise AssertionError("missing symbol was silently ignored")


def test_inventory_labels_are_strict_and_compatibility_is_explicit():
    report = inventory()
    labels = {entry["label"] for entry in report["entries"]}
    assert labels <= {"CANONICAL", "COMPATIBILITY_ONLY", "RETIRED"}
    assert "COMPATIBILITY_ONLY" in labels
