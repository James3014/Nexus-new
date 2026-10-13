from __future__ import annotations

import json
import sys

import pytest

from scripts.ci import nexus_core_observe_dependency as observer


class _Distribution:
    def __init__(self, payload: dict | None) -> None:
        self._payload = payload

    def read_text(self, name: str) -> str | None:
        assert name == "direct_url.json"
        if self._payload is None:
            return None
        return json.dumps(self._payload)


def test_observer_emits_exact_vcs_commit(monkeypatch, capsys) -> None:
    commit = "a" * 40
    monkeypatch.setattr(
        observer.metadata,
        "distribution",
        lambda name: _Distribution({"vcs_info": {"commit_id": commit}}),
    )
    monkeypatch.setattr(sys, "argv", ["observer", "nexus-learning"])

    assert observer.main() == 0
    assert capsys.readouterr().out.strip() == f"git-commit:{commit}"


def test_unknown_dependency_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["observer", "not-trusted"])

    with pytest.raises(SystemExit, match="NEXUS_CORE_DEPENDENCY_ID_INVALID"):
        observer.main()


def test_missing_direct_url_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(observer.metadata, "distribution", lambda name: _Distribution(None))
    monkeypatch.setattr(sys, "argv", ["observer", "nexus-runtime"])

    with pytest.raises(SystemExit, match="NEXUS_CORE_DEPENDENCY_DIRECT_URL_MISSING:nexus-runtime"):
        observer.main()


@pytest.mark.parametrize("commit", ["short", "G" * 40, "a" * 39, "a" * 41])
def test_invalid_commit_identity_fails_closed(monkeypatch, commit: str) -> None:
    monkeypatch.setattr(
        observer.metadata,
        "distribution",
        lambda name: _Distribution({"vcs_info": {"commit_id": commit}}),
    )
    monkeypatch.setattr(sys, "argv", ["observer", "nexus-learning"])

    with pytest.raises(SystemExit, match="NEXUS_CORE_DEPENDENCY_COMMIT_INVALID:nexus-learning"):
        observer.main()
