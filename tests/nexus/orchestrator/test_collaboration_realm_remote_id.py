"""#2940: a remote ending in ".git/" names the same repository as one ending in ".git"."""

from __future__ import annotations

import pytest

from nexus.orchestrator.collaboration_realm import CollaborationRealmVerifier


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/org/repo",
        "https://github.com/org/repo.git",
        "https://github.com/org/repo/",
        "https://github.com/org/repo.git/",
        "git@github.com:org/repo",
        "git@github.com:org/repo.git",
        "git@github.com:org/repo/",
        "git@github.com:org/repo.git/",
    ],
)
def test_remote_repository_id_normalization(remote: str) -> None:
    assert CollaborationRealmVerifier._remote_repository_id(remote) == "org/repo"
