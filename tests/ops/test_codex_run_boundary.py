"""#2254 items 2, 3, 6: codex disposable HOME, env allowlist, symlink/.git checks."""

import os
import stat
import subprocess
from pathlib import Path

_LAUNCHER = (
    Path(__file__).resolve().parents[2] / "scripts" / "ops" / "start_codex_nexus_enforced.sh"
)

_FAKE_CODEX = r"""#!/usr/bin/env bash
cat > /dev/null
work=""
args=("$@")
while [[ $# -gt 0 ]]; do
  if [[ "$1" == "-C" ]]; then work="$2"; fi
  shift
done
{
  echo "HOME=$HOME"
  echo "CODEX_HOME=${CODEX_HOME:-}"
  echo "TMPDIR=${TMPDIR:-}"
  for p in .ssh .config/gh .gitconfig .codex/history.jsonl .codex/config.toml .codex/sessions .codex/auth.json; do
    if [[ -e "$HOME/$p" ]]; then echo "reach:$p"; fi
  done
  if [[ -e "${CODEX_HOME:-/nonexistent}/auth.json" ]]; then
    echo "auth_mode=$(stat -f %Lp "$CODEX_HOME/auth.json" 2>/dev/null || stat -c %a "$CODEX_HOME/auth.json")"
    if [[ -L "$CODEX_HOME/auth.json" ]]; then echo "auth_is_symlink"; fi
    echo "auth_body=$(cat "$CODEX_HOME/auth.json")"
  fi
  ls -A "${CODEX_HOME:-/nonexistent}" 2>/dev/null | sed 's/^/codexhome:/'
  env | cut -d= -f1 | sed 's/^/envkey:/'
} > "$FAKE_CODEX_DUMP"
case "$FAKE_CODEX_MODE" in
  symlink) ln -s "$FAKE_ESCAPE_DIR" "$work/escape-link" ;;
  filelink) ln -s "$FAKE_ESCAPE_DIR/secret.txt" "$work/escape-file" ;;
  gitptr) echo "gitdir: $FAKE_ESCAPE_DIR" > "$work/.git" ;;
  hidden) mkdir "$work/locked"; ln -s "$FAKE_ESCAPE_DIR" "$work/locked/escape"; chmod 000 "$work/locked" ;;
  nestedgit) mkdir "$work/sub"; ln -s "$FAKE_ESCAPE_DIR" "$work/sub/.git" ;;
  nestedgitdir) mkdir -p "$work/sub/.git"; ln -s "$FAKE_ESCAPE_DIR" "$work/sub/.git/leak" ;;
  inside) ln -s tracked.txt "$work/inside-link" ;;
esac
echo '{"type":"turn.completed"}'
"""


def _git(root: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=root,
        check=True,
        capture_output=True,
    )


