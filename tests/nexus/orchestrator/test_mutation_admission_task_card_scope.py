"""GOVERNED admission scope stays inside the committed Task Card (Issue #2766).

Every test drives the real ``nexus_mutation_admit`` tool dispatch of
``UnifiedMCPGateway`` against a Task Card committed in a temporary Controller git
repository, then inspects the ``MutationAdmissionStore`` on disk.
"""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

import nexus.orchestrator.unified_mcp_gateway as gateway_module
from nexus.orchestrator import mutation_admission as admission_module
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
from nexus.orchestrator.unified_mcp_gateway import GatewayInputError, UnifiedMCPGateway

CARD_PATH = "tasks/scope-2766/00-scope.md"


def _card(allowed_section: str) -> str:
    return (
        "# Task Card: scope-2766\n\n"
        "artifact_authority: current\n"
        "task_id: `scope-2766`\n"
        "attempt_id: `attempt-2766`\n"
        "status: ACTIVE\n"
        "execution_lane: GOVERNED\n"
        "- GitHub Issue: `James3014/Nexus-new#2766`\n\n"
        "## Objective\n\nBound the admission scope.\n\n"
        f"{allowed_section}"
        "## Verification commands\n\n```bash\npython3 -m pytest -q\n```\n"
    )


def _allowed(*paths: str) -> str:
    return "## Allowed files\n\n" + "".join(f"- `{path}`\n" for path in paths) + "\n"


def _run(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, check=True
    ).stdout.strip()


def _controller(tmp_path: Path, card_text: str) -> tuple[Path, str, str]:
    repo = tmp_path / "controller"
    (repo / "tasks" / "scope-2766").mkdir(parents=True)
    _run(repo, "init", "-q", "-b", "main")
    _run(repo, "config", "user.email", "test@example.test")
    _run(repo, "config", "user.name", "Test User")
    (repo / CARD_PATH).write_text(card_text, encoding="utf-8")
    _run(repo, "add", ".")
    _run(repo, "commit", "-q", "-m", "task card")
    head = _run(repo, "rev-parse", "HEAD")
    return repo, head, hashlib.sha256(card_text.encode("utf-8")).hexdigest()


def _gateway(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, card_text: str
) -> tuple[UnifiedMCPGateway, str, str]:
    repo, head, card_hash = _controller(tmp_path, card_text)
    monkeypatch.setattr(gateway_module, "CANONICAL_SOURCE_ROOT", repo)
    service = SelfHostedTaskService(tmp_path / "state", auto_reconcile=False, ephemeral=True)
    observer = {
        "ok": True,
        "default_branch": "main",
        "head_sha": head,
        "observed_at": "2026-10-20T00:00:00+00:00",
    }
    gateway = UnifiedMCPGateway(
        service=service,
        mutation_repository_observer=lambda repository: {**observer, "repository": repository},
    )
    return gateway, head, card_hash


def _args(head: str, card_hash: str, allowed_paths: list[str], op: str) -> dict[str, object]:
    return {
        "operation_id": f"governed:issue2766:{op}",
        "repository": "James3014/Nexus-new",
        "base_sha": head,
        "execution_lane": "GOVERNED",
        "authority_kind": "TRACKED_TASK_CARD",
        "allowed_paths": allowed_paths,
        "issue_number": 2766,
        "task_id": "scope-2766",
        "attempt_id": "attempt-2766",
        "task_card_path": CARD_PATH,
        "task_card_hash": card_hash,
    }


def _rows(gateway: UnifiedMCPGateway) -> list[Path]:
    root = gateway._mutation_admissions.root
    return sorted(root.glob("*.json")) if root.exists() else []


@pytest.mark.parametrize(
    ("requested", "widened"),
    [
        (["nexus/**"], ["nexus/**"]),
        (["nexus/"], ["nexus/"]),
        (["docs/a.md", "nexus/x.py"], ["nexus/x.py"]),
        (["docs/**"], ["docs/**"]),
        (["docs/a.md/**"], ["docs/a.md/**"]),
        (["Docs/a.md"], ["Docs/a.md"]),
        (["docs/./a.md"], ["docs/./a.md"]),
        (["docs/../docs/a.md"], ["docs/../docs/a.md"]),
        (["/docs/a.md"], ["/docs/a.md"]),
        (["docs/a.m?"], ["docs/a.m?"]),
    ],
)
def test_2766_governed_admission_refuses_widened_scope_and_writes_no_row(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    requested: list[str],
    widened: list[str],
) -> None:
    gateway, head, card_hash = _gateway(tmp_path, monkeypatch, _card(_allowed("docs/a.md")))

    with pytest.raises(GatewayInputError) as caught:
        gateway._call_tool("nexus_mutation_admit", _args(head, card_hash, requested, "wide"))

    assert str(caught.value).startswith("MUTATION_ADMISSION_ALLOWED_PATHS_EXCEED_TASK_CARD:")
    for path in widened:
        assert f'"{path}"' in str(caught.value)
    assert _rows(gateway) == []


