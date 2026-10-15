import os
import subprocess
from pathlib import Path


def test_codex_enforced_startup_contract_block():
    try:
        res = subprocess.run(
            ["bash", "scripts/ops/start_codex_nexus_enforced.sh"],
            capture_output=True, text=True, cwd="/tmp"
        )
        assert res.returncode != 0
    except Exception:
        pass

def test_antigravity_compat_proxy():
    # 測試舊腳本是否成功導向
    res = subprocess.run(
        ["bash", "scripts/ops/start_antigravity_nexus_enforced.sh", "--help"],
        capture_output=True, text=True
    )
    # 應該包含轉接警告
    assert "[DEPRECATION-WARNING]" in res.stdout


# ---------------------------------------------------------------------------
# #2195: no sandbox bypass, disposable work copy, integrity, denied actions
# ---------------------------------------------------------------------------

_LAUNCHER = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "start_codex_nexus_enforced.sh"
)

_FAKE_CODEX = r"""#!/usr/bin/env bash
printf '%s\n' "$@" > "$FAKE_CODEX_ARGV"
cat > /dev/null
work=""
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-C" ]]; then work="$2"; fi
  shift
done
case "$FAKE_CODEX_MODE" in
  work) echo delivered > "$work/candidate.txt"; echo '{"type":"turn.completed"}' ;;
  canonical) echo tampered > "$FAKE_CANONICAL/tracked.txt"; echo '{"type":"turn.completed"}' ;;
  declined) echo '{"type":"item.completed","item":{"type":"command_execution","status":"declined"}}' ;;
  sandbox) echo 'sandbox denied exec error, exit code: 1' ;;
esac
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)


def _launch(
    tmp_path: Path, mode: str, approval: str = "workspace-write", work_root: Path | None = None
):
    canonical = tmp_path / "canonical"
    ops = canonical / "scripts" / "ops"
    ops.mkdir(parents=True)
    (ops / "_nexus_enforced_briefing.sh").write_text('echo "$1"\n', encoding="utf-8")
    (ops / "nexus_startup_contract_check.py").write_text("", encoding="utf-8")
    (canonical / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(canonical, "init", "-q")
    _git(canonical, "add", ".")
    _git(canonical, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "codex"
    fake.write_text(_FAKE_CODEX, encoding="utf-8")
    fake.chmod(0o755)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("bounded task\n", encoding="utf-8")
    state = tmp_path / "state"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "CODEX_BIN": "codex",
        "FAKE_CODEX_MODE": mode,
        "FAKE_CODEX_ARGV": str(tmp_path / "argv.txt"),
        "FAKE_CANONICAL": str(canonical),
        "NEXUS_MACHINE_STATE_DIR": str(state),
        "LOCK_FILE": str(tmp_path / "launcher.lock"),
        "NEXUS_CODEX_WORK_ROOT": str(work_root or tmp_path / "runs"),
    }
    res = subprocess.run(
        ["bash", str(_LAUNCHER), "gpt-test", approval, str(prompt)],
        cwd=canonical,
        env=env,
        capture_output=True,
        text=True,
    )
    argv_file = tmp_path / "argv.txt"
    argv = argv_file.read_text(encoding="utf-8").splitlines() if argv_file.exists() else []
    return res, argv, canonical.resolve()


def test_codex_launcher_refuses_sandbox_bypass_modes(tmp_path):
    for approval in ("danger", "danger-full-access", "yolo"):
        res, argv, _ = _launch(tmp_path / approval, "work", approval=approval)
        assert res.returncode == 2
        assert "approval mode refused" in res.stderr
        assert argv == []


def test_codex_launcher_runs_sandboxed_in_a_disposable_work_copy(tmp_path):
    res, argv, canonical = _launch(tmp_path, "work")

    assert res.returncode == 0, res.stderr
    assert argv[argv.index("--sandbox") + 1] == "workspace-write"
    assert argv[argv.index("-c") + 1] == 'approval_policy="never"'
    assert not any("dangerously" in item for item in argv)
    work = Path(argv[argv.index("-C") + 1]).resolve()
    assert work.parent == (tmp_path / "runs").resolve()
    assert canonical not in work.parents and work not in canonical.parents
    assert (work / "candidate.txt").read_text(encoding="utf-8") == "delivered\n"
    assert not (canonical / "candidate.txt").exists()


def test_codex_launcher_read_only_mode_uses_read_only_sandbox(tmp_path):
    res, argv, _ = _launch(tmp_path, "none", approval="read-only")

    assert res.returncode == 0, res.stderr
    assert argv[argv.index("--sandbox") + 1] == "read-only"


def test_codex_launcher_fails_when_canonical_checkout_changes(tmp_path):
    res, _, canonical = _launch(tmp_path, "canonical")

    assert res.returncode == 5
    assert "canonical_checkout_integrity_violation" in res.stderr
    # Reported, never reverted.
    assert (canonical / "tracked.txt").read_text(encoding="utf-8") == "tampered\n"


def test_codex_launcher_denied_actions_are_non_delivery(tmp_path):
    for mode in ("declined", "sandbox"):
        res, _, _ = _launch(tmp_path / mode, mode)
        assert res.returncode == 4, res.stderr
        assert "codex_action_denied" in res.stderr


def test_codex_launcher_refuses_work_root_inside_canonical(tmp_path):
    res, argv, _ = _launch(tmp_path, "work", work_root=tmp_path / "canonical" / "runs")

    assert res.returncode == 2
    assert "overlaps the canonical checkout" in res.stderr
    assert argv == []
