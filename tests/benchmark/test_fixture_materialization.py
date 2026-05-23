from __future__ import annotations

from pathlib import Path

import pytest

from scripts.bench.fixture_materialization import (
    ExternalFixtureAdapterRequired,
    ExternalFixtureCacheManifest,
    ExternalFixturePolicyError,
    ExternalFixtureRequest,
    FixtureMaterializationResult,
    LocalFixtureSource,
    OfflineCachedExternalFixtureAdapter,
    SandboxedLocalExternalFixtureAdapter,
    materialize_local_fixture,
    nexus_value_fixture_source,
    resolve_external_fixture,
    rlm_harder_fixture_source,
    split_nexus_value_fixture_tests,
    split_rlm_harder_fixture_tests,
)


def test_materialize_local_fixture_writes_visible_hidden_and_extras(tmp_path: Path):
    result = materialize_local_fixture(
        tmp_path,
        task_id="fixture-001",
        source=LocalFixtureSource(
            target_code="VALUE = 1\n",
            visible_test_code="def test_visible():\n    assert True\n",
            hidden_test_code="def test_hidden():\n    assert True\n",
            extra_files={"README.md": "# Contract\n"},
        ),
    )

    assert Path(result.target_file).read_text(encoding="utf-8") == "VALUE = 1\n"
    assert Path(result.visible_test_file).name == "test_visible.py"
    assert Path(result.hidden_test_file).name == "test_hidden.py"
    assert (Path(result.case_dir) / "README.md").read_text(encoding="utf-8") == "# Contract\n"


def test_materialize_local_fixture_supports_visible_only_contract(tmp_path: Path):
    result = materialize_local_fixture(
        tmp_path,
        task_id="fixture-002",
        source=LocalFixtureSource(
            target_code="VALUE = 1\n",
            visible_test_code="def test_visible():\n    assert True\n",
            visible_test_name="test_target.py",
        ),
    )

    assert Path(result.visible_test_file).name == "test_target.py"
    assert result.hidden_test_file == ""
    assert not (Path(result.case_dir) / "test_hidden.py").exists()


def test_materialize_local_fixture_rejects_extra_file_path_escape(tmp_path: Path):
    with pytest.raises(ValueError, match="escapes case dir"):
        materialize_local_fixture(
            tmp_path,
            task_id="fixture-003",
            source=LocalFixtureSource(
                target_code="VALUE = 1\n",
                visible_test_code="def test_visible():\n    assert True\n",
                extra_files={"../escape.md": "nope\n"},
            ),
        )


def test_resolve_external_fixture_fails_closed_until_clone_adapter_exists():
    with pytest.raises(ExternalFixtureAdapterRequired, match="clone/setup adapter is required"):
        resolve_external_fixture(
            ExternalFixtureRequest(
                task_id="external-001",
                repo="https://example.invalid/repo.git",
                repo_ref="main",
                fixture_kind="external_pytest",
            )
        )


def test_resolve_external_fixture_uses_injected_adapter(tmp_path: Path):
    class FakeExternalAdapter:
        def __init__(self) -> None:
            self.requests = []

        def resolve(self, request: ExternalFixtureRequest) -> FixtureMaterializationResult:
            self.requests.append(request)
            target = tmp_path / "target.py"
            visible = tmp_path / "test_visible.py"
            hidden = tmp_path / "test_hidden.py"
            return FixtureMaterializationResult(
                case_dir=str(tmp_path),
                target_file=str(target),
                visible_test_file=str(visible),
                hidden_test_file=str(hidden),
            )

    adapter = FakeExternalAdapter()
    request = ExternalFixtureRequest(
        task_id="external-001",
        repo="https://example.invalid/repo.git",
        repo_ref="main",
        fixture_kind="external_pytest",
        target_file="src/pkg.py",
        test_file="tests/test_pkg.py",
        hidden_test_file="tests/test_hidden.py",
    )

    result = resolve_external_fixture(request, adapter=adapter)

    assert result.target_file == str(tmp_path / "target.py")
    assert adapter.requests == [request]


