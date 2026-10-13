"""Swarm winner -> Owner-approved integration through the single facade (no model needed)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from nexus.engine.swarm_run import integrate_swarm_winner

FIXTURE = Path(__file__).resolve().parents[2] / "scripts" / "ops" / "wiring_fixtures" / "swarm"
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@invalid"]


def _repo_with_winner(tmp_path: Path) -> tuple[Path, str, dict]:
    ws = tmp_path / "ws"
    ws.mkdir()
    for name in ("calc.py", "repro.py"):
        (ws / name).write_text((FIXTURE / name).read_text(encoding="utf-8"), encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=ws, check=True)
    subprocess.run([*GIT, "add", "-A"], cwd=ws, check=True)
    subprocess.run([*GIT, "commit", "-qm", "fixture"], cwd=ws, check=True)
    base = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ws, text=True).strip()
    subprocess.run(["git", "checkout", "-qb", "battle_t_conservative"], cwd=ws, check=True)
    (ws / "calc.py").write_text(
        (FIXTURE / "calc.py").read_text(encoding="utf-8").replace("a - b", "a + b"),
        encoding="utf-8",
    )
    subprocess.run([*GIT, "commit", "-qam", "swarm winner"], cwd=ws, check=True)
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ws, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ws, text=True).strip()
    subprocess.run(["git", "checkout", "-q", "main"], cwd=ws, check=True)
    subprocess.run(["git", "branch", "-qD", "battle_t_conservative"], cwd=ws, check=True)
    winner = {"strategy": "conservative", "commit": commit, "tree": tree, "verify_result": "pass"}
    return ws, base, winner


def test_without_owner_approval_the_facade_refuses(tmp_path: Path, monkeypatch) -> None:
    ws, base, winner = _repo_with_winner(tmp_path)
    monkeypatch.setenv("NEXUS_SELF_HOSTED_CANONICAL_STATE_DIR", str(tmp_path / "state"))
    record = integrate_swarm_winner(ws, "swarm-t", winner, "", base)
    assert record["attempted"] is True and record["merge_performed"] is False
    assert "unknown task_id" in record["refusal"]


def test_owner_approved_winner_integrates_through_controlled_manager(
    tmp_path: Path, monkeypatch
) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.ops.capability_wiring_audit import owner_fixture_integrate_swarm_winner

    ws, base, winner = _repo_with_winner(tmp_path)
    pending = {
        "task_id": "swarm-t",
        "candidate_commit_sha": winner["commit"],
        "candidate_tree_sha": winner["tree"],
        "target_base_revision": base,
        "target_file": "calc.py",
        "verify_script": "repro.py",
        "integration_branch": "nexus/integration/swarm-t",
    }
    out = owner_fixture_integrate_swarm_winner(ws, pending, winner, tmp_path / "state")
    assert out["lifecycle_status"] == "INTEGRATED", (
        out["integration"].get("refusal"),
        out["status_trail"],
        out["failure_detail"],
    )
    assert out["integration"]["merge_performed"] is True
    head = subprocess.check_output(
        ["git", "rev-parse", "nexus/integration/swarm-t"], cwd=ws, text=True
    ).strip()
    assert (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", winner["commit"], head], cwd=ws
        ).returncode
        == 0
    )
    assert subprocess.run([sys.executable, "repro.py"], cwd=ws).returncode == 0


def test_owner_step_rejects_a_different_commit(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from scripts.ops.capability_wiring_audit import owner_fixture_integrate_swarm_winner

    ws, base, winner = _repo_with_winner(tmp_path)
    pending = {
        "task_id": "swarm-t",
        "candidate_commit_sha": winner["commit"],
        "candidate_tree_sha": winner["tree"],
        "target_base_revision": base,
        "target_file": "calc.py",
        "verify_script": "repro.py",
        "integration_branch": "nexus/integration/swarm-t",
    }
    forged = {**winner, "commit": base}
    out = owner_fixture_integrate_swarm_winner(ws, pending, forged, tmp_path / "state")
    # The approved lifecycle task is bound to the real winner; offering another commit is
    # refused before the facade, and nothing is merged.
    assert out["integration"]["merge_performed"] is False
    assert out["integration"]["refusal"] == "LIFECYCLE_CANDIDATE_MISMATCH"
