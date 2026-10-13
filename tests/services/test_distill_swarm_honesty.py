"""Distill and spec-pack side effects must be honest: no fake tx, no implicit git tags."""

import json
import subprocess
from pathlib import Path

import pytest

from nexus.services.implementation_pack import ImplementationPackGenerator
from nexus.services.mem_palace import MemPalace
from nexus.services.metabolism_engine import SessionMetabolism


def _metabolism(root: Path) -> SessionMetabolism:
    m = SessionMetabolism()
    m.project_root = root
    m.stack_path = root / ".nexus" / "metabolism" / "task_stack.json"
    return m


def _init_repo(root: Path) -> None:
    def run(*args: str) -> None:
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)

    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    (root / "f.txt").write_text("x", encoding="utf-8")
    run("add", "f.txt")
    run("commit", "-qm", "init")


def _tags(root: Path) -> list[str]:
    out = subprocess.run(["git", "tag", "-l"], cwd=root, check=True, capture_output=True, text=True)
    return out.stdout.split()


def test_distill_local_reports_local_only_without_tx(tmp_path):
    result = _metabolism(tmp_path).distill_local()
    assert result["status"] == "LOCAL_ONLY"
    assert result["tx"] is None
    assert result["upload"] == "NOT_PERFORMED"
    seed = Path(result["seed_path"])
    assert seed.is_file()
    assert seed.is_relative_to(tmp_path)
    assert "ar_tx_distilled" not in json.dumps(result)


def test_distill_wrapper_returns_seed_path_not_fake_tx(tmp_path):
    ref = _metabolism(tmp_path).distill({"goal": "g"})
    assert ref.endswith("session_seed.json")
    assert "ar_tx_distilled" not in ref


def test_session_context_empty_when_no_real_data(tmp_path):
    m = _metabolism(tmp_path)
    ctx = m.build_session_context()
    assert ctx["goal"] is None
    assert ctx["context_source"] == "NONE"
    result = m.distill_local()
    seed = json.loads(Path(result["seed_path"]).read_text(encoding="utf-8"))
    assert seed["current_objective"] is None
    assert result["objective"] is None
    assert "v23.7 Recovery" not in json.dumps(seed)


def test_session_context_comes_from_checkpoint(tmp_path):
    m = _metabolism(tmp_path)
    m.save_checkpoint("task-xyz", "step-2", ["step-3"])
    ctx = m.build_session_context()
    assert "task-xyz" in ctx["goal"]
    assert ctx["todo"] == ["step-3"]
    assert ctx["context_source"].startswith("checkpoint:")


def test_session_context_comes_from_mission(tmp_path):
    from nexus.core.mission_contracts import NexusMission

    NexusMission(mission_id="m1", objective="ship the real thing").persist(tmp_path)
    ctx = _metabolism(tmp_path).build_session_context()
    assert ctx["goal"] == "ship the real thing"
    assert ctx["context_source"].startswith("mission:")


def test_cli_distill_source_has_no_hardcoded_context():
    src = (Path(__file__).resolve().parents[2] / "scripts" / "engine" / "nexus_cli.py").read_text(
        encoding="utf-8"
    )
    assert "v23.7 Recovery" not in src
    assert "Arweave TX:" not in src


def test_arweave_distillation_is_labelled_simulated():
    palace = MemPalace.__new__(MemPalace)
    tx = palace.trigger_arweave_distillation({"a": 1})
    assert tx.startswith("SIMULATED-")


@pytest.mark.parametrize("auto_tag,verified", [(None, True), (False, True), (True, False)])
def test_auto_tag_not_performed_by_default_or_unverified(tmp_path, monkeypatch, auto_tag, verified):
    monkeypatch.delenv("NEXUS_SPEC_AUTO_TAG", raising=False)
    _init_repo(tmp_path)
    gen = ImplementationPackGenerator.__new__(ImplementationPackGenerator)
    gen.project_root = tmp_path
    res = gen._execute_auto_tag(100, auto_tag=auto_tag, verified_run=verified)
    assert res["status"] == "NOT_PERFORMED"
    assert _tags(tmp_path) == []


def test_auto_tag_created_only_when_opted_in_and_verified(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_SPEC_AUTO_TAG", raising=False)
    _init_repo(tmp_path)
    gen = ImplementationPackGenerator.__new__(ImplementationPackGenerator)
    gen.project_root = tmp_path
    res = gen._execute_auto_tag(100, auto_tag=True, verified_run=True)
    assert res["status"] == "CREATED"
    assert _tags(tmp_path) == ["spec-v1.100"]


def test_generate_without_tag_flag_creates_no_tag_and_labels_simulated(tmp_path, monkeypatch):
    monkeypatch.delenv("NEXUS_SPEC_AUTO_TAG", raising=False)
    _init_repo(tmp_path)
    gen = ImplementationPackGenerator(tmp_path, "t-honest", augmenter=None)
    out = gen.generate({"goal": "Build the parser module", "deliverables": ["parser.py"]})
    assert out["audit"]["readability_score"] == 100
    assert out["arweave_status"] == "SIMULATED"
    assert out["arweave_tx"].startswith("SIMULATED-")
    assert out["score_basis"] == "READABILITY_LINT_HEURISTIC"
    assert out["tag"]["status"] == "NOT_PERFORMED"
    assert _tags(tmp_path) == []
    side_path = tmp_path / ".nexus" / "runs" / "t-honest" / "spec_side_effects.json"
    assert json.loads(side_path.read_text())["arweave_status"] == "SIMULATED"


def test_generate_with_tag_flag_but_unverified_score_still_no_tag(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SPEC_AUTO_TAG", "1")
    _init_repo(tmp_path)
    gen = ImplementationPackGenerator(tmp_path, "t-honest2", augmenter=None)
    out = gen.generate({"goal": "Build the parser module", "deliverables": ["parser.py"]})
    assert out["tag"]["status"] == "NOT_PERFORMED"
    assert _tags(tmp_path) == []


def _invoke_swarm(monkeypatch, tmp_path, extra_args):
    import os

    import click
    from click.testing import CliRunner

    from scripts.engine.commands import swarm as swarm_mod

    seen = {}

    class _FakeService:
        def execute_bug(self, *_a, **_k):
            seen["env"] = os.environ.get("NEXUS_SPEC_AUTO_TAG")
            return False

    monkeypatch.setattr(swarm_mod, "build_legacy_cli_service", lambda _root: _FakeService())

    @click.group()
    def root():
        pass

    swarm_mod.register(root, tmp_path)
    CliRunner().invoke(root, ["swarm", "run", "smoke", "--output-json", *extra_args])
    return seen


def test_swarm_run_tagging_is_opt_in(tmp_path, monkeypatch):
    monkeypatch.setenv("NEXUS_SPEC_AUTO_TAG", "1")
    assert _invoke_swarm(monkeypatch, tmp_path, [])["env"] is None
    assert _invoke_swarm(monkeypatch, tmp_path, ["--tag"])["env"] == "1"


# ARCHIVED 2026-10-13 legacy-engine: this file tests (in whole or in part) modules archived with
# the legacy NexusEngine (scripts.engine.commands.swarm); see ARCHIVED_2026-10-13-legacy-engine.md.
# It keeps running with unchanged node ids until the deletion PR removes it with those modules.