def test_sandboxed_local_external_fixture_adapter_copies_declared_files(tmp_path: Path):
    source_root = tmp_path / "external_source"
    (source_root / "src").mkdir(parents=True)
    (source_root / "tests").mkdir(parents=True)
    (source_root / "src/pkg.py").write_text("VALUE = 1\n", encoding="utf-8")
    (source_root / "tests/test_pkg.py").write_text("from src.pkg import VALUE\n\ndef test_value():\n    assert VALUE == 1\n", encoding="utf-8")
    (source_root / "tests/test_hidden.py").write_text("def test_hidden():\n    assert True\n", encoding="utf-8")
    workspace = tmp_path / "workspace"
    adapter = SandboxedLocalExternalFixtureAdapter(
        workspace_root=workspace,
        allowed_source_roots=[source_root],
    )

    result = resolve_external_fixture(
        ExternalFixtureRequest(
            task_id="external-local",
            repo=source_root.as_uri(),
            repo_ref="HEAD",
            fixture_kind="external_pytest",
            target_file="src/pkg.py",
            test_file="tests/test_pkg.py",
            hidden_test_file="tests/test_hidden.py",
        ),
        adapter=adapter,
    )

    assert Path(result.case_dir) == workspace / ".nexus" / "bench_cases" / "external-local"
    assert Path(result.target_file).read_text(encoding="utf-8") == "VALUE = 1\n"
    assert Path(result.visible_test_file).name == "test_pkg.py"
    assert Path(result.hidden_test_file).name == "test_hidden.py"


def test_sandboxed_local_external_fixture_adapter_blocks_remote_urls(tmp_path: Path):
    adapter = SandboxedLocalExternalFixtureAdapter(
        workspace_root=tmp_path / "workspace",
        allowed_source_roots=[tmp_path],
    )

    with pytest.raises(ValueError, match="remote external fixture repo not allowed"):
        adapter.resolve(
            ExternalFixtureRequest(
                task_id="remote",
                repo="https://example.invalid/repo.git",
                repo_ref="main",
                target_file="src/pkg.py",
                test_file="tests/test_pkg.py",
            )
        )


def test_sandboxed_local_external_fixture_adapter_blocks_path_escape(tmp_path: Path):
    source_root = tmp_path / "external_source"
    source_root.mkdir()
    (source_root / "target.py").write_text("VALUE = 1\n", encoding="utf-8")
    adapter = SandboxedLocalExternalFixtureAdapter(
        workspace_root=tmp_path / "workspace",
        allowed_source_roots=[source_root],
    )

    with pytest.raises(ValueError, match="escapes external fixture source"):
        adapter.resolve(
            ExternalFixtureRequest(
                task_id="escape",
                repo=str(source_root),
                repo_ref="HEAD",
                target_file="../target.py",
                test_file="target.py",
            )
        )


def test_live_external_fixture_adapter_requires_offline_cache_manifest(tmp_path: Path):
    adapter = OfflineCachedExternalFixtureAdapter(
        workspace_root=tmp_path / "workspace",
        cache_manifest=None,
    )

    with pytest.raises(ExternalFixturePolicyError, match="offline cache manifest is required"):
        adapter.resolve(
            ExternalFixtureRequest(
                task_id="remote",
                repo="https://example.invalid/repo.git",
                repo_ref="main",
                target_file="src/pkg.py",
                test_file="tests/test_pkg.py",
            )
        )


