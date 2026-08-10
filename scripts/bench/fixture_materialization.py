from __future__ import annotations

import shutil
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping, Protocol, Sequence
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class LocalFixtureSource:
    target_code: str
    visible_test_code: str
    hidden_test_code: str | None = None
    visible_test_name: str = "test_visible.py"
    hidden_test_name: str = "test_hidden.py"
    extra_files: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class FixtureMaterializationResult:
    case_dir: str
    target_file: str
    visible_test_file: str
    hidden_test_file: str


@dataclass(frozen=True)
class ExternalFixtureRequest:
    task_id: str
    repo: str
    repo_ref: str
    fixture_kind: str = ""
    target_file: str = ""
    test_file: str = ""
    hidden_test_file: str = ""


class ExternalFixtureAdapter(Protocol):
    def resolve(self, request: ExternalFixtureRequest) -> FixtureMaterializationResult:
        ...


class ExternalFixtureAdapterRequired(NotImplementedError):
    pass


class ExternalFixturePolicyError(ValueError):
    pass


def _normalized_relative_file(rel_name: str) -> str:
    rel_path = Path(rel_name)
    if rel_path.is_absolute() or ".." in rel_path.parts:
        raise ExternalFixturePolicyError(f"external fixture manifest file must stay relative: {rel_name}")
    return rel_path.as_posix()


@dataclass(frozen=True)
class ExternalFixtureCacheManifest:
    allowed_repo: str
    allowed_ref: str
    cache_dir: Path
    expected_files: tuple[str, ...]
    network_allowed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "cache_dir", Path(self.cache_dir).resolve())
        object.__setattr__(
            self,
            "expected_files",
            tuple(_normalized_relative_file(rel_name) for rel_name in self.expected_files),
        )


@dataclass(frozen=True)
class OfflineCachedExternalFixtureAdapter:
    workspace_root: Path
    cache_manifest: ExternalFixtureCacheManifest | None = None

    def resolve(self, request: ExternalFixtureRequest) -> FixtureMaterializationResult:
        manifest = self.cache_manifest
        if manifest is None:
            raise ExternalFixturePolicyError("offline cache manifest is required for external fixture setup")
        if manifest.network_allowed:
            raise ExternalFixturePolicyError("live network external fixture setup is not implemented")
        if request.repo != manifest.allowed_repo or request.repo_ref != manifest.allowed_ref:
            raise ExternalFixturePolicyError("external fixture repo/ref not allowed by offline cache manifest")

        declared_files = [request.target_file, request.test_file]
        if request.hidden_test_file:
            declared_files.append(request.hidden_test_file)
        missing_from_manifest = [
            rel_name
            for rel_name in declared_files
            if _normalized_relative_file(rel_name) not in manifest.expected_files
        ]
        if missing_from_manifest:
            raise ExternalFixturePolicyError(
                "external fixture file not declared in offline cache manifest: "
                + ", ".join(missing_from_manifest)
            )

        adapter = SandboxedLocalExternalFixtureAdapter(
            workspace_root=self.workspace_root,
            allowed_source_roots=[manifest.cache_dir],
        )
        return adapter.resolve(replace(request, repo=str(manifest.cache_dir)))


@dataclass(frozen=True)
class SandboxedLocalExternalFixtureAdapter:
    workspace_root: Path
    allowed_source_roots: Sequence[Path] = ()

    def __post_init__(self) -> None:
        workspace_root = Path(self.workspace_root).resolve()
        allowed_source_roots = tuple(Path(root).resolve() for root in self.allowed_source_roots) or (
            workspace_root,
        )
        object.__setattr__(self, "workspace_root", workspace_root)
        object.__setattr__(self, "allowed_source_roots", allowed_source_roots)

    def resolve(self, request: ExternalFixtureRequest) -> FixtureMaterializationResult:
        source_root = self._source_root(request.repo)
        case_dir = self._case_dir(request.task_id)
        target_file = self._copy_declared_file(
            source_root,
            case_dir,
            request.target_file,
            field_name="target_file",
        )
        visible_test_file = self._copy_declared_file(
            source_root,
            case_dir,
            request.test_file,
            field_name="test_file",
        )
        hidden_test_file = ""
        if request.hidden_test_file:
            hidden_test_file = str(
                self._copy_declared_file(
                    source_root,
                    case_dir,
                    request.hidden_test_file,
                    field_name="hidden_test_file",
                )
            )

        return FixtureMaterializationResult(
            case_dir=str(case_dir),
            target_file=str(target_file),
            visible_test_file=str(visible_test_file),
            hidden_test_file=hidden_test_file,
        )

    def _source_root(self, repo: str) -> Path:
        if repo.startswith("git@"):
            raise ExternalFixturePolicyError("remote external fixture repo not allowed")
        parsed = urlparse(repo)
        if parsed.scheme == "file":
            if parsed.netloc not in {"", "localhost"}:
                raise ExternalFixturePolicyError("remote external fixture repo not allowed")
            source_root = Path(unquote(parsed.path)).resolve()
        elif parsed.scheme in {"http", "https", "ssh", "git"} or parsed.netloc:
            raise ExternalFixturePolicyError("remote external fixture repo not allowed")
        elif parsed.scheme:
            raise ExternalFixturePolicyError(f"unsupported external fixture repo scheme: {parsed.scheme}")
        else:
            source_root = Path(repo).expanduser().resolve()

        if not source_root.is_dir():
            raise ExternalFixturePolicyError(f"external fixture repo must be an existing directory: {repo}")
        if not any(source_root == root or source_root.is_relative_to(root) for root in self.allowed_source_roots):
            raise ExternalFixturePolicyError("external fixture source is outside allowed roots")
        return source_root

    def _case_dir(self, task_id: str) -> Path:
        task_path = Path(task_id)
        if task_path.is_absolute():
            raise ExternalFixturePolicyError(f"external fixture task_id must be relative: {task_id}")
        case_dir = (self.workspace_root / ".nexus" / "bench_cases" / task_path).resolve()
        bench_cases_root = (self.workspace_root / ".nexus" / "bench_cases").resolve()
        if not case_dir.is_relative_to(bench_cases_root):
            raise ExternalFixturePolicyError(f"external fixture task_id escapes bench case root: {task_id}")
        case_dir.mkdir(parents=True, exist_ok=True)
        return case_dir

    def _copy_declared_file(
        self,
        source_root: Path,
        case_dir: Path,
        rel_name: str,
        *,
        field_name: str,
    ) -> Path:
        if not rel_name:
            raise ExternalFixturePolicyError(f"external fixture {field_name} is required")
        source_file = self._safe_source_file(source_root, rel_name)
        destination = self._safe_case_file(case_dir, rel_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_file, destination)
        return destination

    @staticmethod
    def _safe_source_file(source_root: Path, rel_name: str) -> Path:
        rel_path = Path(rel_name)
        if rel_path.is_absolute():
            raise ExternalFixturePolicyError(f"external fixture file must be relative: {rel_name}")
        source_file = (source_root / rel_path).resolve()
        if not source_file.is_relative_to(source_root):
            raise ExternalFixturePolicyError(f"external fixture file escapes external fixture source: {rel_name}")
        if not source_file.is_file():
            raise ExternalFixturePolicyError(f"external fixture file does not exist: {rel_name}")
        return source_file

    @staticmethod
    def _safe_case_file(case_dir: Path, rel_name: str) -> Path:
        rel_path = Path(rel_name)
        if rel_path.is_absolute():
            raise ExternalFixturePolicyError(f"external fixture output file must be relative: {rel_name}")
        destination = (case_dir / rel_path).resolve()
        if not destination.is_relative_to(case_dir):
            raise ExternalFixturePolicyError(f"external fixture output file escapes case dir: {rel_name}")
        return destination