def _launch(tmp_path: Path, mode: str, *, prepare=None, report_file: Path | None = None):
    canonical = tmp_path / "canonical"
    ops = canonical / "scripts" / "ops"
    ops.mkdir(parents=True)
    (ops / "_nexus_enforced_briefing.sh").write_text('echo "$1"\n', encoding="utf-8")
    (ops / "nexus_startup_contract_check.py").write_text("", encoding="utf-8")
    (canonical / "tracked.txt").write_text("base\n", encoding="utf-8")
    _git(canonical, "init", "-q")
    _git(canonical, "add", ".")
    _git(canonical, "commit", "-qm", "init")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake = bin_dir / "codex"
    fake.write_text(_FAKE_CODEX, encoding="utf-8")
    fake.chmod(0o755)
    real_home = tmp_path / "realhome"
    (real_home / ".ssh").mkdir(parents=True)
    (real_home / ".ssh" / "id_ed25519").write_text("PRIVATE\n", encoding="utf-8")
    (real_home / ".config" / "gh").mkdir(parents=True)
    (real_home / ".config" / "gh" / "hosts.yml").write_text("token: x\n", encoding="utf-8")
    (real_home / ".gitconfig").write_text("[user]\n\tname = real\n", encoding="utf-8")
    codex_home = real_home / ".codex"
    codex_home.mkdir()
    (codex_home / "auth.json").write_text('{"OPENAI_API_KEY":"sk-fake"}', encoding="utf-8")
    (codex_home / "auth.json").chmod(0o644)
    (codex_home / "history.jsonl").write_text("secret history\n", encoding="utf-8")
    (codex_home / "config.toml").write_text("[mcp_servers.x]\n", encoding="utf-8")
    (codex_home / "sessions").mkdir()
    secret_dir = tmp_path / "secret"
    secret_dir.mkdir()
    (secret_dir / "secret.txt").write_text("s\n", encoding="utf-8")
    if prepare is not None:
        prepare(canonical)
    prompt = tmp_path / "prompt.md"
    prompt.write_text("bounded task\n", encoding="utf-8")
    dump = tmp_path / "dump.txt"
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HOME": str(real_home),
        "CODEX_HOME": str(codex_home),
        "GH_TOKEN": "ghp_fake",
        "GITHUB_TOKEN": "ghp_fake2",
        "SSH_AUTH_SOCK": "/tmp/agent.sock",
        "OPENAI_API_KEY": "sk-ambient",
        "CODEX_BIN": "codex",
        "NEXUS_CODEX_ENV_PASSTHROUGH": "FAKE_CODEX_MODE,FAKE_CODEX_DUMP,FAKE_ESCAPE_DIR,GH_TOKEN",
        "FAKE_CODEX_MODE": mode,
        "FAKE_CODEX_DUMP": str(dump),
        "FAKE_ESCAPE_DIR": str(secret_dir),
        "NEXUS_MACHINE_STATE_DIR": str(tmp_path / "state"),
        "LOCK_FILE": str(tmp_path / "launcher.lock"),
        "NEXUS_CODEX_WORK_ROOT": str(tmp_path / "runs"),
        "XDG_STATE_HOME": str(tmp_path / "xdg"),
        "TMPDIR": str(tmp_path / "tmpdir"),
    }
    env.pop("REPORT_FILE", None)
    if report_file is not None:
        env["REPORT_FILE"] = str(report_file)
    res = subprocess.run(
        ["bash", str(_LAUNCHER), "gpt-test", "workspace-write", str(prompt)],
        cwd=canonical,
        env=env,
        capture_output=True,
        text=True,
    )
    lines = dump.read_text(encoding="utf-8").splitlines() if dump.exists() else []
    return res, lines, real_home, tmp_path / "xdg"


def _value(lines: list[str], key: str) -> str:
    return next(line.split("=", 1)[1] for line in lines if line.startswith(key + "="))


def test_codex_runs_in_a_disposable_home_with_auth_only(tmp_path):
    res, dump, real_home, _ = _launch(tmp_path, "inside")

    assert res.returncode == 0, res.stderr
    home = Path(_value(dump, "HOME"))
    assert home != real_home and real_home not in home.parents
    assert _value(dump, "CODEX_HOME") == str(home / ".codex")
    for forbidden in (".ssh", ".config/gh", ".gitconfig"):
        assert f"reach:{forbidden}" not in dump
    for forbidden in (".codex/history.jsonl", ".codex/config.toml", ".codex/sessions"):
        assert f"reach:{forbidden}" not in dump
    assert [line for line in dump if line.startswith("codexhome:")] == ["codexhome:auth.json"]
    assert "auth_is_symlink" not in dump
    assert "auth_mode=600" in dump
    assert 'auth_body={"OPENAI_API_KEY":"sk-fake"}' in dump
    # Deleted afterwards.
    assert not home.exists()


def test_codex_child_env_is_an_allowlist(tmp_path):
    res, dump, _, _ = _launch(tmp_path, "inside")

    assert res.returncode == 0, res.stderr
    keys = {line.split(":", 1)[1] for line in dump if line.startswith("envkey:")}
    for forbidden in ("GH_TOKEN", "GITHUB_TOKEN", "SSH_AUTH_SOCK", "OPENAI_API_KEY"):
        assert forbidden not in keys
    assert {"PATH", "HOME", "CODEX_HOME", "TMPDIR"} <= keys


def test_codex_run_fails_on_a_planted_escaping_directory_symlink(tmp_path):
    res, _, _, _ = _launch(tmp_path, "symlink")

    assert res.returncode == 6
    assert "codex_target_symlink_or_git_escape" in res.stderr


