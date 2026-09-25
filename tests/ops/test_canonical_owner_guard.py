from __future__ import annotations

import textwrap
from pathlib import Path

from scripts.ops.canonical_owner_guard import (
    CANONICAL_OWNERS,
    _check_forbidden_tree_imports,
    _check_forwarding_module,
    _check_frozen_paths_for_modifications,
    audit_repository_ownership,
)


def test_canonical_owners_mapping_is_complete():
    expected_owners = {
        "nexus-core",
        "nexus-learning",
        "nexus-open-swe-runtime",
        "nexus-runtime",
        "repository-intelligence-engine",
    }
    assert set(CANONICAL_OWNERS.keys()) == expected_owners


def test_current_repo_passes_canonical_owner_audit():
    repo_root = Path(__file__).resolve().parents[2]
    result = audit_repository_ownership(repo_root)
    assert result["status"] == "PASS"
    assert result["issue_count"] == 0
    assert result["issues"] == []


def test_forwarding_module_detects_duplicate_canonical_class(tmp_path: Path):
    fake_module = tmp_path / "outcome_memory.py"
    fake_module.write_text(
        textwrap.dedent("""
        from nexus_learning import CANONICAL_IMPLEMENTATION_MODULE

        class OutcomeMemoryManager:
            def duplicate_canonical_logic(self):
                return True
        """),
        encoding="utf-8",
    )
    issues = _check_forwarding_module(fake_module, ("nexus_learning",))
    assert any("DUPLICATE_CANONICAL_CLASS_IN_FACADE" in issue for issue in issues)


def test_forwarding_module_detects_missing_canonical_reference(tmp_path: Path):
    fake_module = tmp_path / "facade.py"
    fake_module.write_text(
        textwrap.dedent("""
        # Just local definitions without forwarding
        def helper():
            pass
        """),
        encoding="utf-8",
    )
    issues = _check_forwarding_module(fake_module, ("nexus_learning",))
    assert any("FORWARDING_FACADE_MISSING_CANONICAL_REFERENCE" in issue for issue in issues)


def test_forwarding_module_rejects_incidental_runtime_string(tmp_path: Path):
    fake_module = tmp_path / "facade.py"
    fake_module.write_text(
        "_RUNTIME = object()\ndef helper():\n    return _RUNTIME\n",
        encoding="utf-8",
    )
    issues = _check_forwarding_module(fake_module, ("nexus_runtime", "runtime_compat"))
    assert any("FORWARDING_FACADE_MISSING_CANONICAL_REFERENCE" in issue for issue in issues)


def test_forbidden_tree_imports_fail_closed_on_unparseable_active_module(tmp_path: Path):
    nexus_dir = tmp_path / "nexus"
    nexus_dir.mkdir(parents=True)
    (nexus_dir / "broken.py").write_text("def broken(:\n", encoding="utf-8")

    issues = _check_forbidden_tree_imports(tmp_path, ("repository_intelligence",))
    assert any("UNPARSEABLE_ACTIVE_MODULE" in issue for issue in issues)


def test_forbidden_tree_imports_detects_repository_intelligence(tmp_path: Path):
    nexus_dir = tmp_path / "nexus"
    nexus_dir.mkdir(parents=True)
    bad_file = nexus_dir / "bad_consumer.py"
    bad_file.write_text(
        textwrap.dedent("""
        import repository_intelligence
        from repository_intelligence.engine import query
        """),
        encoding="utf-8",
    )
    issues = _check_forbidden_tree_imports(tmp_path, ("repository_intelligence",))
    assert len(issues) == 2
    assert any("FORBIDDEN_IMPORT" in issue for issue in issues)
    assert any("FORBIDDEN_IMPORT_FROM" in issue for issue in issues)


def test_frozen_paths_checks_for_modifications():
    frozen_prefixes = ("product/", "runtimes/open_swe/")
    changed_files = [
        "product/new_feature.py",
        "nexus/engine/capability_planner.py",
        "runtimes/open_swe/nexus_open_swe_runtime/extra.py",
    ]
    issues = _check_frozen_paths_for_modifications(Path("."), frozen_prefixes, changed_files)
    assert len(issues) == 2
    assert any("product/new_feature.py" in issue for issue in issues)
    assert any("runtimes/open_swe/nexus_open_swe_runtime/extra.py" in issue for issue in issues)


def test_audit_fails_on_hostile_fixture(tmp_path: Path):
    # Construct a minimal repo tree
    nexus_dir = tmp_path / "nexus"
    learning_dir = nexus_dir / "learning"
    learning_dir.mkdir(parents=True)

    # Introduce duplicate class in outcome_memory
    outcome_memory = learning_dir / "outcome_memory.py"
    outcome_memory.write_text(
        "from nexus_learning import x\nclass OutcomeMemoryManager:\n    pass\n",
        encoding="utf-8",
    )
    # And valid others
    (learning_dir / "learning_closure_effectiveness.py").write_text(
        "from nexus_learning import x\n"
    )
    (learning_dir / "learning_episode_projection.py").write_text("from nexus_learning import x\n")
    contracts_dir = nexus_dir / "contracts"
    contracts_dir.mkdir()
    (contracts_dir / "learning_experience.py").write_text("from nexus_learning import x\n")

    services_dir = nexus_dir / "services"
    services_dir.mkdir()
    (services_dir / "runtime_compat.py").write_text("from nexus_runtime import x\n")
    (services_dir / "unified_runtime.py").write_text("from nexus_runtime import x\n")

    result = audit_repository_ownership(tmp_path)
    assert result["status"] == "FAIL"
    assert result["issue_count"] > 0
    assert any("DUPLICATE_CANONICAL_CLASS_IN_FACADE" in issue for issue in result["issues"])