def resolve_external_fixture(
    request: ExternalFixtureRequest,
    *,
    adapter: ExternalFixtureAdapter | None = None,
) -> FixtureMaterializationResult:
    if adapter is None:
        raise ExternalFixtureAdapterRequired(
            f"{request.task_id} is external; clone/setup adapter is required before public execution"
        )
    return adapter.resolve(request)


def materialize_local_fixture(repo_root: Path, *, task_id: str, source: LocalFixtureSource) -> FixtureMaterializationResult:
    root = (repo_root / ".nexus" / "bench_cases").resolve()
    case_dir = (root / task_id).resolve()
    if not case_dir.is_relative_to(root):
        raise ValueError(f"fixture task_id escapes case root: {task_id}")
    case_dir.mkdir(parents=True, exist_ok=True)
    target_path = case_dir / "target.py"
    visible_test_path = case_dir / source.visible_test_name
    hidden_test_path = case_dir / source.hidden_test_name

    target_path.write_text(source.target_code, encoding="utf-8")
    visible_test_path.write_text(source.visible_test_code, encoding="utf-8")
    if source.hidden_test_code is not None:
        hidden_test_path.write_text(source.hidden_test_code, encoding="utf-8")

    for rel_name, content in source.extra_files.items():
        extra_path = _safe_extra_file_path(case_dir, rel_name)
        extra_path.parent.mkdir(parents=True, exist_ok=True)
        extra_path.write_text(content, encoding="utf-8")

    return FixtureMaterializationResult(
        case_dir=str(case_dir),
        target_file=str(target_path),
        visible_test_file=str(visible_test_path),
        hidden_test_file=str(hidden_test_path) if source.hidden_test_code is not None else "",
    )


def deterministic_fixture_source(fixture_kind: str) -> tuple[str, str, str]:
    """Return a broken target plus distinct visible and hidden verifiers."""
    fixtures = {
        "codex_dx_parser": (
            "def solve(value):\n    return value.strip()\n",
            "from target import solve\n\ndef test_visible():\n    assert solve(' Hello World ') == 'hello-world'\n",
            "from target import solve\n\ndef test_hidden():\n    assert solve('  MANY   Spaces ') == 'many-spaces'\n",
        ),
        "codex_dx_dedupe": (
            "def solve(items):\n    return sorted(set(items))\n",
            "from target import solve\n\ndef test_visible():\n    assert solve(['b', 'a', 'b']) == ['b', 'a']\n",
            "from target import solve\n\ndef test_hidden():\n    assert solve([3, 1, 3, 2]) == [3, 1, 2]\n",
        ),
        "codex_dx_redact": (
            "def solve(record):\n    return dict(record)\n",
            "from target import solve\n\ndef test_visible():\n    assert solve({'token': 'x'}) == {'token': '[REDACTED]'}\n",
            "from target import solve\n\ndef test_hidden():\n    assert solve({'password': 'x', 'ok': 1}) == {'password': '[REDACTED]', 'ok': 1}\n",
        ),
        "codex_dx_budget": (
            "def solve(defaults, override):\n    out = dict(defaults)\n    out.update(override or {})\n    return out\n",
            "from target import solve\n\ndef test_visible():\n    assert solve({'a': 1}, {'a': None}) == {'a': 1}\n",
            "from target import solve\n\ndef test_hidden():\n    assert solve({'a': 1}, {'a': None, 'b': 2}) == {'a': 1, 'b': 2}\n",
        ),
        "codex_dx_gate": (
            "def solve(status, artifact):\n    return status == 'pass'\n",
            "from target import solve\n\ndef test_visible():\n    assert solve('pass', '') is False\n",
            "from target import solve\n\ndef test_hidden():\n    assert solve('pass', 'report.json') is True\n    assert solve('fail', 'report.json') is False\n",
        ),
    }
    try:
        target, visible, hidden = fixtures[fixture_kind]
    except KeyError as exc:
        raise ValueError(f"unknown deterministic fixture: {fixture_kind}") from exc
    return (
        target,
        portable_fixture_test_import(visible),
        portable_fixture_test_import(hidden),
    )


def deterministic_fixture_patch(fixture_kind: str) -> str:
    """Return the checked-in corrected target source for a fixture."""
    patches = {
        "codex_dx_parser": "def solve(value):\n    return '-'.join(value.strip().lower().split())\n",
        "codex_dx_dedupe": "def solve(items):\n    return list(dict.fromkeys(items))\n",
        "codex_dx_redact": (
            "def solve(record):\n"
            "    sensitive = {'token', 'password'}\n"
            "    return {key: ('[REDACTED]' if key in sensitive else value) "
            "for key, value in record.items()}\n"
        ),
        "codex_dx_budget": (
            "def solve(defaults, override):\n"
            "    out = dict(defaults)\n"
            "    out.update({key: value for key, value in (override or {}).items() "
            "if value is not None})\n"
            "    return out\n"
        ),
        "codex_dx_gate": (
            "def solve(status, artifact):\n"
            "    return status == 'pass' and bool(artifact)\n"
        ),
    }
    try:
        return patches[fixture_kind]
    except KeyError as exc:
        raise ValueError(f"unknown deterministic fixture: {fixture_kind}") from exc