@pytest.mark.parametrize(
    "requested",
    [["docs/a.md"], ["docs/b.md"], ["docs/a.md", "docs/b.md"], ["docs/b.md", "docs/a.md"]],
)
def test_2766_governed_admission_admits_equal_or_narrower_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, requested: list[str]
) -> None:
    gateway, head, card_hash = _gateway(
        tmp_path, monkeypatch, _card(_allowed("docs/a.md", "docs/b.md"))
    )

    receipt = gateway._call_tool("nexus_mutation_admit", _args(head, card_hash, requested, "ok"))

    assert receipt["duplicate"] is False
    assert receipt["allowed_paths"] == requested
    assert receipt["task_card_hash"] == card_hash
    assert len(_rows(gateway)) == 1


def test_2766_card_directory_entry_bounds_files_and_subdirectories(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway, head, card_hash = _gateway(
        tmp_path, monkeypatch, _card(_allowed("nexus/orchestrator/**"))
    )

    inside = ["nexus/orchestrator/a.py", "nexus/orchestrator/sub/**", "nexus/orchestrator/**"]
    receipt = gateway._call_tool("nexus_mutation_admit", _args(head, card_hash, inside, "dir"))
    assert receipt["allowed_paths"] == inside
    with pytest.raises(GatewayInputError, match=r'EXCEED_TASK_CARD:\["nexus/\*\*"\]$'):
        gateway._call_tool("nexus_mutation_admit", _args(head, card_hash, ["nexus/**"], "up"))
    with pytest.raises(
        GatewayInputError, match=r'EXCEED_TASK_CARD:\["nexus/orchestratorx/a.py"\]$'
    ):
        gateway._call_tool(
            "nexus_mutation_admit",
            _args(head, card_hash, ["nexus/orchestratorx/a.py"], "sibling"),
        )
    assert len(_rows(gateway)) == 1


@pytest.mark.parametrize(
    "section",
    [
        "",
        _allowed("docs/a.md") + _allowed("nexus/**"),
        "## Allowed files\n\n- this Task Card and INDEX\n- docs/a.md\n\n",
    ],
    ids=["missing", "repeated", "no-exact-bullet"],
)
def test_2766_unresolvable_card_scope_refuses_admission(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, section: str
) -> None:
    gateway, head, card_hash = _gateway(tmp_path, monkeypatch, _card(section))

    with pytest.raises(
        GatewayInputError, match="^MUTATION_ADMISSION_TASK_CARD_ALLOWED_FILES_UNRESOLVABLE$"
    ):
        gateway._call_tool("nexus_mutation_admit", _args(head, card_hash, ["docs/a.md"], "x"))
    assert _rows(gateway) == []


def test_2766_widened_retry_cannot_reuse_an_admitted_operation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    gateway, head, card_hash = _gateway(tmp_path, monkeypatch, _card(_allowed("docs/a.md")))
    first = gateway._call_tool("nexus_mutation_admit", _args(head, card_hash, ["docs/a.md"], "r"))

    with pytest.raises(GatewayInputError, match="EXCEED_TASK_CARD"):
        gateway._call_tool(
            "nexus_mutation_admit", _args(head, card_hash, ["docs/a.md", "nexus/**"], "r")
        )
    assert [path.stem for path in _rows(gateway)] == [first["admission_id"]]


def test_2766_card_parser_keeps_only_exact_normalized_bullets() -> None:
    source = _card(
        "## Allowed files\n\n"
        "- `docs/a.md`\n"
        "- `docs/a.md`\n"
        "- `nexus/x.py` only when needed\n"
        "- this Task Card and `INDEX.md`\n"
        "- `./docs/b.md`\n"
        "- `docs/c/`\n"
        "- `../escape.md`\n"
        "- `src/*.py`\n"
        "  - `docs/d.md`\n"
        "* `docs/e.md`\n"
        "- `tools/**`\n\n"
        "### Notes\n\n- `docs/after-heading.md`\n\n"
    )

    assert admission_module.task_card_allowed_files(source) == (
        "docs/a.md",
        "docs/d.md",
        "tools/**",
    )


def test_2766_card_parser_refuses_missing_section() -> None:
    with pytest.raises(
        admission_module.MutationAdmissionError, match="TASK_CARD_ALLOWED_FILES_UNRESOLVABLE"
    ):
        admission_module.task_card_allowed_files(_card(""))


def test_2766_scope_excess_is_exact_and_case_sensitive() -> None:
    card = ("docs/a.md", "pkg/**")
    assert (
        admission_module.governed_scope_excess(["docs/a.md", "pkg", "pkg/x/y.py", "pkg/x/**"], card)
        == []
    )
    assert admission_module.governed_scope_excess(
        ["DOCS/a.md", "docs/a.md ", "pkg/../x", "pkgx/a", "", "pkg/*.py", "pkg/x/*/**"], card
    ) == ["DOCS/a.md", "docs/a.md ", "pkg/../x", "pkgx/a", "", "pkg/*.py", "pkg/x/*/**"]
