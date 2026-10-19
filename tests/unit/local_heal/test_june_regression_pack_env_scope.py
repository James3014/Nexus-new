"""run_pack must not leak its env switches or depend on one host's paths (Refs #1924).

Before the fix run_pack left NEXUS_REGRESSION_MOCK_LLM / NEXUS_LOCAL_QWEN_BACKEND
set for the rest of the process (14 later tests in the nightly process then ran
against the mock-oracle backend) and read /Users/jameschen/... paths.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from scripts.local_heal import run_june_regression_pack as pack

_KEYS = ("NEXUS_REGRESSION_MOCK_LLM", "NEXUS_LOCAL_QWEN_BACKEND")


@pytest.mark.parametrize("replay_mode", ["mock_oracle", "real_model"])
def test_scoped_pack_env_restores_unset_keys(
    monkeypatch: pytest.MonkeyPatch, replay_mode: str
) -> None:
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    with pack._scoped_pack_env(replay_mode):
        assert os.environ["NEXUS_LOCAL_QWEN_BACKEND"] == "1"
        assert os.environ["NEXUS_REGRESSION_MOCK_LLM"] == (
            "1" if replay_mode == "mock_oracle" else "0"
        )
    for key in _KEYS:
        assert key not in os.environ


def test_scoped_pack_env_restores_preexisting_values_on_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NEXUS_REGRESSION_MOCK_LLM", "caller-mock")
    monkeypatch.setenv("NEXUS_LOCAL_QWEN_BACKEND", "caller-qwen")
    with pytest.raises(RuntimeError), pack._scoped_pack_env("mock_oracle"):
        raise RuntimeError("boom")
    assert os.environ["NEXUS_REGRESSION_MOCK_LLM"] == "caller-mock"
    assert os.environ["NEXUS_LOCAL_QWEN_BACKEND"] == "caller-qwen"


def test_run_pack_uses_given_workspace_root_and_restores_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    for key in _KEYS:
        monkeypatch.delenv(key, raising=False)
    seen: list[tuple[str, Path]] = []
    real_install = pack.install_package

    def fake_install(
        python_exec: str, workspace_path: Path, package_spec: str
    ) -> dict[str, object]:
        seen.append((python_exec, workspace_path))
        return real_install(python_exec, workspace_path, package_spec)

    monkeypatch.setattr(pack, "install_package", fake_install)
    root = tmp_path / "host_root"
    res = pack.run_pack(replay_mode="real_model", workspace_root=root, results_dir=tmp_path / "out")

    assert res["status"] == "completed"
    assert [r["task_id"] for r in res["results"]] == ["astropy__astropy-13236"]
    assert seen == [
        (
            str(root / ".nexus/workspaces/astropy/.venv_12907/bin/python"),
            root / ".nexus/workspaces/astropy",
        )
    ]
    assert (tmp_path / "out" / "results.jsonl").is_file()
    for key in _KEYS:
        assert key not in os.environ


def test_regression_pack_has_no_host_specific_paths() -> None:
    for item in pack.REGRESSION_PACK:
        for field in ("workspace_path", "python_executable"):
            assert "/Users/" not in str(item[field]), (item["task_id"], field)


def test_receipt_stdout_tail_accepts_dict_and_namespace_receipts() -> None:
    """HealOrchestrator stores a dict receipt without stdout_tail (Refs #1926)."""
    from types import SimpleNamespace

    assert pack._receipt_stdout_tail(SimpleNamespace()) == ""
    assert pack._receipt_stdout_tail(SimpleNamespace(verifier_receipt=None)) == ""
    assert (
        pack._receipt_stdout_tail(
            SimpleNamespace(verifier_receipt={"verifier_status": "fail", "receipt_id": "r"})
        )
        == ""
    )
    assert (
        pack._receipt_stdout_tail(
            SimpleNamespace(verifier_receipt={"stdout_tail": "Environment ImportError"})
        )
        == "Environment ImportError"
    )
    assert (
        pack._receipt_stdout_tail(
            SimpleNamespace(verifier_receipt=SimpleNamespace(stdout_tail="BUG PRESENT"))
        )
        == "BUG PRESENT"
    )
