from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.ops import nexus_gateway_manager_bootstrap as b


def _result(stdout: bytes = b"", stderr: bytes = b"", code: int = 0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=code)


def _runner(*, owner_body: str, target: bytes, tree: str = b.ACCEPTED_TREE):
    def run(command, **_kwargs):
        if command[:2] == ["gh", "api"]:
            payload = {"user": {"login": b.OWNER_LOGIN}, "body": owner_body}
            return _result(json.dumps(payload).encode())
        if command[:4] == ["git", "--git-dir", str(b.REPOSITORY_MIRROR), "rev-parse"]:
            return _result((tree + "\n").encode())
        if command[:4] == ["git", "--git-dir", str(b.REPOSITORY_MIRROR), "show"]:
            return _result(target)
        return _result(stderr=b"unexpected command", code=1)
    return run


def _bind_tmp(monkeypatch, tmp_path: Path, *, predecessor: bytes) -> Path:
    state = tmp_path / "gateway-direct"
    state.mkdir()
    mirror = state / "repository.git"
    mirror.mkdir()
    destination = state / "manager.py"
    destination.write_bytes(predecessor)
    destination.chmod(0o600)
    monkeypatch.setattr(b, "STATE_ROOT", state)
    monkeypatch.setattr(b, "REPOSITORY_MIRROR", mirror)
    monkeypatch.setattr(b, "DESTINATION", destination)
    return destination


def test_dry_run_proves_exact_transition_without_mutation(monkeypatch, tmp_path):
    predecessor = b"old-manager"
    target = b"new-manager"
    destination = _bind_tmp(monkeypatch, tmp_path, predecessor=predecessor)
    monkeypatch.setattr(b, "PREDECESSOR_SHA256", hashlib.sha256(predecessor).hexdigest())
    monkeypatch.setattr(b, "TARGET_SHA256", hashlib.sha256(target).hexdigest())
    owner_body = "owner activation"
    monkeypatch.setattr(b, "OWNER_COMMENT_SHA256", hashlib.sha256(owner_body.encode()).hexdigest())

    result = b.apply_bootstrap(
        dry_run=True,
        runner=_runner(owner_body=owner_body, target=target),
    )

    assert result["status"] == "READY"
    assert result["effect_started"] is False
    assert destination.read_bytes() == predecessor


def test_apply_is_exact_atomic_and_replay_idempotent(monkeypatch, tmp_path):
    predecessor = b"old-manager"
    target = b"new-manager"
    destination = _bind_tmp(monkeypatch, tmp_path, predecessor=predecessor)
    monkeypatch.setattr(b, "PREDECESSOR_SHA256", hashlib.sha256(predecessor).hexdigest())
    monkeypatch.setattr(b, "TARGET_SHA256", hashlib.sha256(target).hexdigest())
    owner_body = "owner activation"
    monkeypatch.setattr(b, "OWNER_COMMENT_SHA256", hashlib.sha256(owner_body.encode()).hexdigest())
    runner = _runner(owner_body=owner_body, target=target)

    first = b.apply_bootstrap(runner=runner)
    second = b.apply_bootstrap(runner=runner)

    assert first["status"] == "CONVERGED"
    assert first["effect_started"] is True
    assert second["status"] == "ALREADY_CONVERGED"
    assert second["effect_started"] is False
    assert destination.read_bytes() == target
    assert destination.stat().st_mode & 0o777 == 0o600


def test_owner_activation_tamper_fails_before_write(monkeypatch, tmp_path):
    predecessor = b"old-manager"
    target = b"new-manager"
    destination = _bind_tmp(monkeypatch, tmp_path, predecessor=predecessor)
    monkeypatch.setattr(b, "PREDECESSOR_SHA256", hashlib.sha256(predecessor).hexdigest())
    monkeypatch.setattr(b, "TARGET_SHA256", hashlib.sha256(target).hexdigest())
    monkeypatch.setattr(b, "OWNER_COMMENT_SHA256", hashlib.sha256(b"expected").hexdigest())

    with pytest.raises(b.BootstrapError, match="OWNER_ACTIVATION_BODY_MISMATCH"):
        b.apply_bootstrap(runner=_runner(owner_body="tampered", target=target))

    assert destination.read_bytes() == predecessor


def test_wrong_predecessor_fails_closed(monkeypatch, tmp_path):
    destination = _bind_tmp(monkeypatch, tmp_path, predecessor=b"foreign-manager")
    target = b"new-manager"
    monkeypatch.setattr(b, "PREDECESSOR_SHA256", hashlib.sha256(b"expected-old").hexdigest())
    monkeypatch.setattr(b, "TARGET_SHA256", hashlib.sha256(target).hexdigest())
    owner_body = "owner activation"
    monkeypatch.setattr(b, "OWNER_COMMENT_SHA256", hashlib.sha256(owner_body.encode()).hexdigest())

    with pytest.raises(b.BootstrapError, match="STABLE_MANAGER_PREDECESSOR_MISMATCH"):
        b.apply_bootstrap(runner=_runner(owner_body=owner_body, target=target))

    assert destination.read_bytes() == b"foreign-manager"


def test_wrong_target_tree_or_bytes_fail_before_write(monkeypatch, tmp_path):
    predecessor = b"old-manager"
    destination = _bind_tmp(monkeypatch, tmp_path, predecessor=predecessor)
    monkeypatch.setattr(b, "PREDECESSOR_SHA256", hashlib.sha256(predecessor).hexdigest())
    monkeypatch.setattr(b, "TARGET_SHA256", hashlib.sha256(b"expected-target").hexdigest())
    owner_body = "owner activation"
    monkeypatch.setattr(b, "OWNER_COMMENT_SHA256", hashlib.sha256(owner_body.encode()).hexdigest())

    with pytest.raises(b.BootstrapError, match="ACCEPTED_TREE_MISMATCH"):
        b.apply_bootstrap(
            runner=_runner(owner_body=owner_body, target=b"expected-target", tree="0" * 40)
        )
    with pytest.raises(b.BootstrapError, match="TARGET_MANAGER_HASH_MISMATCH"):
        b.apply_bootstrap(runner=_runner(owner_body=owner_body, target=b"wrong-target"))

    assert destination.read_bytes() == predecessor
