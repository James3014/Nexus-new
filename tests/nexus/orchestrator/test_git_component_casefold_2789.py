"""``.git`` path components are refused case-insensitively (#2789).

The canonical checkout lives on case-insensitive APFS, so ``.GIT/config`` and
``pkg/.gIt/HEAD`` address real git metadata. Every scope / allowlist guard must
refuse a component whose casefold equals ``.git``; ordinary paths behave as before.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nexus.contracts import autonomy_goal, lifecycle_action
from nexus.orchestrator import autonomy_policy, lifecycle_guards, mutation_admission
from nexus.orchestrator import unified_mcp_gateway as gateway
from nexus.orchestrator.task_card_scope import protected_path_reason
from nexus.orchestrator.unified_mcp_gateway_parts import search

GIT_SPELLINGS = (".GIT/x", ".Git/config", "pkg/.gIt/HEAD", ".git/", ".Git", "a/.GIT/hooks/x")
ORDINARY = ("gitignore.py", "src/git.py", "docs/.gitkeep_notes.md", ".gitignore")


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_lifecycle_action_repo_path_refuses_git_any_case(path):
    with pytest.raises(ValueError):
        lifecycle_action._repo_path(path, "allowed_path")


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_autonomy_goal_repo_path_refuses_git_any_case(path):
    with pytest.raises(ValueError):
        autonomy_goal._repo_path(path, "path")


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_autonomy_policy_path_refuses_git_any_case(path):
    with pytest.raises(ValueError):
        autonomy_policy._path(path)


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_lifecycle_guards_repo_relative_refuses_git_any_case(path, tmp_path):
    with pytest.raises(lifecycle_guards.LifecycleGuardError):
        lifecycle_guards._repo_relative(path, root=tmp_path)


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_mutation_admission_refuses_git_any_case(path):
    with pytest.raises(mutation_admission.MutationAdmissionError):
        mutation_admission._validate_scope([path])
    with pytest.raises(mutation_admission.MutationAdmissionError):
        mutation_admission._validate_scope([path.rstrip("/") + "/**"])
    assert mutation_admission.path_is_allowed(path, ("**",)) is False
    assert mutation_admission.path_is_allowed(path, (path.split("/")[0] + "/**",)) is False


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_gateway_safe_relative_path_refuses_git_any_case(path, tmp_path):
    with pytest.raises(gateway.GatewayInputError, match="cannot access .git"):
        gateway._safe_relative_path(path)
    with pytest.raises(gateway.GatewayInputError, match="cannot access .git"):
        gateway._safe_relative_path(path, root=tmp_path)


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_gateway_safe_search_target_refuses_git_any_case(path):
    with pytest.raises(gateway.GatewayInputError, match="cannot access .git"):
        gateway._safe_search_target(path)


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_search_candidate_under_git_any_case_is_not_searchable(path, tmp_path):
    candidate = tmp_path / path.rstrip("/") / "f.txt"
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("x", encoding="utf-8")
    assert search._searchable_file(root=tmp_path, candidate=candidate) is False


@pytest.mark.parametrize("path", GIT_SPELLINGS)
def test_task_card_scope_protects_git_any_case(path):
    assert protected_path_reason(path) == "GIT_METADATA"


@pytest.mark.parametrize("path", ORDINARY)
def test_ordinary_git_lookalikes_still_pass(path, tmp_path):
    assert lifecycle_action._repo_path(path, "allowed_path") == path
    assert autonomy_goal._repo_path(path, "path") == path
    assert autonomy_policy._path(path) == path
    assert lifecycle_guards._repo_relative(path, root=tmp_path) == (tmp_path / path).resolve()
    assert mutation_admission._validate_scope([path]) == (path,)
    assert mutation_admission.path_is_allowed(path, (path,)) is True
    assert gateway._safe_relative_path(path, root=tmp_path) == (tmp_path / path).resolve()
    assert protected_path_reason(path) is None
    candidate = tmp_path / path
    candidate.parent.mkdir(parents=True, exist_ok=True)
    candidate.write_text("x", encoding="utf-8")
    assert search._searchable_file(root=tmp_path, candidate=candidate) is True


def test_github_keeps_its_current_classification(tmp_path):
    # ``.github`` is an authority directory for Task Cards and an ordinary path elsewhere.
    assert protected_path_reason(".github/x") == "AUTHORITY_DIRECTORY"
    assert lifecycle_action._repo_path(".github/x", "allowed_path") == ".github/x"
    assert mutation_admission.path_is_allowed(".github/x", (".github/**",)) is True
    assert (
        gateway._safe_relative_path(".github/x", root=tmp_path)
        == (tmp_path / ".github/x").resolve()
    )


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/state/acceptance-artifacts/t/.git/x", True),
        ("/state/acceptance-artifacts/t/.GIT/x", True),
        ("/state/acceptance-artifacts/t/a/.Git", True),
        ("/state/acceptance-artifacts/t/.gitignore", False),
        ("/state/acceptance-artifacts/t/report.json", False),
    ],
)
def test_acceptance_artifact_guard_refuses_git_metadata_in_any_case(path, expected):
    """Codex r1 on #2790: the external-acceptance artifact guard was case-sensitive."""
    from nexus.orchestrator.self_hosted_task_service import _names_git_metadata

    assert _names_git_metadata(Path(path)) is expected