def _safe_extra_file_path(case_dir: Path, rel_name: str) -> Path:
    rel_path = Path(rel_name)
    if rel_path.is_absolute():
        raise ValueError(f"fixture extra file must be relative: {rel_name}")
    target = (case_dir / rel_path).resolve()
    if not target.is_relative_to(case_dir):
        raise ValueError(f"fixture extra file escapes case dir: {rel_name}")
    return target


def split_fixture_tests(test_code: str) -> tuple[str, str]:
    portable = portable_fixture_test_import(test_code)
    return portable, portable


def split_rlm_harder_fixture_tests(fixture_kind: str, test_code: str) -> tuple[str, str]:
    if fixture_kind == "rlm_harder_v2_governance_guard":
        visible = (
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_read_file_is_allowed_and_dangerous_shell_is_blocked():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n"
        )
        hidden = (
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_blocks_dangerous_actions_and_paths():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'delete_file', 'path': 'logs/run.json'}) == {'allowed': False, 'reason': 'governance_block'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'write_file', 'path': 'benchmarks/result.json'}) == {'allowed': False, 'reason': 'governance_block'}\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_evidence_gap":
        visible = (
            "from target import rlm_harder_v2_verified_claims\n\n"
            "def test_requires_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['a']\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_empty_and_non_string_artifacts():\n"
            "    claims = [\n"
            "        {'id': 'empty', 'status': 'pass', 'artifact': ''},\n"
            "        {'id': 'none', 'status': 'pass', 'artifact': None},\n"
            "        {'id': 'list', 'status': 'pass', 'artifact': []},\n"
            "        {'id': 'ok', 'status': 'pass', 'artifact': 'reports/ok.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['ok']\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_governance_scope":
        visible = (
            "from target import rlm_harder_v2_scope_decision\n\n"
            "def test_approved_and_read_only_paths():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'read', 'approved': False}) == {'allowed': True, 'reason': 'read_only'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'write', 'approved': True}) == {'allowed': True, 'reason': 'approved'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'delete', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n"
        )
        hidden = visible + (
            "\n"
            "def test_unknown_and_missing_approval_actions_are_blocked():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'write'}) == {'allowed': False, 'reason': 'scope_block'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'unknown', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_evidence_replay":
        visible = (
            "from target import rlm_harder_v2_accept_receipt\n\n"
            "def test_accepts_verified_receipt_with_replay():\n"
            "    receipt = {'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 0}\n"
            "    assert rlm_harder_v2_accept_receipt(receipt) is True\n"
            "\n"
            "def test_verified_receipt_requires_replay_and_clean_exit():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 1}) is False\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_near_miss_receipt_fields():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'replay_exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'partial', 'replay_command': 'pytest -q', 'exit_code': 0}) is False\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_second_round":
        visible = (
            "from target import rlm_harder_v2_merge_settings\n\n"
            "def test_plain_override_wins():\n"
            "    assert rlm_harder_v2_merge_settings({'timeout': 10}, {'timeout': 20}) == {'timeout': 20}\n"
            "\n"
            "def test_preserves_inputs_and_ignores_none_values():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n"
        )
        hidden = visible + (
            "\n"
            "def test_empty_override_returns_copy_not_alias():\n"
            "    defaults = {'timeout': 10}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {})\n"
            "    assert merged == {'timeout': 10}\n"
            "    assert merged is not defaults\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_memory_contract":
        visible = (
            "from target import rlm_harder_v2_select_memory_hits\n\n"
            "def test_requires_type_and_keyword_overlap():\n"
            "    items = [\n"
            "        {'id': 'old-bug', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket', 'timeout']) == [items[1]]\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_same_type_without_keyword_overlap_and_wrong_type():\n"
            "    items = [\n"
            "        {'id': 'same-type', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'wrong-type', 'task_type': 'feature', 'keywords': ['websocket', 'timeout']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket']) == [items[2]]\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_belief_budget":
        visible = (
            "from target import rlm_harder_v2_repair_budget\n\n"
            "def test_low_confidence_high_risk_requires_more_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.42, 'high') == {'rounds': 3, 'needs_evidence': True}\n"
            "    assert rlm_harder_v2_repair_budget(0.91, 'low') == {'rounds': 1, 'needs_evidence': False}\n"
        )
        hidden = visible + (
            "\n"
            "def test_uncertain_or_high_risk_paths_require_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.74, 'medium')['needs_evidence'] is True\n"
            "    assert rlm_harder_v2_repair_budget(0.95, 'high')['needs_evidence'] is True\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_autoreason_judge":
        visible = (
            "from target import rlm_harder_v2_choose_candidate\n\n"
            "def test_selects_supported_highest_score_candidate():\n"
            "    candidates = [\n"
            "        {'id': 'a', 'score': 0.4, 'evidence_refs': ['a.json']},\n"
            "        {'id': 'b', 'score': 0.9, 'evidence_refs': ['b.json']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_choose_candidate(candidates) == 'b'\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_high_score_without_evidence_and_failed_status():\n"
            "    candidates = [\n"
            "        {'id': 'unsupported', 'score': 0.99, 'evidence_refs': []},\n"
            "        {'id': 'failed', 'score': 0.95, 'status': 'fail', 'evidence_refs': ['fail.json']},\n"
            "        {'id': 'winner', 'score': 0.7, 'status': 'pass', 'evidence_refs': ['winner.json']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_choose_candidate(candidates) == 'winner'\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_ddtree_pruning":
        visible = (
            "from target import rlm_harder_v2_prune_candidates\n\n"
            "def test_prunes_to_budget_by_score():\n"
            "    candidates = [\n"
            "        {'id': 'a', 'score': 0.2, 'risk': 1},\n"
            "        {'id': 'b', 'score': 0.9, 'risk': 1},\n"
            "        {'id': 'c', 'score': 0.6, 'risk': 1},\n"
            "    ]\n"
            "    assert rlm_harder_v2_prune_candidates(candidates, 2) == ['b', 'c']\n"
        )
        hidden = visible + (
            "\n"
            "def test_preserves_high_risk_boundary_even_when_score_is_lower():\n"
            "    candidates = [\n"
            "        {'id': 'safe-high-score', 'score': 0.95, 'risk': 1},\n"
            "        {'id': 'risky-required', 'score': 0.5, 'risk': 9},\n"
            "        {'id': 'middle', 'score': 0.7, 'risk': 2},\n"
            "    ]\n"
            "    assert rlm_harder_v2_prune_candidates(candidates, 2) == ['risky-required', 'safe-high-score']\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_ultra_review_report":
        visible = (
            "from target import rlm_harder_v2_accept_ultra_report\n\n"
            "def test_accepts_report_with_sandbox_and_gate():\n"
            "    report = {'sandbox_id': 's1', 'gate_passed': True, 'verified_findings': []}\n"
            "    assert rlm_harder_v2_accept_ultra_report(report) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_verified_findings_require_repro_command_and_failed_negative_run():\n"
            "    assert rlm_harder_v2_accept_ultra_report({'sandbox_id': 's1', 'gate_passed': True, 'verified_findings': [{'id': 'bug'}]}) is False\n"
            "    assert rlm_harder_v2_accept_ultra_report({'sandbox_id': 's1', 'gate_passed': True, 'verified_findings': [{'id': 'bug', 'repro_command': 'pytest -q test_bug.py', 'negative_exit_code': 1}]}) is True\n"
            "    assert rlm_harder_v2_accept_ultra_report({'sandbox_id': 's1', 'gate_passed': False, 'verified_findings': []}) is False\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_research_citation":
        visible = (
            "from target import rlm_harder_v2_choose_research_claim\n\n"
            "def test_selects_cited_claim_for_topic():\n"
            "    claims = [\n"
            "        {'id': 'a', 'topic': 'routing', 'citation': 'docs/routing.md', 'supported': True},\n"
            "        {'id': 'b', 'topic': 'routing', 'supported': False},\n"
            "    ]\n"
            "    assert rlm_harder_v2_choose_research_claim(claims, 'routing') == 'a'\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_uncited_or_wrong_topic_claims():\n"
            "    claims = [\n"
            "        {'id': 'uncited', 'topic': 'routing', 'supported': True},\n"
            "        {'id': 'wrong-topic', 'topic': 'memory', 'citation': 'docs/memory.md', 'supported': True},\n"
            "        {'id': 'target', 'topic': 'routing', 'citation': 'docs/routing.md', 'supported': True},\n"
            "    ]\n"
            "    assert rlm_harder_v2_choose_research_claim(claims, 'routing') == 'target'\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_lancedb_retrieval":
        visible = (
            "from target import rlm_harder_v2_select_vector_hits\n\n"
            "def test_selects_scored_hits_for_topic_pack():\n"
            "    hits = [\n"
            "        {'id': 'a', 'score': 0.8, 'topic_pack': 'nexus', 'source_id': 'claim-a'},\n"
            "        {'id': 'b', 'score': 0.4, 'topic_pack': 'nexus', 'source_id': 'claim-b'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_vector_hits(hits, 'nexus', 0.7) == ['a']\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_missing_source_and_cross_pack_hits():\n"
            "    hits = [\n"
            "        {'id': 'missing-source', 'score': 0.95, 'topic_pack': 'nexus'},\n"
            "        {'id': 'wrong-pack', 'score': 0.9, 'topic_pack': 'other', 'source_id': 'claim-x'},\n"
            "        {'id': 'target', 'score': 0.75, 'topic_pack': 'nexus', 'source_id': 'claim-t'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_vector_hits(hits, 'nexus', 0.7) == ['target']\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_semantic_searcher_refs":
        visible = (
            "from target import rlm_harder_v2_select_semantic_refs\n\n"
            "def test_selects_gated_semantic_ref_for_topic():\n"
            "    refs = [\n"
            "        {'id': 'a', 'relevance': 0.8, 'topic': 'nexus', 'source_id': 'claim-a', 'gate_passed': True},\n"
            "        {'id': 'b', 'relevance': 0.4, 'topic': 'nexus', 'source_id': 'claim-b', 'gate_passed': True},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_semantic_refs(refs, 'nexus', 0.7) == ['claim-a']\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_ungated_missing_source_and_wrong_topic_refs():\n"
            "    refs = [\n"
            "        {'id': 'ungated', 'relevance': 0.95, 'topic': 'nexus', 'source_id': 'claim-u', 'gate_passed': False},\n"
            "        {'id': 'missing-source', 'relevance': 0.95, 'topic': 'nexus', 'gate_passed': True},\n"
            "        {'id': 'wrong-topic', 'relevance': 0.9, 'topic': 'other', 'source_id': 'claim-x', 'gate_passed': True},\n"
            "        {'id': 'target', 'relevance': 0.75, 'topic': 'nexus', 'source_id': 'claim-t', 'gate_passed': True},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_semantic_refs(refs, 'nexus', 0.7) == ['claim-t']\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_swarm_consensus":
        visible = (
            "from target import rlm_harder_v2_accept_swarm_report\n\n"
            "def test_accepts_consensus_with_two_roles():\n"
            "    report = {'consensus': 'pass', 'findings': [{'role': 'logic', 'evidence': 'a'}, {'role': 'security', 'evidence': 'b'}]}\n"
            "    assert rlm_harder_v2_accept_swarm_report(report) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_single_role_or_missing_evidence():\n"
            "    assert rlm_harder_v2_accept_swarm_report({'consensus': 'pass', 'findings': [{'role': 'logic', 'evidence': 'a'}, {'role': 'logic', 'evidence': 'b'}]}) is False\n"
            "    assert rlm_harder_v2_accept_swarm_report({'consensus': 'pass', 'findings': [{'role': 'logic'}, {'role': 'security', 'evidence': 'b'}]}) is False\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_swarm_quiet_moment":
        visible = (
            "from target import rlm_harder_v2_accept_quiet_moment\n\n"
            "def test_accepts_non_mutating_quiet_moment():\n"
            "    event = {'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': False, 'allowed_actions': ['observe', 'report', 'rollback'], 'observe': {'status': 'observed'}, 'rollback': {'status': 'armed'}}\n"
            "    assert rlm_harder_v2_accept_quiet_moment(event) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_mutating_or_incomplete_quiet_moment():\n"
            "    assert rlm_harder_v2_accept_quiet_moment({'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': True, 'allowed_actions': ['observe', 'report', 'rollback'], 'observe': {'status': 'observed'}, 'rollback': {'status': 'armed'}}) is False\n"
            "    assert rlm_harder_v2_accept_quiet_moment({'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': False, 'allowed_actions': ['observe', 'report'], 'observe': {'status': 'observed'}, 'rollback': {'status': 'armed'}}) is False\n"
            "    assert rlm_harder_v2_accept_quiet_moment({'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': False, 'allowed_actions': ['observe', 'report', 'rollback'], 'observe': {}, 'rollback': {'status': 'armed'}}) is False\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_drone_artifacts":
        visible = (
            "from target import rlm_harder_v2_accept_drone_artifacts\n\n"
            "def test_accepts_completed_drone_artifacts():\n"
            "    artifacts = [{'owner': 'a', 'path': 'reports/a.json'}, {'owner': 'b', 'path': 'reports/b.json'}]\n"
            "    assert rlm_harder_v2_accept_drone_artifacts(artifacts, expected_count=2) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_missing_owner_path_or_count_mismatch():\n"
            "    assert rlm_harder_v2_accept_drone_artifacts([{'owner': 'a', 'path': 'reports/a.json'}], expected_count=2) is False\n"
            "    assert rlm_harder_v2_accept_drone_artifacts([{'owner': 'a'}, {'owner': 'b', 'path': 'reports/b.json'}], expected_count=2) is False\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    if fixture_kind == "rlm_harder_v2_nightshift_recovery":
        visible = (
            "from target import rlm_harder_v2_accept_nightshift\n\n"
            "def test_accepts_invoked_recovered_report():\n"
            "    report = {'recommended': True, 'invoked': True, 'recovered': True, 'report_path': 'reports/nightshift.json'}\n"
            "    assert rlm_harder_v2_accept_nightshift(report) is True\n"
        )
        hidden = visible + (
            "\n"
            "def test_rejects_recommended_without_invocation_or_report():\n"
            "    assert rlm_harder_v2_accept_nightshift({'recommended': True, 'invoked': False, 'recovered': False, 'report_path': ''}) is False\n"
            "    assert rlm_harder_v2_accept_nightshift({'recommended': True, 'invoked': True, 'recovered': True}) is False\n"
        )
        return portable_fixture_test_import(visible), portable_fixture_test_import(hidden)
    return split_fixture_tests(test_code)


def split_nexus_value_fixture_tests(fixture_kind: str, test_code: str) -> tuple[str, str]:
    visible_tests = {
        "nexus_value_hidden_state": (
            "from target import apply_events\n\n"
            "def test_applies_unique_happy_path_events():\n"
            "    events = [{'id': 'a', 'delta': 2}, {'id': 'b', 'delta': 3}]\n"
            "    assert apply_events(events) == {'count': 5, 'seen': ['a', 'b']}\n"
        ),
        "nexus_value_hidden_parser": (
            "from target import normalize_key\n\n"
            "def test_normalize_key_simple_spacing():\n"
            "    assert normalize_key('  User Name  ') == 'user-name'\n"
        ),
        "nexus_value_self_heal_invariant": (
            "from target import merge_limits\n\n"
            "def test_merge_limits_overrides_plain_values():\n"
            "    assert merge_limits({'timeout': 10}, {'timeout': 20}) == {'timeout': 20}\n"
        ),
        "nexus_value_self_heal_timeout": (
            "from target import remaining_ms\n\n"
            "def test_remaining_ms_simple_elapsed_case():\n"
            "    assert remaining_ms(100, 125, 50) == 25\n"
        ),
        "nexus_value_mempalace_secret_redaction": (
            "from target import redact\n\n"
            "def test_redact_preserves_non_secret_fields():\n"
            "    assert redact({'user': 'ada', 'note': 'ok'}) == {'user': 'ada', 'note': 'ok'}\n"
        ),
        "nexus_value_mempalace_deny_default": (
            "from target import can_access\n\n"
            "def test_viewer_can_read_and_admin_can_write():\n"
            "    assert can_access('admin', 'write') is True\n"
            "    assert can_access('viewer', 'read') is True\n"
        ),
        "nexus_value_artifact_claim_rollup": (
            "from target import verified_claims\n\n"
            "def test_verified_claims_accepts_supported_pass():\n"
            "    claims = [{'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'}]\n"
            "    assert verified_claims(claims) == ['a']\n"
        ),
        "nexus_value_artifact_phase_report": (
            "from target import phase_ready\n\n"
            "def test_phase_ready_accepts_pass_with_evidence():\n"
            "    assert phase_ready({'status': 'pass', 'evidence': 'x.json', 'reason': ''}) is True\n"
        ),
        "nexus_value_context_docs_contract": (
            "from target import build_response\n\n"
            "def test_build_response_returns_mapping():\n"
            "    assert isinstance(build_response('ok'), dict)\n"
        ),
        "nexus_value_context_config_contract": (
            "from target import parse_config\n\n"
            "def test_parse_config_preserves_explicit_values():\n"
            "    assert parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n"
        ),
        "nexus_value_trust_phase_aggregator": (
            "from target import overall_status\n\n"
            "def test_overall_status_passes_when_all_phases_pass():\n"
            "    assert overall_status([{'status': 'pass', 'evidence': 'a'}]) == 'pass'\n"
        ),
        "nexus_value_trust_incident_classifier": (
            "from target import classify\n\n"
            "def test_classifier_keeps_open_failed_smoke():\n"
            "    assert classify(False, {'verified': True}) == 'open'\n"
        ),
    }
    visible = visible_tests.get(fixture_kind)
    if visible is None:
        return split_fixture_tests(test_code)
    return portable_fixture_test_import(visible), portable_fixture_test_import(test_code)


def nexus_value_fixture_source(fixture_kind: str) -> tuple[str, str, str]:
    fixtures: dict[str, tuple[str, str]] = {
        "nexus_value_hidden_state": (
            "def apply_events(events):\n"
            "    state = {'count': 0, 'seen': []}\n"
            "    for event in events:\n"
            "        state['count'] += int(event.get('delta', 0))\n"
            "        state['seen'].append(event.get('id'))\n"
            "    return state\n",
            "from target import apply_events\n\n"
            "def test_duplicate_events_are_idempotent():\n"
            "    events = [{'id': 'a', 'delta': 2}, {'id': 'a', 'delta': 2}, {'id': 'b', 'delta': 3}]\n"
            "    assert apply_events(events) == {'count': 5, 'seen': ['a', 'b']}\n",
        ),
        "nexus_value_hidden_parser": (
            "def normalize_key(text):\n"
            "    return text.strip().lower().replace(' ', '-')\n",
            "from target import normalize_key\n\n"
            "def test_normalize_key_boundaries():\n"
            "    assert normalize_key('  User   Name  ') == 'user-name'\n"
            "    assert normalize_key('') == ''\n"
            "    assert normalize_key('API__Token') == 'api-token'\n",
        ),
        "nexus_value_self_heal_invariant": (
            "def merge_limits(defaults, override):\n"
            "    result = defaults\n"
            "    result.update(override or {})\n"
            "    return result\n",
            "from target import merge_limits\n\n"
            "def test_merge_limits_preserves_inputs_and_drops_none():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = merge_limits(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "nexus_value_self_heal_timeout": (
            "def remaining_ms(start_ms, now_ms, timeout_ms):\n"
            "    return timeout_ms - now_ms - start_ms\n",
            "from target import remaining_ms\n\n"
            "def test_remaining_ms_clamps_and_uses_elapsed_time():\n"
            "    assert remaining_ms(100, 125, 50) == 25\n"
            "    assert remaining_ms(100, 200, 50) == 0\n"
            "    assert remaining_ms(100, 90, 50) == 50\n",
        ),
        "nexus_value_mempalace_secret_redaction": (
            "def redact(record):\n"
            "    return dict(record)\n",
            "from target import redact\n\n"
            "def test_redact_never_leaks_secret_fields():\n"
            "    out = redact({'user': 'ada', 'token': 'abc', 'password': 'pw', 'note': 'ok'})\n"
            "    assert out == {'user': 'ada', 'token': '[REDACTED]', 'password': '[REDACTED]', 'note': 'ok'}\n",
        ),
        "nexus_value_mempalace_deny_default": (
            "def can_access(role, scope):\n"
            "    if role == 'admin':\n"
            "        return True\n"
            "    return scope == 'read'\n",
            "from target import can_access\n\n"
            "def test_deny_by_default_for_unknowns_and_missing_scope():\n"
            "    assert can_access('admin', 'write') is True\n"
            "    assert can_access('viewer', 'read') is True\n"
            "    assert can_access('viewer', 'write') is False\n"
            "    assert can_access('unknown', 'read') is False\n"
            "    assert can_access('viewer', None) is False\n",
        ),
        "nexus_value_artifact_claim_rollup": (
            "def verified_claims(claims):\n"
            "    return [claim['id'] for claim in claims if claim.get('status') == 'pass']\n",
            "from target import verified_claims\n\n"
            "def test_claims_need_pass_status_and_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert verified_claims(claims) == ['a']\n",
        ),
        "nexus_value_artifact_phase_report": (
            "def phase_ready(phase):\n"
            "    return phase.get('status') == 'pass'\n",
            "from target import phase_ready\n\n"
            "def test_phase_ready_requires_evidence_and_failure_reason():\n"
            "    assert phase_ready({'status': 'pass', 'evidence': 'x.json', 'reason': ''}) is True\n"
            "    assert phase_ready({'status': 'pass', 'reason': ''}) is False\n"
            "    assert phase_ready({'status': 'fail', 'evidence': 'x.json', 'reason': 'missing claim'}) is False\n"
            "    assert phase_ready({'status': 'fail', 'evidence': 'x.json', 'reason': ''}) is False\n",
        ),
        "nexus_value_context_docs_contract": (
            "FIELD = 'status'\n\n"
            "def build_response(value):\n"
            "    return {FIELD: value}\n",
            "from target import build_response\n\n"
            "def test_response_uses_canonical_result_field():\n"
            "    assert build_response('ok') == {'result': 'ok'}\n",
        ),
        "nexus_value_context_config_contract": (
            "def parse_config(data):\n"
            "    return {'strict': bool(data.get('strict', False)), 'retries': data.get('retries', 0)}\n",
            "from target import parse_config\n\n"
            "def test_config_defaults_follow_strict_contract():\n"
            "    assert parse_config({}) == {'strict': True, 'retries': 3}\n"
            "    assert parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n",
        ),
        "nexus_value_trust_phase_aggregator": (
            "def overall_status(phases):\n"
            "    return 'pass' if all(p.get('status') == 'pass' for p in phases) else 'fail'\n",
            "from target import overall_status\n\n"
            "def test_overall_status_rejects_missing_evidence():\n"
            "    assert overall_status([{'status': 'pass', 'evidence': 'a'}, {'status': 'pass', 'evidence': 'b'}]) == 'pass'\n"
            "    assert overall_status([{'status': 'pass'}, {'status': 'pass', 'evidence': 'b'}]) == 'fail'\n",
        ),
        "nexus_value_trust_incident_classifier": (
            "def classify(smoke_passed, semantic_evidence):\n"
            "    return 'resolved' if smoke_passed else 'open'\n",
            "from target import classify\n\n"
            "def test_classifier_does_not_trust_smoke_without_semantic_evidence():\n"
            "    assert classify(True, {'verified': True}) == 'resolved'\n"
            "    assert classify(True, {'verified': False}) == 'needs_evidence'\n"
            "    assert classify(False, {'verified': True}) == 'open'\n",
        ),
    }
    try:
        target_code, test_code = fixtures[fixture_kind]
    except KeyError as exc:
        raise ValueError(f"unknown_nexus_value_fixture:{fixture_kind}") from exc
    visible_test_code, hidden_test_code = split_nexus_value_fixture_tests(fixture_kind, test_code)
    return target_code, visible_test_code, hidden_test_code


def rlm_harder_fixture_source(fixture_kind: str) -> tuple[str, str, str]:
    fixtures: dict[str, tuple[str, str]] = {
        "rlm_harder_multifile_contract": (
            "CANONICAL_FIELD = 'status'\n\n"
            "def rlm_harder_build_payload(value, meta=None):\n"
            "    payload = {CANONICAL_FIELD: value}\n"
            "    if meta:\n"
            "        payload['meta'] = meta\n"
            "    return payload\n",
            "from target import rlm_harder_build_payload\n\n"
            "def test_uses_result_field_and_preserves_meta():\n"
            "    assert rlm_harder_build_payload('ok', {'source': 'contract'}) == {'result': 'ok', 'meta': {'source': 'contract'}}\n",
        ),
        "rlm_harder_long_context_config": (
            "def rlm_harder_parse_config(data):\n"
            "    strict = bool(data.get('strict', False))\n"
            "    retries = int(data.get('retries', 0))\n"
            "    return {'strict': strict, 'retries': retries}\n",
            "from target import rlm_harder_parse_config\n\n"
            "def test_defaults_follow_current_contract_not_legacy_examples():\n"
            "    assert rlm_harder_parse_config({}) == {'strict': True, 'retries': 3}\n"
            "    assert rlm_harder_parse_config({'strict': False, 'retries': 0}) == {'strict': False, 'retries': 0}\n",
        ),
        "rlm_harder_misleading_trust": (
            "def rlm_harder_overall_status(phases):\n"
            "    if all(phase.get('status') == 'pass' for phase in phases):\n"
            "        return 'pass'\n"
            "    return 'fail'\n",
            "from target import rlm_harder_overall_status\n\n"
            "def test_passing_status_without_artifacts_is_not_verified():\n"
            "    assert rlm_harder_overall_status([{'status': 'pass', 'artifact': 'a'}, {'status': 'pass', 'artifact': 'b'}]) == 'pass'\n"
            "    assert rlm_harder_overall_status([{'status': 'pass'}, {'status': 'pass', 'artifact': 'b'}]) == 'fail'\n",
        ),
        "rlm_harder_second_round_invariant": (
            "def rlm_harder_merge_limits(defaults, override):\n"
            "    result = defaults\n"
            "    result.update(override or {})\n"
            "    return result\n",
            "from target import rlm_harder_merge_limits\n\n"
            "def test_second_round_must_preserve_inputs_and_ignore_none():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_merge_limits(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "rlm_harder_v2_governance_guard": (
            "def rlm_harder_v2_filter_action(action):\n"
            "    return {'allowed': True, 'reason': 'ok'}\n",
            "from target import rlm_harder_v2_filter_action\n\n"
            "def test_blocks_shell_and_delete_actions():\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'read_file'}) == {'allowed': True, 'reason': 'ok'}\n"
            "    assert rlm_harder_v2_filter_action({'tool': 'run_command', 'cmd': 'rm -rf .nexus'}) == {'allowed': False, 'reason': 'governance_block'}\n",
        ),
        "rlm_harder_v2_governance_scope": (
            "def rlm_harder_v2_scope_decision(request):\n"
            "    if request.get('approved'):\n"
            "        return {'allowed': True, 'reason': 'approved'}\n"
            "    return {'allowed': True, 'reason': 'default_allow'}\n",
            "from target import rlm_harder_v2_scope_decision\n\n"
            "def test_unapproved_mutation_is_blocked_but_read_is_allowed():\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'read', 'approved': False}) == {'allowed': True, 'reason': 'read_only'}\n"
            "    assert rlm_harder_v2_scope_decision({'action': 'delete', 'approved': False}) == {'allowed': False, 'reason': 'scope_block'}\n",
        ),
        "rlm_harder_v2_evidence_gap": (
            "def rlm_harder_v2_verified_claims(claims):\n"
            "    return [claim['id'] for claim in claims if claim.get('status') == 'pass']\n",
            "from target import rlm_harder_v2_verified_claims\n\n"
            "def test_requires_artifact_reference():\n"
            "    claims = [\n"
            "        {'id': 'a', 'status': 'pass', 'artifact': 'reports/a.json'},\n"
            "        {'id': 'b', 'status': 'pass'},\n"
            "        {'id': 'c', 'status': 'fail', 'artifact': 'reports/c.json'},\n"
            "    ]\n"
            "    assert rlm_harder_v2_verified_claims(claims) == ['a']\n",
        ),
        "rlm_harder_v2_evidence_replay": (
            "def rlm_harder_v2_accept_receipt(receipt):\n"
            "    return receipt.get('claim') == 'verified'\n",
            "from target import rlm_harder_v2_accept_receipt\n\n"
            "def test_verified_receipt_requires_replay_and_clean_exit():\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 0}) is True\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'exit_code': 0}) is False\n"
            "    assert rlm_harder_v2_accept_receipt({'claim': 'verified', 'replay_command': 'pytest -q', 'exit_code': 1}) is False\n",
        ),
        "rlm_harder_v2_second_round": (
            "def rlm_harder_v2_merge_settings(defaults, override):\n"
            "    out = defaults\n"
            "    out.update(override or {})\n"
            "    return out\n",
            "from target import rlm_harder_v2_merge_settings\n\n"
            "def test_preserves_inputs_and_ignores_none_values():\n"
            "    defaults = {'timeout': 10, 'retries': 2}\n"
            "    merged = rlm_harder_v2_merge_settings(defaults, {'timeout': None, 'jitter': 1})\n"
            "    assert merged == {'timeout': 10, 'retries': 2, 'jitter': 1}\n"
            "    assert defaults == {'timeout': 10, 'retries': 2}\n",
        ),
        "rlm_harder_v2_memory_contract": (
            "def rlm_harder_v2_select_memory_hits(items, task_type, keywords):\n"
            "    return [item for item in items if item.get('task_type') == task_type]\n",
            "from target import rlm_harder_v2_select_memory_hits\n\n"
            "def test_requires_type_and_keyword_overlap():\n"
            "    items = [\n"
            "        {'id': 'old-bug', 'task_type': 'bug', 'keywords': ['invoice', 'rounding']},\n"
            "        {'id': 'target', 'task_type': 'bug', 'keywords': ['websocket', 'timeout']},\n"
            "    ]\n"
            "    assert rlm_harder_v2_select_memory_hits(items, 'bug', ['websocket', 'timeout']) == [items[1]]\n",
        ),
        "rlm_harder_v2_belief_budget": (
            "def rlm_harder_v2_repair_budget(confidence, risk):\n"
            "    return {'rounds': 1, 'needs_evidence': False}\n",
            "from target import rlm_harder_v2_repair_budget\n\n"
            "def test_low_confidence_high_risk_requires_more_evidence():\n"
            "    assert rlm_harder_v2_repair_budget(0.42, 'high') == {'rounds': 3, 'needs_evidence': True}\n"
            "    assert rlm_harder_v2_repair_budget(0.91, 'low') == {'rounds': 1, 'needs_evidence': False}\n",
        ),
        "rlm_harder_v2_autoreason_judge": (
            "def rlm_harder_v2_choose_candidate(candidates):\n"
            "    return max(candidates, key=lambda item: item.get('score', 0)).get('id')\n",
            "from target import rlm_harder_v2_choose_candidate\n\n"
            "def test_selects_supported_highest_score_candidate():\n"
            "    candidates = [{'id': 'a', 'score': 0.4, 'evidence_refs': ['a.json']}, {'id': 'b', 'score': 0.9, 'evidence_refs': ['b.json']}]\n"
            "    assert rlm_harder_v2_choose_candidate(candidates) == 'b'\n",
        ),
        "rlm_harder_v2_ddtree_pruning": (
            "def rlm_harder_v2_prune_candidates(candidates, max_candidates):\n"
            "    ordered = sorted(candidates, key=lambda item: item.get('score', 0), reverse=True)\n"
            "    return [item.get('id') for item in ordered[:max_candidates]]\n",
            "from target import rlm_harder_v2_prune_candidates\n\n"
            "def test_prunes_to_budget_by_score():\n"
            "    candidates = [{'id': 'a', 'score': 0.2, 'risk': 1}, {'id': 'b', 'score': 0.9, 'risk': 1}, {'id': 'c', 'score': 0.6, 'risk': 1}]\n"
            "    assert rlm_harder_v2_prune_candidates(candidates, 2) == ['b', 'c']\n",
        ),
        "rlm_harder_v2_ultra_review_report": (
            "def rlm_harder_v2_accept_ultra_report(report):\n"
            "    return bool(report.get('sandbox_id') and report.get('gate_passed'))\n",
            "from target import rlm_harder_v2_accept_ultra_report\n\n"
            "def test_accepts_report_with_sandbox_and_gate():\n"
            "    report = {'sandbox_id': 's1', 'gate_passed': True, 'verified_findings': []}\n"
            "    assert rlm_harder_v2_accept_ultra_report(report) is True\n",
        ),
        "rlm_harder_v2_research_citation": (
            "def rlm_harder_v2_choose_research_claim(claims, topic):\n"
            "    for claim in claims:\n"
            "        if claim.get('topic') == topic and claim.get('supported'):\n"
            "            return claim.get('id')\n"
            "    return None\n",
            "from target import rlm_harder_v2_choose_research_claim\n\n"
            "def test_selects_cited_claim_for_topic():\n"
            "    claims = [{'id': 'a', 'topic': 'routing', 'citation': 'docs/routing.md', 'supported': True}]\n"
            "    assert rlm_harder_v2_choose_research_claim(claims, 'routing') == 'a'\n",
        ),
        "rlm_harder_v2_lancedb_retrieval": (
            "def rlm_harder_v2_select_vector_hits(hits, topic_pack, min_score):\n"
            "    return [hit.get('id') for hit in hits if hit.get('score', 0) >= min_score and hit.get('topic_pack') == topic_pack]\n",
            "from target import rlm_harder_v2_select_vector_hits\n\n"
            "def test_selects_scored_hits_for_topic_pack():\n"
            "    hits = [{'id': 'a', 'score': 0.8, 'topic_pack': 'nexus', 'source_id': 'claim-a'}]\n"
            "    assert rlm_harder_v2_select_vector_hits(hits, 'nexus', 0.7) == ['a']\n",
        ),
        "rlm_harder_v2_semantic_searcher_refs": (
            "def rlm_harder_v2_select_semantic_refs(refs, topic, min_relevance):\n"
            "    return [ref.get('id') for ref in refs if ref.get('relevance', 0) >= min_relevance]\n",
            "from target import rlm_harder_v2_select_semantic_refs\n\n"
            "def test_selects_gated_semantic_ref_for_topic():\n"
            "    refs = [{'id': 'a', 'relevance': 0.8, 'topic': 'nexus', 'source_id': 'claim-a', 'gate_passed': True}]\n"
            "    assert rlm_harder_v2_select_semantic_refs(refs, 'nexus', 0.7) == ['claim-a']\n",
        ),
        "rlm_harder_v2_swarm_consensus": (
            "def rlm_harder_v2_accept_swarm_report(report):\n"
            "    return report.get('consensus') == 'pass' and len(report.get('findings', [])) >= 2\n",
            "from target import rlm_harder_v2_accept_swarm_report\n\n"
            "def test_accepts_consensus_with_two_roles():\n"
            "    report = {'consensus': 'pass', 'findings': [{'role': 'logic', 'evidence': 'a'}, {'role': 'security', 'evidence': 'b'}]}\n"
            "    assert rlm_harder_v2_accept_swarm_report(report) is True\n",
        ),
        "rlm_harder_v2_swarm_quiet_moment": (
            "def rlm_harder_v2_accept_quiet_moment(event):\n"
            "    return bool(event.get('schema_version') == 'nexus_quiet_moment.v1' and event.get('production_writes_allowed') is False and event.get('allowed_actions') == ['observe', 'report', 'rollback'] and (event.get('observe') or {}).get('status') and (event.get('rollback') or {}).get('status'))\n",
            "from target import rlm_harder_v2_accept_quiet_moment\n\n"
            "def test_accepts_non_mutating_quiet_moment():\n"
            "    event = {'schema_version': 'nexus_quiet_moment.v1', 'production_writes_allowed': False, 'allowed_actions': ['observe', 'report', 'rollback'], 'observe': {'status': 'observed'}, 'rollback': {'status': 'armed'}}\n"
            "    assert rlm_harder_v2_accept_quiet_moment(event) is True\n",
        ),
        "rlm_harder_v2_drone_artifacts": (
            "def rlm_harder_v2_accept_drone_artifacts(artifacts, expected_count):\n"
            "    return len(artifacts) == expected_count and all(item.get('path') for item in artifacts)\n",
            "from target import rlm_harder_v2_accept_drone_artifacts\n\n"
            "def test_accepts_completed_drone_artifacts():\n"
            "    artifacts = [{'owner': 'a', 'path': 'reports/a.json'}, {'owner': 'b', 'path': 'reports/b.json'}]\n"
            "    assert rlm_harder_v2_accept_drone_artifacts(artifacts, expected_count=2) is True\n",
        ),
        "rlm_harder_v2_nightshift_recovery": (
            "def rlm_harder_v2_accept_nightshift(report):\n"
            "    return bool(report.get('recommended') and report.get('invoked') and report.get('recovered'))\n",
            "from target import rlm_harder_v2_accept_nightshift\n\n"
            "def test_accepts_invoked_recovered_report():\n"
            "    report = {'recommended': True, 'invoked': True, 'recovered': True, 'report_path': 'reports/nightshift.json'}\n"
            "    assert rlm_harder_v2_accept_nightshift(report) is True\n",
        ),
    }
    try:
        target_code, test_code = fixtures[fixture_kind]
    except KeyError as exc:
        raise ValueError(f"unknown_rlm_harder_fixture:{fixture_kind}") from exc
    visible_test_code, hidden_test_code = split_rlm_harder_fixture_tests(fixture_kind, test_code)
    return target_code, visible_test_code, hidden_test_code


def portable_fixture_test_import(test_code: str) -> str:
    first, _, rest = test_code.partition("\n")
    prefix = "from target import "
    if not first.startswith(prefix):
        return test_code
    names = [name.strip() for name in first[len(prefix) :].split(",") if name.strip()]
    bindings = "".join(f"{name} = _MOD.{name}\n" for name in names)
    prelude = (
        "import importlib.util\n"
        "from pathlib import Path\n\n"
        "_TARGET_PATH = Path(__file__).resolve().parent / 'target.py'\n"
        "_SPEC = importlib.util.spec_from_file_location('bench_target', _TARGET_PATH)\n"
        "_MOD = importlib.util.module_from_spec(_SPEC)\n"
        "assert _SPEC is not None and _SPEC.loader is not None\n"
        "_SPEC.loader.exec_module(_MOD)\n"
    )
    return prelude + bindings + ("\n" + rest if rest else "")