def test_codex_run_fails_on_a_planted_escaping_file_symlink(tmp_path):
    res, _, _, _ = _launch(tmp_path, "filelink")

    assert res.returncode == 6
    assert "codex_target_symlink_or_git_escape" in res.stderr


def test_codex_run_fails_when_the_git_pointer_is_rewritten(tmp_path):
    res, _, _, _ = _launch(tmp_path, "gitptr")

    assert res.returncode == 6
    assert "codex_target_symlink_or_git_escape" in res.stderr


def test_codex_run_allows_an_inside_symlink_and_committed_escaping_baseline(tmp_path):
    def commit_escaping_link(canonical: Path) -> None:
        os.symlink("/etc/hosts", canonical / "baseline-link")
        _git(canonical, "add", "baseline-link")
        _git(canonical, "commit", "-qm", "baseline escaping link")

    res, _, _, _ = _launch(tmp_path, "inside", prepare=commit_escaping_link)

    assert res.returncode == 0, res.stderr


def test_codex_run_home_is_removed_when_the_run_fails(tmp_path):
    res, dump, _, xdg = _launch(tmp_path, "symlink")

    assert res.returncode == 6
    home = Path(_value(dump, "HOME"))
    assert not home.exists()
    assert stat.S_ISDIR(os.stat(xdg).st_mode)


def test_codex_run_fails_on_an_escaping_symlink_hidden_in_an_unreadable_directory(tmp_path):
    res, _, _, _ = _launch(tmp_path, "hidden")

    assert res.returncode == 6, res.stderr
    assert "codex_target_symlink_or_git_escape" in res.stderr


def test_codex_launcher_creates_its_state_dir_when_report_file_is_set(tmp_path):
    res, dump, _, _ = _launch(tmp_path, "inside", report_file=tmp_path / "elsewhere" / "report.txt")

    assert res.returncode == 0, res.stderr
    assert dump


def test_codex_env_passthrough_refuses_injection_and_credential_names():
    from nexus.executors.codex_run_boundary import codex_child_env

    source = {
        "PATH": "/usr/bin",
        "NEXUS_CODEX_ENV_PASSTHROUGH": "GIT_ASKPASS,GIT_SSH_COMMAND,LD_PRELOAD,DYLD_INSERT_LIBRARIES,"
        "PYTHONPATH,BASH_ENV,NODE_OPTIONS,GH_TOKEN,MY_API_KEY,SAFE_VALUE",
        "GIT_ASKPASS": "x",
        "GIT_SSH_COMMAND": "x",
        "LD_PRELOAD": "x",
        "DYLD_INSERT_LIBRARIES": "x",
        "PYTHONPATH": "x",
        "BASH_ENV": "x",
        "NODE_OPTIONS": "x",
        "GH_TOKEN": "x",
        "MY_API_KEY": "x",
        "SAFE_VALUE": "ok",
    }
    env = codex_child_env(source, home=Path("/h"), tmpdir=Path("/h/tmp"))

    assert env["SAFE_VALUE"] == "ok"
    for name in list(source)[2:-1]:
        assert name not in env


def test_codex_run_fails_on_an_escaping_symlink_named_dot_git_in_a_subdirectory(tmp_path):
    res, _, _, _ = _launch(tmp_path, "nestedgit")

    assert res.returncode == 6, res.stderr


def test_codex_run_fails_on_an_escaping_symlink_inside_a_nested_dot_git_directory(tmp_path):
    res, _, _, _ = _launch(tmp_path, "nestedgitdir")

    assert res.returncode == 6, res.stderr


def test_codex_env_lc_prefix_does_not_pass_credential_shaped_names():
    from nexus.executors.codex_run_boundary import codex_child_env

    env = codex_child_env(
        {"LC_ALL": "C", "LC_GITHUB_TOKEN": "x", "LC_AUTH_SOCK": "x"},
        home=Path("/h"),
        tmpdir=Path("/h/tmp"),
    )

    assert env["LC_ALL"] == "C"
    assert "LC_GITHUB_TOKEN" not in env and "LC_AUTH_SOCK" not in env
