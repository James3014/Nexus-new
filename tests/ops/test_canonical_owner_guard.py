from __future__ import annotations

import subprocess
import textwrap
from pathlib import Path

from scripts.ops.canonical_owner_guard import (
    CANONICAL_OWNERS,
    GUARD_OWN_PATHS,
    OWNERSHIP_FREEZE_BASELINE,
    _check_changed_paths,
    _check_forwarding_module,
    audit_repository_ownership,
    collect_candidate_changed_paths,
)


def _git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


def test_canonical_owners_mapping_is_complete():
    assert set(CANONICAL_OWNERS) == {
        "nexus-core",
        "nexus-learning",
        "nexus-open-swe-runtime",
        "nexus-runtime",
        "repository-intelligence-engine",
    }


def test_current_repo_passes_canonical_owner_audit():
    repo_root = Path(__file__).resolve().parents[2]
    result = audit_repository_ownership(repo_root)
    assert result["baseline_commit"] == OWNERSHIP_FREEZE_BASELINE
    assert result["status"] == "PASS", result["issues"]
    assert result["issue_count"] == 0
    assert set(result["changed_paths_checked"]).issubset(GUARD_OWN_PATHS)


def test_forwarding_module_allows_thin_host_composition(tmp_path: Path):
    module = tmp_path / "facade.py"
    module.write_text(
        textwrap.dedent(
            """
            from nexus_runtime import build_runtime_exports

            def build_host_exports():
                return build_runtime_exports()
            """
        ),
        encoding="utf-8",
    )
    assert _check_forwarding_module(module, canonical_package="nexus_runtime") == []


def test_forwarding_module_detects_local_class_even_with_canonical_import(tmp_path: Path):
    module = tmp_path / "facade.py"
    module.write_text(
        textwrap.dedent(
            """
            from nexus_learning import canonical

            class OutcomeMemoryManager:
                def duplicate_canonical_logic(self):
                    return True
            """
        ),
        encoding="utf-8",
    )
    issues = _check_forwarding_module(module, canonical_package="nexus_learning")
    assert any("LOCAL_CLASS_IN_FORWARDING_FACADE" in issue for issue in issues)


def test_forwarding_module_detects_missing_canonical_reference(tmp_path: Path):
    module = tmp_path / "facade.py"
    module.write_text("def helper():\n    return 1\n", encoding="utf-8")
    issues = _check_forwarding_module(module, canonical_package="nexus_learning")
    assert any("FORWARDING_FACADE_MISSING_CANONICAL_REFERENCE" in issue for issue in issues)


def test_changed_paths_block_all_three_legacy_extraction_surfaces():
    issues = _check_changed_paths(
        [
            "product/new_feature.py",
            "tests/product/test_new_feature.py",
            "tests/benchmark/test_core_v1_new_feature.py",
            "runtimes/open_swe/nexus_open_swe_runtime/new_feature.py",
            "nexus/learning/new_feature.py",
            "nexus/contracts/learning_experience.py",
        ]
    )
    assert len(issues) == 6
    assert any("product/new_feature.py" in issue for issue in issues)
    assert any("runtimes/open_swe" in issue for issue in issues)
    assert any("nexus/learning/new_feature.py" in issue for issue in issues)


def test_changed_paths_block_new_local_package_roots_for_all_extracted_owners():
    issues = _check_changed_paths(
        [
            "nexus_core/new_owner.py",
            "nexus_learning/new_owner.py",
            "nexus_open_swe_runtime/new_owner.py",
            "nexus_runtime/new_owner.py",
            "nexus/runtime/new_owner.py",
            "repository_intelligence/engine.py",
            "repository_intelligence_engine/engine.py",
            "nexus/repository_intelligence/query.py",
        ]
    )
    assert len(issues) == 8
    assert all("SECOND_CANONICAL_IMPLEMENTATION_ROOT" in issue for issue in issues)


def test_changed_paths_allow_current_integration_and_consumer_surfaces():
    assert _check_changed_paths(
        [
            "nexus/services/runtime_compat.py",
            "nexus/services/unified_runtime.py",
            "nexus/services/open_swe_external_intelligence.py",
            "nexus/contracts/changeset_certification.py",
            "nexus/services/repository_intelligence_consumer.py",
        ]
    ) == []


def test_canonical_package_consumption_is_not_forbidden(tmp_path: Path):
    consumer = tmp_path / "consumer.py"
    consumer.write_text(
        "from repository_intelligence import analyze\n"
        "from nexus_runtime import build_runtime_exports\n",
        encoding="utf-8",
    )
    assert consumer.read_text(encoding="utf-8")
    assert _check_changed_paths(["nexus/services/consumer.py"]) == []


def test_collect_candidate_changed_paths_covers_committed_unstaged_and_untracked(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "--initial-branch=main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)

    (repo / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "add", "base.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=repo, check=True)
    baseline = _git(repo, "rev-parse", "HEAD")

    (repo / "committed.txt").write_text("committed\n", encoding="utf-8")
    subprocess.run(["git", "add", "committed.txt"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-m", "candidate"], cwd=repo, check=True)
    (repo / "base.txt").write_text("dirty\n", encoding="utf-8")
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")

    assert collect_candidate_changed_paths(repo, baseline_commit=baseline) == [
        "base.txt",
        "committed.txt",
        "untracked.txt",
    ]


def test_hostile_duplicate_class_fixture_fails(tmp_path: Path):
    module = tmp_path / "facade.py"
    module.write_text(
        "from nexus_learning import canonical\n"
        "class OutcomeMemoryManager:\n"
        "    pass\n",
        encoding="utf-8",
    )
    issues = _check_forwarding_module(module, canonical_package="nexus_learning")
    assert any("LOCAL_CLASS_IN_FORWARDING_FACADE" in issue for issue in issues)