def test_live_external_fixture_adapter_blocks_remote_without_allowlist(tmp_path: Path):
    cache_root = tmp_path / "cache"
    cache_root.mkdir()
    manifest = ExternalFixtureCacheManifest(
        allowed_repo="https://allowed.example/repo.git",
        allowed_ref="main",
        cache_dir=cache_root,
        expected_files=("src/pkg.py", "tests/test_pkg.py"),
    )
    adapter = OfflineCachedExternalFixtureAdapter(
        workspace_root=tmp_path / "workspace",
        cache_manifest=manifest,
    )

    with pytest.raises(ExternalFixturePolicyError, match="not allowed by offline cache manifest"):
        adapter.resolve(
            ExternalFixtureRequest(
                task_id="remote",
                repo="https://example.invalid/repo.git",
                repo_ref="main",
                target_file="src/pkg.py",
                test_file="tests/test_pkg.py",
            )
        )


def test_offline_cached_external_fixture_adapter_materializes_allowlisted_cache(tmp_path: Path):
    cache_root = tmp_path / "cache"
    (cache_root / "src").mkdir(parents=True)
    (cache_root / "tests").mkdir(parents=True)
    (cache_root / "src/pkg.py").write_text("VALUE = 2\n", encoding="utf-8")
    (cache_root / "tests/test_pkg.py").write_text("from src.pkg import VALUE\n\ndef test_value():\n    assert VALUE == 2\n", encoding="utf-8")
    manifest = ExternalFixtureCacheManifest(
        allowed_repo="https://allowed.example/repo.git",
        allowed_ref="abc123",
        cache_dir=cache_root,
        expected_files=("src/pkg.py", "tests/test_pkg.py"),
    )
    adapter = OfflineCachedExternalFixtureAdapter(
        workspace_root=tmp_path / "workspace",
        cache_manifest=manifest,
    )

    result = adapter.resolve(
        ExternalFixtureRequest(
            task_id="remote-cache",
            repo="https://allowed.example/repo.git",
            repo_ref="abc123",
            target_file="src/pkg.py",
            test_file="tests/test_pkg.py",
        )
    )

    assert Path(result.target_file).read_text(encoding="utf-8") == "VALUE = 2\n"
    assert Path(result.visible_test_file).name == "test_pkg.py"


def test_split_nexus_value_fixture_tests_builds_distinct_visible_and_hidden_contracts():
    visible, hidden = split_nexus_value_fixture_tests(
        "nexus_value_hidden_parser",
        "from target import normalize_key\n\n"
        "def test_hidden_contract():\n"
        "    assert normalize_key('User__Name') == 'user-name'\n",
    )

    assert "spec_from_file_location" in visible
    assert "test_normalize_key_simple_spacing" in visible
    assert "User__Name" not in visible
    assert "User__Name" in hidden


def test_split_rlm_harder_fixture_tests_builds_hidden_only_conditions():
    visible, hidden = split_rlm_harder_fixture_tests(
        "rlm_harder_v2_governance_guard",
        "from target import rlm_harder_v2_filter_action\n\n"
        "def test_contract():\n"
        "    assert rlm_harder_v2_filter_action({'tool': 'read_file'})['allowed'] is True\n",
    )

    assert "spec_from_file_location" in visible
    assert "dangerous_shell_is_blocked" in visible
    assert "benchmarks/result.json" not in visible
    assert "benchmarks/result.json" in hidden


def test_nexus_value_fixture_source_keeps_source_and_split_contract_together():
    target_code, visible_test_code, hidden_test_code = nexus_value_fixture_source("nexus_value_hidden_parser")

    assert "def normalize_key" in target_code
    assert "test_normalize_key_simple_spacing" in visible_test_code
    assert "test_normalize_key_boundaries" in hidden_test_code
    assert "spec_from_file_location" in visible_test_code


def test_rlm_harder_fixture_source_keeps_hidden_conditions_in_fixture_module():
    target_code, visible_test_code, hidden_test_code = rlm_harder_fixture_source(
        "rlm_harder_v2_governance_guard"
    )

    assert "def rlm_harder_v2_filter_action" in target_code
    assert "dangerous_shell_is_blocked" in visible_test_code
    assert "benchmarks/result.json" in hidden_test_code
    assert "spec_from_file_location" in hidden_test_code
