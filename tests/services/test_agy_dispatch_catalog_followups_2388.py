"""#2388: Agy model catalog admission follow-ups (#1357 review LOWs).

1. An explicit ``--effort`` must match an effort-suffixed id, and with an
   effort the catalog must serve ``<id>-<effort>`` whenever it encodes tiers.
2. The ``agy models`` fetch is charged to the operation's total deadline.
3. No test reaches a live ``agy models``: tests/conftest.py turns the check
   off unless a test re-enables it.
"""

from __future__ import annotations

import os
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader(
    "nexus_agy_dispatch_catalog_2388", str(ROOT / "scripts" / "ops" / "nexus-agy-dispatch")
).load_module()

TIERED = (
    "gemini-3.8-flash-low\tGemini 3.8 Flash (Low)\n"
    "gemini-3.8-flash-medium\tGemini 3.8 Flash (Medium)\n"
    "gemini-3.8-flash\tGemini 3.8 Flash\n"
    "claude-sonnet-5-5\tClaude Sonnet 5.5\n"
)


def _fake_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog: str) -> dict:
    monkeypatch.setenv("NEXUS_AGY_MODEL_CATALOG_CHECK", "1")
    monkeypatch.setattr(dispatch, "OPERATION_ROOT", tmp_path / "ops")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    out = tmp_path / "catalog.txt"
    out.write_text(catalog, encoding="utf-8")
    calls = tmp_path / "calls.txt"
    fake = bin_dir / "agy"
    fake.write_text(
        f"#!{sys.executable}\nimport sys\nopen({str(calls)!r}, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        f"sys.stdout.write(open({str(out)!r}).read())\n",
        encoding="utf-8",
    )
    fake.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
    home = tmp_path / "home"
    home.mkdir()
    return {"HOME": str(home), "PATH": os.environ["PATH"], "_calls": str(calls)}


def _admit(env: dict, model: str, effort: str | None, **kw):
    return dispatch._agy_model_catalog_admission(
        model=model,
        effort=effort,
        env={k: v for k, v in env.items() if not k.startswith("_")},
        account_alias_hash="acct",
        **kw,
    )


def test_bare_id_with_effort_requires_the_suffixed_tier_when_tiers_exist(tmp_path, monkeypatch):
    env = _fake_catalog(tmp_path, monkeypatch, TIERED)
    assert _admit(env, "gemini-3.8-flash", "low")["admitted"] is True
    unserved = _admit(env, "gemini-3.8-flash", "high")
    assert unserved["admitted"] is False
    assert unserved["model_catalog"]["status"] == "MODEL_CAPABILITY_UNAVAILABLE"


def test_untiered_bare_id_with_effort_is_still_admitted(tmp_path, monkeypatch):
    env = _fake_catalog(tmp_path, monkeypatch, TIERED)
    assert _admit(env, "claude-sonnet-5-5", "high")["admitted"] is True


def test_effort_suffix_and_effort_flag_must_agree():
    assert dispatch._model_effort_suffix("gemini-3.8-flash-medium") == "medium"
    assert dispatch._model_effort_suffix("gemini-3.8-flash") is None
    assert dispatch._model_effort_suffix("claude-sonnet-5-5") is None


def test_dispatch_rejects_a_suffixed_id_with_another_effort_before_any_lease(capsys):
    class _NoLease:
        def acquire_claim(self, **_kw):  # pragma: no cover - must not be reached
            raise AssertionError("leased")

    code = dispatch.dispatch_run(
        prompt="p",
        cwd=str(ROOT),
        mode="plan",
        model="gemini-3.8-flash-medium",
        effort="high",
        coordinator=_NoLease(),
        run_agy_fn=lambda **_kw: (0, "", "", False, 1),
    )
    assert code == 64
    assert (
        "DISPATCH_MODEL_CONTRACT_REJECTED:UNSUPPORTED_EFFORT_FOR_MODEL:gemini-3.8-flash-medium:high"
    ) in capsys.readouterr().err


def test_catalog_fetch_timeout_is_capped_by_the_remaining_budget(tmp_path, monkeypatch):
    env = _fake_catalog(tmp_path, monkeypatch, TIERED)
    seen: list[float] = []
    real_fetch = dispatch._agy_model_catalog_fetch

    def fetch(fetch_env, timeout):
        seen.append(timeout)
        return real_fetch(fetch_env, timeout)

    monkeypatch.setattr(dispatch, "_agy_model_catalog_fetch", fetch)
    _admit(env, "gemini-3.8-flash", "low", max_fetch_seconds=7.5)
    assert seen == [7.5]
    _admit(env, "gemini-3.8-flash-low", None, max_fetch_seconds=-3)  # cached now
    assert seen == [7.5]


def test_catalog_fetch_floor_is_one_second(tmp_path, monkeypatch):
    env = _fake_catalog(tmp_path, monkeypatch, TIERED)
    seen: list[float] = []
    monkeypatch.setattr(
        dispatch, "_agy_model_catalog_fetch", lambda e, t: seen.append(t) or (1, "", "")
    )
    _admit(env, "gemini-3.8-flash", "low", max_fetch_seconds=0.01)
    assert seen == [1.0]


def test_catalog_check_is_off_by_default_in_every_test():
    """The shared tests/conftest.py fixture: no test file reaches a live `agy models`."""
    assert os.environ.get("NEXUS_AGY_MODEL_CATALOG_CHECK") == "0"


def test_disabled_check_never_runs_agy(tmp_path, monkeypatch):
    env = _fake_catalog(tmp_path, monkeypatch, TIERED)
    monkeypatch.setenv("NEXUS_AGY_MODEL_CATALOG_CHECK", "0")
    decision = _admit(env, "gemini-3.8-flash", "low")
    assert decision["model_catalog"]["status"] == "DISABLED"
    assert not Path(env["_calls"]).exists()
