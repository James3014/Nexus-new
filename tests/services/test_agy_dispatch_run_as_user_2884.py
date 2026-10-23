"""#2884 (Cairnwork #19 Phase B): ``nexus-agy-dispatch --run-as-user _cairnwork_worker``.

Covers the sudo/wrapper argv, the wrapper's refusals (run with its constants
pointed at a temporary layout, so nothing here needs sudo or the worker
account), the cross-run Seatbelt rules, that the leased account HOME is never
modified, copy-in/copy-back, the cross-uid sweep, and that a dispatch without
``--run-as-user`` takes the unchanged path.
"""

from __future__ import annotations

import functools
import grp
import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import time
from importlib.machinery import SourceFileLoader
from pathlib import Path
from typing import Any

import pytest

from nexus.executors import agy_dispatch_boundary as boundary_mod
from nexus.executors import agy_worker_account as worker_mod
from nexus.executors import agy_write_admission as admission
from nexus.executors import cli_worker

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"
WRAPPER = ROOT / "scripts" / "ops" / "agy-worker-exec"
INSTALLER = ROOT / "scripts" / "ops" / "install_agy_worker_exec.sh"

os.environ["NEXUS_AGY_SNAPSHOT"] = str(ROOT)
dispatch = SourceFileLoader("nexus_agy_dispatch_run_as_user_2884", str(DISPATCH_PATH)).load_module()

TOKEN = Path(".gemini") / "antigravity-cli" / "antigravity-oauth-token"
INSTALLATION_ID = Path(".gemini") / "antigravity-cli" / "installation_id"


# ---------------------------------------------------------------------------
# a tiny SBPL evaluator (last matching rule wins), enough for these profiles
# ---------------------------------------------------------------------------


def _sexprs(text: str) -> list:
    tokens = re.findall(r'#?"(?:[^"\\]|\\.)*"|[()]|[^\s()]+', re.sub(r";[^\n]*", "", text))
    stack: list[list] = [[]]
    for token in tokens:
        if token == "(":
            stack.append([])
        elif token == ")":
            done = stack.pop()
            stack[-1].append(done)
        else:
            stack[-1].append(token)
    assert len(stack) == 1
    return stack[0]


def _effective(profile: str, op: str, path: Path) -> str:
    verdict = "deny"
    target = str(path)
    for form in _sexprs(profile):
        if not form or form[0] not in ("allow", "deny"):
            continue
        ops = [item for item in form[1:] if isinstance(item, str)]
        filters = [item for item in form[1:] if isinstance(item, list)]
        if "default" not in ops and not any(
            o == op or (o.endswith("*") and op.startswith(o[:-1])) for o in ops
        ):
            continue
        if not filters:
            verdict = form[0]
            continue
        for kind, *args in filters:
            value = args[0].strip('"') if args and args[0].startswith('"') else None
            if value is None:
                continue
            if (kind == "literal" and target == value) or (
                kind == "subpath" and (target == value or target.startswith(value + "/"))
            ):
                verdict = form[0]
    return verdict


# ---------------------------------------------------------------------------
# layout fixtures
# ---------------------------------------------------------------------------


def _layout(tmp_path: Path) -> dict[str, Any]:
    base = tmp_path.resolve()
    runs = base / "worker-runs"
    runs.mkdir()
    os.chmod(runs, 0o2710)
    bin_dir = base / "bin"
    bin_dir.mkdir()
    os.chmod(bin_dir, 0o755)
    wrapper = bin_dir / "agy-worker-exec"
    shutil.copyfile(WRAPPER, wrapper)
    os.chmod(wrapper, 0o755)
    source_agy = base / "owner-bin" / "agy"
    source_agy.parent.mkdir()
    os.chmod(source_agy.parent, 0o755)  # the refresh refuses a group-writable source dir
    source_agy.write_text("#!/bin/sh\necho agy\n", encoding="utf-8")
    os.chmod(source_agy, 0o755)
    worker_agy = bin_dir / "agy"
    shutil.copyfile(source_agy, worker_agy)
    os.chmod(worker_agy, 0o755)
    home = base / "pool" / "google-07" / "home"
    for rel, text in ((TOKEN, "token"), (INSTALLATION_ID, "install-id")):
        (home / rel).parent.mkdir(parents=True, exist_ok=True)
        (home / rel).write_text(text, encoding="utf-8")
    (home / ".gemini" / "antigravity-cli" / "settings.json").write_text("{}\n", encoding="utf-8")
    target = base / "attempt"
    (target / "src").mkdir(parents=True)
    (target / "src" / "a.py").write_text("print('a')\n", encoding="utf-8")
    (target / "README.md").write_text("readme\n", encoding="utf-8")
    (target / ".git").mkdir()
    (target / ".git" / "HEAD").write_text("ref: refs/heads/cwt-hidden\n", encoding="utf-8")
    (target / ".agents").mkdir()
    (target / ".agents" / "hooks.json").write_text("{}\n", encoding="utf-8")
    return {
        "runs": runs,
        "bin": bin_dir,
        "wrapper": wrapper,
        "source_agy": source_agy,
        "worker_agy": worker_agy,
        "home": home,
        "pool": base / "pool",
        "target": target,
    }


@pytest.fixture
def worker_env(tmp_path, monkeypatch):
    """A temporary worker layout; the worker user and run group map to ourselves."""
    layout = _layout(tmp_path)
    gid = os.getgid()
    monkeypatch.setattr(worker_mod.pwd, "getpwnam", lambda name: object())
    monkeypatch.setattr(worker_mod.os, "getgroups", lambda: [gid])
    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    # The run group is ours, so the boundary's chgrp calls are no-ops.
    os.chown(layout["runs"], -1, gid)
    os.chmod(layout["runs"], 0o2710)  # chown clears setgid
    layout["group"] = grp.getgrgid(gid).gr_name
    layout["gid"] = gid
    return layout


def _prepare(layout: dict, **overrides):
    kwargs: dict[str, Any] = dict(
        source_env={"HOME": str(layout["home"]), "PATH": "/usr/bin:/bin", "GH_TOKEN": "x"},
        target=layout["target"],
        worker_user=worker_mod.WORKER_USER,
        source_agy=str(layout["source_agy"]),
        runs_dir=layout["runs"],
        wrapper=layout["wrapper"],
        worker_agy=layout["worker_agy"],
        run_group=layout["group"],
        repo_wrapper=WRAPPER,
    )
    kwargs.update(overrides)
    return worker_mod.prepare_worker_account_boundary(**kwargs)


def _tree_state(root: Path) -> dict[str, tuple]:
    state = {}
    for path in sorted(root.rglob("*")):
        info = os.lstat(path)
        content = path.read_bytes() if stat.S_ISREG(info.st_mode) else b""
        state[str(path)] = (info.st_mode, info.st_uid, info.st_gid, info.st_mtime_ns, content)
    return state


# ---------------------------------------------------------------------------
# argv construction
# ---------------------------------------------------------------------------


def test_worker_argv_is_the_exact_sudo_wrapper_form(tmp_path):
    run_root = Path("/Users/Shared/cairnwork-worker/worker-runs/" + "a" * 32)
    argv = worker_mod.worker_argv(
        ["/Users/james/.local/bin/agy", "--new-project", "--add-dir", str(run_root / "work")],
        run_root=run_root,
        workdir=run_root / "work",
        profile_path=run_root / "agy-dispatch.sb",
    )
    assert argv == [
        "/usr/bin/sudo",
        "-n",
        "-u",
        "_cairnwork_worker",
        "/Users/Shared/cairnwork-worker/bin/agy-worker-exec",
        str(run_root),
        str(run_root / "work"),
        str(run_root / "agy-dispatch.sb"),
        "--",
        "/Users/Shared/cairnwork-worker/bin/agy",
        "--new-project",
        "--add-dir",
        str(run_root / "work"),
    ]


def test_sweep_argv_lists_sorted_unique_pid_tokens():
    run_root = Path("/Users/Shared/cairnwork-worker/worker-runs/" + "b" * 32)
    tokens = ["7:Thu_Oct_22_21:17:38_2026", "42:Thu_Oct_22_21:17:39_2026"]
    assert worker_mod.sweep_argv(run_root, [tokens[1], tokens[0], tokens[1]]) == [
        "/usr/bin/sudo",
        "-n",
        "-u",
        "_cairnwork_worker",
        "/Users/Shared/cairnwork-worker/bin/agy-worker-exec",
        "--sweep",
        str(run_root),
        *tokens,
    ]


def test_pid_start_tokens_keep_only_live_pids_started_since():
    proc = _spawn_sleeper()
    try:
        (token,) = worker_mod.pid_start_tokens([proc.pid, 1, 0], since=None)
        pid, start = token.split(":", 1)
        assert pid == str(proc.pid) and re.fullmatch(
            r"[A-Z][a-z]{2}_[A-Z][a-z]{2}_\d+_[\d:]+_\d{4}", start
        )
        assert worker_mod.pid_start_tokens([proc.pid], since=time.time() + 3600) == []
    finally:
        proc.kill()
        proc.wait()
    assert worker_mod.pid_start_tokens([proc.pid], since=None) == []


def test_cli_accepts_only_the_cairnwork_worker_user(capsys):
    with pytest.raises(SystemExit):
        dispatch.main(["--run-as-user", "root", "--cwd", "/", "x"])
    assert "invalid choice" in capsys.readouterr().err


def test_remap_rules_rewrites_only_paths_inside_cwd(tmp_path):
    cwd = str(tmp_path.resolve())
    rules = [
        f"write_file({cwd}/src/a.py)",
        f"read_file({cwd}/**)",
        f"write_file({cwd}-other/x)",
        "command(*)",
    ]
    assert dispatch._remap_rules_to_workdir(rules, cwd, "/runs/t/work") == [
        "write_file(/runs/t/work/src/a.py)",
        "read_file(/runs/t/work/**)",
        f"write_file({cwd}-other/x)",
        "command(*)",
    ]


# ---------------------------------------------------------------------------
# the wrapper (run as ourselves, constants pointed at a temporary layout)
# ---------------------------------------------------------------------------


def _wrapper_copy(tmp_path: Path, *, ps: str | None = None, lsof: str | None = None) -> dict:
    base = tmp_path.resolve()
    runs = base / "wr-runs"
    runs.mkdir()
    bin_dir = base / "wr-bin"
    bin_dir.mkdir()
    agy = bin_dir / "agy"
    agy.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    os.chmod(agy, 0o755)
    record = base / "sandbox-record.txt"
    sandbox = bin_dir / "fake-sandbox-exec"
    sandbox.write_text(
        "#!/bin/sh\n"
        f'{{ echo "cwd=$(pwd -P)"; echo "umask=$(umask)"; printf "arg=%s\\n" "$@"; env | sort; }} > "{record}"\n',
        encoding="utf-8",
    )
    os.chmod(sandbox, 0o755)
    text = WRAPPER.read_text(encoding="utf-8")
    replacements = {
        "RUNS=/Users/Shared/cairnwork-worker/worker-runs": f"RUNS={runs}",
        "AGY=/Users/Shared/cairnwork-worker/bin/agy": f"AGY={agy}",
        "SANDBOX_EXEC=/usr/bin/sandbox-exec": f"SANDBOX_EXEC={sandbox}",
        "PS=/bin/ps": f"PS={ps or shutil.which('ps')}",
        "LSOF=/usr/sbin/lsof": f"LSOF={lsof or '/nonexistent/lsof'}",
    }
    for old, new in replacements.items():
        assert text.count(old) == 1, old
        text = text.replace(old, new)
    wrapper = bin_dir / "agy-worker-exec"
    wrapper.write_text(text, encoding="utf-8")
    os.chmod(wrapper, 0o755)
    run_root = runs / ("c" * 32)
    (run_root / "work").mkdir(parents=True)
    (run_root / "home").mkdir()
    (run_root / "tmp").mkdir()
    profile = run_root / "agy-dispatch.sb"
    profile.write_text("(version 1)\n", encoding="utf-8")
    return {
        "runs": runs,
        "agy": agy,
        "wrapper": wrapper,
        "record": record,
        "run_root": run_root,
        "work": run_root / "work",
        "profile": profile,
    }


def _run_wrapper(w: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["/bin/sh", str(w["wrapper"]), *args],
        capture_output=True,
        text=True,
        timeout=60,
        env={"PATH": "/usr/bin:/bin", "SECRET_FROM_SUDO": "leak", "HOME": "/owner/home"},
        check=False,
    )


def test_wrapper_execs_sandbox_with_umask_and_fixed_env(tmp_path):
    w = _wrapper_copy(tmp_path)
    done = _run_wrapper(
        w,
        str(w["run_root"]),
        str(w["work"]),
        str(w["profile"]),
        "--",
        str(w["agy"]),
        "--print",
        "hi",
    )
    assert done.returncode == 0, done.stderr
    lines = w["record"].read_text(encoding="utf-8").splitlines()
    assert lines[0] == f"cwd={w['work']}"
    assert lines[1] in ("umask=0007", "umask=007")
    args = [line[4:] for line in lines if line.startswith("arg=")]
    assert args == ["-f", str(w["profile"]), str(w["agy"]), "--print", "hi"]
    env = dict(
        line.split("=", 1) for line in lines[2:] if "=" in line and not line.startswith("arg=")
    )
    env.pop("PWD", None)
    env.pop("SHLVL", None)
    env.pop("_", None)
    assert env == {
        "HOME": f"{w['run_root']}/home",
        "TMPDIR": f"{w['run_root']}/tmp",
        "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
        "LANG": "en_US.UTF-8",
        "USER": env["USER"],
        "LOGNAME": env["USER"],
        "SHELL": "/bin/sh",
        "TERM": "dumb",
        "NEXUS_CLI_WORKER_RUN_TAG": "c" * 32,
    }
    assert (w["run_root"] / ".worker-exec-started").is_file()


def _refused(done: subprocess.CompletedProcess, w: dict) -> bool:
    return done.returncode == 64 and "refusing" in done.stderr and not w["record"].exists()


def test_wrapper_refuses_paths_outside_worker_runs_symlinks_and_other_binaries(tmp_path):
    w = _wrapper_copy(tmp_path)
    run_root, work, profile, agy = w["run_root"], w["work"], w["profile"], w["agy"]
    outside = tmp_path.resolve() / "outside" / ("d" * 32)
    (outside / "work").mkdir(parents=True)
    (outside / "agy-dispatch.sb").write_text("(version 1)\n", encoding="utf-8")
    link_run = w["runs"] / ("e" * 32)
    link_run.symlink_to(run_root)
    nested = run_root / ("f" * 32)
    (nested / "work").mkdir(parents=True)
    badname = w["runs"] / "not-a-run-tag"
    (badname / "work").mkdir(parents=True)
    link_work = run_root / "work-link"
    link_work.symlink_to(work)
    escape_work = run_root / "escape"
    escape_work.symlink_to(outside / "work")
    link_profile = run_root / "profile-link.sb"
    link_profile.symlink_to(outside / "agy-dispatch.sb")
    other_bin = shutil.which("true") or "/bin/true"
    agy_link = w["agy"].parent / "agy-link"
    agy_link.symlink_to(agy)
    cases = {
        "run_root outside worker-runs": [
            str(outside),
            str(outside / "work"),
            str(outside / "agy-dispatch.sb"),
        ],
        "run_root symlink": [
            str(link_run),
            str(link_run / "work"),
            str(link_run / "agy-dispatch.sb"),
        ],
        "run_root nested": [str(nested), str(nested / "work"), str(profile)],
        "run_root bad name": [str(badname), str(badname / "work"), str(profile)],
        "run_root non-canonical": [f"{w['runs']}/../wr-runs/{'c' * 32}", str(work), str(profile)],
        "run_root relative": [os.path.relpath(run_root), str(work), str(profile)],
        "worker-runs itself": [str(w["runs"]), str(work), str(profile)],
        "workdir outside run_root": [str(run_root), str(outside / "work"), str(profile)],
        "workdir is run_root": [str(run_root), str(run_root), str(profile)],
        "workdir symlink": [str(run_root), str(link_work), str(profile)],
        "workdir symlink escape": [str(run_root), str(escape_work), str(profile)],
        "profile outside run_root": [str(run_root), str(work), str(outside / "agy-dispatch.sb")],
        "profile symlink": [str(run_root), str(work), str(link_profile)],
        "profile is a directory": [str(run_root), str(work), str(work)],
    }
    for name, paths in cases.items():
        done = _run_wrapper(w, *paths, "--", str(agy))
        assert _refused(done, w), (name, done.returncode, done.stderr)
    for name, argv in {
        "other binary": [other_bin, "-c", "id"],
        "agy via symlink": [str(agy_link)],
        "shell": ["/bin/sh", "-c", "cat /etc/passwd"],
    }.items():
        done = _run_wrapper(w, str(run_root), str(work), str(profile), "--", *argv)
        assert _refused(done, w), (name, done.stderr)
    for args in (
        [],
        [str(run_root), str(work), str(profile), str(agy)],  # no "--"
        [str(run_root), str(work), str(profile), "--"],
        ["--sweep"],
        ["--sweep", str(outside)],
        ["--sweep", str(link_run)],
        ["--sweep", str(run_root), "12x"],
        ["--sweep", str(run_root), "123"],  # a bare pid has no start time
        ["--sweep", str(run_root), "123:Thu Oct"],
        ["--sweep", str(run_root), "-9"],
    ):
        done = _run_wrapper(w, *args)
        assert _refused(done, w), (args, done.stderr)


def _fake_ps(tmp_path: Path, tagged_lines: str) -> str:
    listing = tmp_path / "ps-listing.txt"
    listing.write_text(tagged_lines, encoding="utf-8")
    fake = tmp_path / "fake-ps"
    fake.write_text(
        "#!/bin/sh\n"
        'for a in "$@"; do [ "$a" = "-E" ] && exec cat ' + f'"{listing}"; done\n'
        f'exec {shutil.which("ps")} "$@"\n',
        encoding="utf-8",
    )
    os.chmod(fake, 0o755)
    return str(fake)


def _spawn_sleeper() -> subprocess.Popen:
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])


def _dead(proc: subprocess.Popen) -> bool:
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return False
    return True


def test_wrapper_sweep_kills_listed_tagged_and_run_cwd_processes(tmp_path):
    listed, tagged, in_cwd, bystander = (_spawn_sleeper() for _ in range(4))
    try:
        tag = "c" * 32
        ps = _fake_ps(
            tmp_path.resolve(),
            f"{tagged.pid} python -c x NEXUS_CLI_WORKER_RUN_TAG={tag} HOME=/x\n"
            f"{bystander.pid} python -c x NEXUS_CLI_WORKER_RUN_TAG={tag}0 HOME=/y\n",
        )
        lsof = tmp_path.resolve() / "fake-lsof"
        w_root = tmp_path.resolve() / "wr-runs" / tag
        lsof.write_text(
            "#!/bin/sh\n"
            f"printf 'p{in_cwd.pid}\\nfcwd\\nn{w_root}/work\\np{bystander.pid}\\nfcwd\\nn{w_root}-other\\n'\n",
            encoding="utf-8",
        )
        os.chmod(lsof, 0o755)
        w = _wrapper_copy(tmp_path, ps=ps, lsof=str(lsof))
        private = w["work"] / "private"
        private.mkdir(mode=0o700)
        (listed_token,) = worker_mod.pid_start_tokens([listed.pid], since=None)
        stale_token = f"{bystander.pid}:Mon_Jan_1_00:00:00_2001"  # pid reused since: spared
        done = _run_wrapper(w, "--sweep", str(w["run_root"]), listed_token, stale_token)
        assert done.returncode == 0, (done.stdout, done.stderr)
        assert done.stdout.strip() == "AGY_WORKER_SWEEP clean"
        assert _dead(listed) and _dead(tagged) and _dead(in_cwd)
        assert bystander.poll() is None  # a longer tag and a sibling path are not this run
        assert stat.S_IMODE(private.stat().st_mode) & 0o070 == 0o070  # handed back to the group
    finally:
        for proc in (listed, tagged, in_cwd, bystander):
            if proc.poll() is None:
                proc.kill()
                proc.wait()


# ---------------------------------------------------------------------------
# boundary preparation, profile, pool untouched
# ---------------------------------------------------------------------------


def test_prepare_builds_private_run_dir_with_copy_home_and_profile(worker_env):
    boundary = _prepare(worker_env)
    try:
        run_root = boundary.run_root
        assert run_root.parent == worker_env["runs"]
        assert re.fullmatch(r"[0-9a-f]{32}", run_root.name)
        assert run_root.name == boundary.run_tag
        assert stat.S_IMODE(run_root.stat().st_mode) == 0o2770
        assert run_root.stat().st_gid == worker_env["gid"]
        work = boundary.target
        assert work == run_root / "work"
        assert (work / "src" / "a.py").read_text() == "print('a')\n"
        assert not (work / ".agents").exists()
        # a fresh one-commit snapshot: no ref or history of the target's .git
        assert not (work / ".git" / "refs" / "heads" / "cwt-hidden").exists()
        log = subprocess.run(
            ["git", "-C", str(work), "log", "--oneline"], capture_output=True, text=True, check=True
        ).stdout.splitlines()
        assert len(log) == 1
        status = subprocess.run(
            ["git", "-C", str(work), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        assert status == ""
        # only the leased account's session files cross into the per-run HOME
        assert (boundary.run_home / TOKEN).read_text() == "token"
        assert (boundary.run_home / INSTALLATION_ID).read_text() == "install-id"
        settings = json.loads((boundary.run_home / admission.AGY_RUN_HOME_SETTINGS).read_text())
        assert settings["permissions"]["deny"] == ["command(*)"]
        assert boundary.env["HOME"] == str(boundary.run_home)
        assert "GH_TOKEN" not in boundary.env
        assert boundary.launch_env == {
            "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
            "LANG": "en_US.UTF-8",
        }
        assert boundary.profile_path == run_root / "agy-dispatch.sb"
        assert boundary.profile_path.read_text() == boundary.profile
        assert boundary.sweep_roots == (str(work), str(run_root))
    finally:
        boundary.cleanup()
    assert not boundary.run_root.exists()


def test_profile_denies_other_runs_and_keeps_the_existing_denies(worker_env):
    boundary = _prepare(worker_env)
    try:
        profile = boundary.profile
        runs, run_root, work = worker_env["runs"], boundary.run_root, boundary.target
        other = runs / ("0" * 32)
        assert f'(deny file-read* file-write* (subpath "{runs}"))' in profile.splitlines()
        assert "(allow signal (target same-sandbox))" in profile.splitlines()
        for op in ("file-read*", "file-write*"):
            assert _effective(profile, op, other / "work" / "secret.py") == "deny", op
            assert _effective(profile, op, other) == "deny", op
            assert _effective(profile, op, runs) == "deny", op
        assert _effective(profile, "file-read*", work / "src" / "a.py") == "allow"
        assert _effective(profile, "file-write*", work / "src" / "a.py") == "allow"
        assert _effective(profile, "file-read*", run_root / "home" / TOKEN) == "allow"
        # the #2202/#2470 write denies inside this run still win
        for path in (
            work / ".git" / "config",
            work / ".agents" / "hooks.json",
            boundary.run_home / admission.AGY_RUN_HOME_SETTINGS,
            worker_env["home"] / TOKEN,
        ):
            assert _effective(profile, "file-write*", path) == "deny", path
        # the normal profile follows the cross-run block unchanged (#2861/#2869/#2875 rules)
        normal = admission.build_seatbelt_profile(
            run_root=run_root,
            writable_target=work,
            run_home=boundary.run_home,
            source_home=worker_env["home"],
        )
        assert normal[len("(version 1)\n(allow default)\n") :] in profile
        for line in admission.LAUNCH_SERVICES_DENY_LINES:
            assert line in profile
    finally:
        boundary.cleanup()


def test_the_account_pool_is_never_modified(worker_env, monkeypatch):
    pool = worker_env["pool"]
    before = _tree_state(pool)
    pool_mode = stat.S_IMODE(pool.stat().st_mode)
    touched: list[str] = []
    real_chmod, real_chown = os.chmod, os.chown

    def guard(real):
        def call(path, *args, **kwargs):
            if str(path).startswith(str(pool)):
                touched.append(str(path))
            return real(path, *args, **kwargs)

        return call

    monkeypatch.setattr(worker_mod.os, "chmod", guard(real_chmod))
    monkeypatch.setattr(worker_mod.os, "chown", guard(real_chown))
    boundary = _prepare(worker_env)
    boundary.before_launch()
    boundary.cleanup()
    assert touched == []
    assert _tree_state(pool) == before
    assert stat.S_IMODE(pool.stat().st_mode) == pool_mode


def test_before_launch_shares_the_run_tree_with_the_group(worker_env):
    boundary = _prepare(worker_env)
    try:
        boundary.before_launch()
        for path in [boundary.run_root, *boundary.run_root.rglob("*")]:
            info = os.lstat(path)
            if stat.S_ISLNK(info.st_mode):
                continue
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISDIR(info.st_mode):
                assert mode == 0o2770, path
            elif path in (
                boundary.profile_path,
                boundary.run_home / admission.AGY_RUN_HOME_SETTINGS,
            ):
                assert mode == 0o640, path
            else:
                assert mode in (0o660, 0o770), (path, oct(mode))
            assert info.st_gid == worker_env["gid"], path
    finally:
        boundary.cleanup()


@pytest.mark.parametrize(
    "overrides, reason",
    [
        ({"worker_user": "root"}, "worker_user_not_allowed"),
        ({"source_agy": None}, "worker_agy_stale"),
    ],
)
def test_prepare_refusals(worker_env, overrides, reason):
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match=reason):
        _prepare(worker_env, **overrides)
    assert list(worker_env["runs"].iterdir()) == []


def test_prepare_refreshes_a_stale_worker_agy_copy(worker_env, capsys):
    # agy updated itself in the Owner's home: the Owner-side copy is replaced, not refused.
    worker_env["source_agy"].write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    boundary = _prepare(worker_env)
    try:
        worker = worker_env["worker_agy"]
        assert worker.read_bytes() == worker_env["source_agy"].read_bytes()
        info = worker.lstat()
        assert stat.S_ISREG(info.st_mode) and stat.S_IMODE(info.st_mode) == 0o755
        assert info.st_uid == os.getuid()
        assert sorted(p.name for p in worker_env["bin"].iterdir()) == ["agy", "agy-worker-exec"]
        assert boundary.worker_agy_refreshed is True
    finally:
        boundary.cleanup()
    again = _prepare(worker_env)  # already current: nothing to refresh
    try:
        assert again.worker_agy_refreshed is False
    finally:
        again.cleanup()


def test_prepare_refresh_failure_refuses_and_leaves_the_copy(worker_env):
    before = worker_env["worker_agy"].read_bytes()
    worker_env["source_agy"].write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    os.chmod(worker_env["bin"], 0o555)  # the temp file cannot be created
    try:
        with pytest.raises(
            boundary_mod.AgyWriteBoundaryError,
            match="worker_agy_stale_refresh_failed:PermissionError",
        ):
            _prepare(worker_env)
    finally:
        os.chmod(worker_env["bin"], 0o755)
    assert worker_env["worker_agy"].read_bytes() == before
    assert sorted(p.name for p in worker_env["bin"].iterdir()) == ["agy", "agy-worker-exec"]
    assert list(worker_env["runs"].iterdir()) == []


def test_prepare_refresh_follows_a_symlinked_source_but_never_replaces_the_wrapper(worker_env):
    real = worker_env["source_agy"].with_name("agy-1.4.6")
    real.write_text("#!/bin/sh\necho versioned agy\n", encoding="utf-8")
    os.chmod(real, 0o755)
    worker_env["source_agy"].unlink()
    worker_env["source_agy"].symlink_to(real)
    wrapper_before = worker_env["wrapper"].read_bytes()
    boundary = _prepare(worker_env)
    try:
        assert not worker_env["worker_agy"].is_symlink()
        assert worker_env["worker_agy"].read_bytes() == real.read_bytes()
        assert worker_env["wrapper"].read_bytes() == wrapper_before
    finally:
        boundary.cleanup()


def test_prepare_refresh_never_publishes_a_source_others_cannot_read(worker_env):
    # The worker copy is world-readable: an owner-only file (a key, say) never lands there.
    before = worker_env["worker_agy"].read_bytes()
    worker_env["source_agy"].write_text("SECRET\n", encoding="utf-8")
    os.chmod(worker_env["source_agy"], 0o700)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="worker_agy_stale_source_unsafe"):
        _prepare(worker_env)
    assert worker_env["worker_agy"].read_bytes() == before
    assert sorted(p.name for p in worker_env["bin"].iterdir()) == ["agy", "agy-worker-exec"]


def test_prepare_refresh_refuses_a_source_in_a_directory_others_can_write(worker_env):
    # Another user could swap a path component there, so the path proves nothing.
    before = worker_env["worker_agy"].read_bytes()
    shared = worker_env["source_agy"].parent / "shared-dir"
    shared.mkdir()
    os.chmod(shared, 0o777)
    real = shared / "agy"
    real.write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    os.chmod(real, 0o755)
    worker_env["source_agy"].unlink()
    worker_env["source_agy"].symlink_to(real)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="worker_agy_stale_source_unsafe"):
        _prepare(worker_env)
    assert worker_env["worker_agy"].read_bytes() == before


def test_prepare_refresh_refuses_a_symlinked_source_planted_in_a_directory_others_can_write(
    worker_env,
):
    # An early PATH entry others can write: realpath would land somewhere safe.
    before = worker_env["worker_agy"].read_bytes()
    real = worker_env["source_agy"]
    real.write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    planted_dir = real.parent.parent / "shared-path-dir"
    planted_dir.mkdir()
    os.chmod(planted_dir, 0o777)
    (planted_dir / "agy").symlink_to(real)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="worker_agy_stale_source_unsafe"):
        _prepare(worker_env, source_agy=planted_dir / "agy")
    assert worker_env["worker_agy"].read_bytes() == before


def test_prepare_refresh_refuses_a_worker_bin_others_can_write(worker_env):
    before = worker_env["worker_agy"].read_bytes()
    worker_env["source_agy"].write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    os.chmod(worker_env["bin"], 0o775)
    try:
        with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="worker_bin_unsafe"):
            _prepare(worker_env)
    finally:
        os.chmod(worker_env["bin"], 0o755)
    assert worker_env["worker_agy"].read_bytes() == before


def _swap_on_open(monkeypatch, name: str, swap, *, after_open: bool) -> None:
    """Run ``swap`` once, just before or just after the refresh opens ``name``.

    The refresh opens each path component relative to its parent (``dir_fd``).
    """
    real_open = os.open
    pending = [swap]

    def fake_open(path, flags, *args, **kwargs):
        hit = pending and "dir_fd" in kwargs and os.fspath(path) == name
        if hit and not after_open:
            pending.pop()()
        fd = real_open(path, flags, *args, **kwargs)
        if hit and after_open and pending:
            pending.pop()()
        return fd

    monkeypatch.setattr(worker_mod.os, "open", fake_open)


def test_prepare_refresh_refuses_a_source_swapped_for_a_symlink_before_open(
    worker_env, monkeypatch
):
    before = worker_env["worker_agy"].read_bytes()
    source = worker_env["source_agy"]
    source.write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    secret = source.with_name("owner-key")
    secret.write_text("SECRET\n", encoding="utf-8")
    os.chmod(secret, 0o600)

    def swap():
        source.unlink()
        source.symlink_to(secret)

    _swap_on_open(monkeypatch, Path(os.path.realpath(source)).name, swap, after_open=False)
    with pytest.raises(
        boundary_mod.AgyWriteBoundaryError, match="worker_agy_stale_refresh_failed:OSError"
    ):
        _prepare(worker_env)
    assert worker_env["worker_agy"].read_bytes() == before
    assert sorted(p.name for p in worker_env["bin"].iterdir()) == ["agy", "agy-worker-exec"]


def test_prepare_refresh_refuses_a_directory_swapped_for_a_symlink_mid_path(
    worker_env, monkeypatch
):
    # A directory on the path swapped for a symlink to a private directory
    # holding a 0755 file: the walk refuses instead of publishing those bytes.
    before = worker_env["worker_agy"].read_bytes()
    base = worker_env["source_agy"].parent
    sub = base / "agy-dir"
    sub.mkdir()
    os.chmod(sub, 0o755)
    real = sub / "agy"
    real.write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    os.chmod(real, 0o755)
    private = base / "private-dir"
    private.mkdir()
    (private / "agy").write_text("SECRET\n", encoding="utf-8")
    os.chmod(private / "agy", 0o755)
    os.chmod(private, 0o700)
    worker_env["source_agy"].unlink()
    worker_env["source_agy"].symlink_to(real)

    def swap():
        sub.rename(base / "agy-dir-old")
        sub.symlink_to(private)

    _swap_on_open(monkeypatch, "agy-dir", swap, after_open=False)
    # O_DIRECTORY|O_NOFOLLOW on a symlink: ENOTDIR on macOS, ELOOP on Linux.
    with pytest.raises(
        boundary_mod.AgyWriteBoundaryError,
        match="worker_agy_stale_refresh_failed:(NotADirectoryError|OSError)",
    ):
        _prepare(worker_env)
    assert worker_env["worker_agy"].read_bytes() == before
    assert sorted(p.name for p in worker_env["bin"].iterdir()) == ["agy", "agy-worker-exec"]


def test_prepare_refresh_copies_the_checked_file_even_if_the_path_is_swapped_after_open(
    worker_env, monkeypatch
):
    source = worker_env["source_agy"]
    source.write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    checked = source.read_bytes()
    other = source.with_name("other-agy")
    other.write_text("#!/bin/sh\necho swapped\n", encoding="utf-8")
    os.chmod(other, 0o755)

    _swap_on_open(
        monkeypatch,
        Path(os.path.realpath(source)).name,
        lambda: os.replace(other, source),
        after_open=True,
    )
    # The copy holds the bytes that were checked; the re-check then sees the
    # source changed and refuses rather than launching.
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="worker_agy_stale$"):
        _prepare(worker_env)
    assert worker_env["worker_agy"].read_bytes() == checked
    assert sorted(p.name for p in worker_env["bin"].iterdir()) == ["agy", "agy-worker-exec"]


def test_prepare_refuses_a_bad_layout(worker_env, monkeypatch):
    runs = worker_env["runs"]
    os.chmod(runs, 0o2770)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="worker_runs_wrong_mode"):
        _prepare(worker_env)
    os.chmod(runs, 0o2710)
    worker_env["wrapper"].write_text('#!/bin/sh\nexec "$@"\n', encoding="utf-8")
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="wrapper_stale"):
        _prepare(worker_env)
    shutil.copyfile(WRAPPER, worker_env["wrapper"])
    # A stale copy is refreshed (below); one whose source anyone else can write is not.
    worker_env["source_agy"].write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    os.chmod(worker_env["source_agy"], 0o775)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="worker_agy_stale_source_unsafe"):
        _prepare(worker_env)
    os.chmod(worker_env["source_agy"], 0o755)
    shutil.copyfile(worker_env["worker_agy"], worker_env["source_agy"])
    monkeypatch.setattr(worker_mod.os, "getgroups", lambda: [])
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="owner_not_in_run_group"):
        _prepare(worker_env)
    link = worker_env["runs"].parent / "runs-link"
    link.symlink_to(runs)
    monkeypatch.setattr(worker_mod.os, "getgroups", lambda: [worker_env["gid"]])
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="worker_runs_missing"):
        _prepare(worker_env, runs_dir=link)
    assert list(runs.iterdir()) == []


# ---------------------------------------------------------------------------
# sweep across the uid boundary, copy-back, cleanup
# ---------------------------------------------------------------------------


class _Tracker:
    probe_failed = False

    def __init__(self, pids):
        self.pids = set(pids)

    def stop(self):
        return set(self.pids)


class _Run:
    def __init__(self, stdout: str, returncode: int = 0):
        self.calls: list[list[str]] = []
        self.stdout, self.returncode = stdout, returncode

    def __call__(self, argv, **kwargs):
        self.calls.append(list(argv))
        assert kwargs["cwd"] == "/"
        assert kwargs["env"] == worker_mod.LAUNCH_ENV
        return subprocess.CompletedProcess(argv, self.returncode, self.stdout, "")


def _launched(boundary, monkeypatch, *, owner_clean=True, tracked=()):
    boundary.before_launch()
    boundary._launched = True
    boundary._tracker = _Tracker(tracked)
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: owner_clean)
    (boundary.run_root / worker_mod.WRAPPER_STARTED_MARKER).write_text("", encoding="utf-8")


def test_sweep_kills_through_the_wrapper_and_needs_both_sides_clean(worker_env, monkeypatch):
    run = _Run("AGY_WORKER_SWEEP clean\n")
    boundary = _prepare(worker_env, run_command=run)
    early = _spawn_sleeper()  # started before the run: never listed
    time.sleep(2.5)  # ps start times have 1 s resolution and a 1 s margin
    _launched(boundary, monkeypatch)
    child = _spawn_sleeper()
    boundary._tracker = _Tracker((child.pid, early.pid, 99999999))
    try:
        assert boundary.sweep() is True
        expected = worker_mod.pid_start_tokens([child.pid], since=None)
        assert len(expected) == 1
    finally:
        for proc in (early, child):
            proc.kill()
            proc.wait()
    assert run.calls == [
        worker_mod.sweep_argv(boundary.run_root, expected, wrapper=worker_env["wrapper"])
    ]
    assert boundary.sweep() is True and len(run.calls) == 1  # runs once
    boundary.cleanup()

    for stdout, code, owner_clean in (
        ("AGY_WORKER_SWEEP unclean 4242\n", 3, True),
        ("AGY_WORKER_SWEEP clean\n", 0, False),
        ("", 1, True),  # sudo refused: never clean
    ):
        boundary = _prepare(worker_env, run_command=_Run(stdout, code))
        _launched(boundary, monkeypatch, owner_clean=owner_clean)
        (boundary.target / "src" / "a.py").write_text("worker edit\n", encoding="utf-8")
        assert boundary.sweep() is False
        boundary.cleanup()
        # an unclean sweep never copies anything back
        assert (worker_env["target"] / "src" / "a.py").read_text() == "print('a')\n"
        # ... and keeps the run root (#2888): the lease reaper sweeps that run later
        assert boundary.run_root.exists()
        assert boundary.leftover_run_root == str(boundary.run_root)
        shutil.rmtree(boundary.run_root)


def test_terminate_worker_sweeps_as_the_worker(worker_env, monkeypatch):
    run = _Run("AGY_WORKER_SWEEP clean\n")
    boundary = _prepare(worker_env, run_command=run)
    boundary.terminate_worker()
    assert run.calls == []  # nothing launched yet
    _launched(boundary, monkeypatch)
    boundary.terminate_worker()
    assert run.calls == [
        worker_mod.sweep_argv(boundary.run_root, [], wrapper=worker_env["wrapper"])
    ]
    boundary.cleanup()


def test_clean_run_copies_changes_back_and_removes_the_run_dir(worker_env, monkeypatch):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    work = boundary.target
    (work / "src" / "a.py").write_text("print('edited')\n", encoding="utf-8")
    (work / "src" / "new").mkdir()
    (work / "src" / "new" / "b.py").write_text("b\n", encoding="utf-8")
    (work / "README.md").unlink()
    assert boundary.sweep() is True
    boundary.cleanup()
    target = worker_env["target"]
    assert boundary.worker_failure is None
    assert (target / "src" / "a.py").read_text() == "print('edited')\n"
    assert (target / "src" / "new" / "b.py").read_text() == "b\n"
    assert not (target / "README.md").exists()
    # the target's own .git and customizations are never replaced from the copy
    assert (target / ".git" / "HEAD").read_text() == "ref: refs/heads/cwt-hidden\n"
    assert (target / ".agents" / "hooks.json").is_file()
    assert not boundary.run_root.exists()


@pytest.mark.parametrize("planted", ["symlink", "destination_symlink"])
def test_copy_back_refuses_symlinks_and_applies_nothing(worker_env, monkeypatch, planted):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    work, target = boundary.target, worker_env["target"]
    (work / "src" / "a.py").write_text("edited\n", encoding="utf-8")
    if planted == "symlink":
        (work / "src" / "link").symlink_to("/etc/passwd")
    else:
        (work / "src" / "c.py").write_text("c\n", encoding="utf-8")
        (target / "src" / "c.py").symlink_to(target / "README.md")
    boundary.cleanup()
    assert boundary.worker_failure is not None
    assert boundary.worker_failure.startswith("AGY_WORKER_COPY_BACK_REFUSED")
    assert (target / "src" / "a.py").read_text() == "print('a')\n"
    assert (target / "README.md").read_text() == "readme\n"
    assert not boundary.run_root.exists()


@pytest.mark.parametrize("owner_clean", [True, False])
def test_launch_without_the_wrapper_marker_is_a_launch_failure(
    worker_env, monkeypatch, owner_clean
):
    boundary = _prepare(worker_env, run_command=_Run("", 1))
    _launched(boundary, monkeypatch, owner_clean=owner_clean)
    (boundary.run_root / worker_mod.WRAPPER_STARTED_MARKER).unlink()
    # no worker process can exist, so only the Owner-side check decides
    assert boundary.sweep() is owner_clean
    boundary.cleanup()
    assert boundary.worker_failure == "AGY_WORKER_LAUNCH_FAILED:wrapper_did_not_start"
    # an unproven sweep keeps the run root for the lease reaper (#2888)
    assert boundary.run_root.exists() is (not owner_clean)
    if not owner_clean:
        shutil.rmtree(boundary.run_root)


# ---------------------------------------------------------------------------
# dispatcher integration
# ---------------------------------------------------------------------------


class _Claim:
    def __init__(self, home: Path) -> None:
        self.account_alias_hash = "worker"
        self.lease_id_hash = "lease-worker"
        self.internal_id = "worker-account"
        self.lease = type(
            "Lease", (), {"execution_env": {"HOME": str(home), "PATH": "/usr/bin:/bin"}}
        )()
        self.released = False
        self.marks: list[dict[str, Any]] = []

    def mark_worker_run(self, *, run_root: str, run_root_id: list[int], run_as_user: str) -> None:
        self.marks.append({
            "run_root": run_root,
            "run_root_id": run_root_id,
            "run_as_user": run_as_user,
        })

    def release(self) -> None:
        self.released = True


class _Coordinator:
    def __init__(self, home: Path) -> None:
        self.claim = _Claim(home)
        self.acquire_count = 0

    def acquire_claim(self, **_kwargs):
        self.acquire_count += 1
        return self.claim


def _metas(err: str) -> list[dict]:
    prefix = "NEXUS_AGY_DISPATCH "
    return [json.loads(line[len(prefix) :]) for line in err.splitlines() if line.startswith(prefix)]


def _patch_prepare(monkeypatch, layout, run):
    monkeypatch.setattr(
        worker_mod,
        "prepare_worker_account_boundary",
        functools.partial(
            worker_mod.prepare_worker_account_boundary,
            runs_dir=layout["runs"],
            wrapper=layout["wrapper"],
            worker_agy=layout["worker_agy"],
            run_group=layout["group"],
            repo_wrapper=WRAPPER,
            run_command=run,
        ),
    )
    real_which = shutil.which
    monkeypatch.setattr(
        dispatch.shutil,
        "which",
        lambda name, *a, **k: (
            str(layout["source_agy"]) if name == "agy" else real_which(name, *a, **k)
        ),
    )


def test_dispatch_run_as_user_runs_agy_in_the_worker_copy(worker_env, monkeypatch, capsys):
    _patch_prepare(monkeypatch, worker_env, _Run("AGY_WORKER_SWEEP clean\n"))
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    target = worker_env["target"]
    coordinator = _Coordinator(worker_env["home"])
    seen: dict = {}

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        seen["cwd"] = cwd
        seen["boundary"] = write_boundary
        seen["permissions"] = json.loads(
            (write_boundary.run_home / admission.AGY_RUN_HOME_SETTINGS).read_text()
        )["permissions"]
        write_boundary.before_launch()
        write_boundary._launched = True
        write_boundary._tracker = _Tracker(())
        (write_boundary.run_root / worker_mod.WRAPPER_STARTED_MARKER).write_text("")
        (Path(cwd) / "src" / "a.py").write_text("print('worker')\n", encoding="utf-8")
        return 0, "edited", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
        run_as_user="_cairnwork_worker",
    )
    meta = _metas(capsys.readouterr().err)[-1]
    assert code == 0, meta
    boundary = seen["boundary"]
    assert isinstance(boundary, worker_mod.AgyWorkerAccountBoundary)
    assert seen["cwd"] == str(boundary.target) != str(target)
    work = boundary.target
    assert f"write_file({work}/src/a.py)" in seen["permissions"]["allow"]
    assert f"read_file({work}/**)" in seen["permissions"]["allow"]
    assert not any(str(target) in rule for rule in seen["permissions"]["allow"])
    # the edit came back into the real target and the run dir is gone
    assert (target / "src" / "a.py").read_text() == "print('worker')\n"
    assert not boundary.run_root.exists()
    assert list(worker_env["runs"].iterdir()) == []
    assert coordinator.claim.released is True


def test_dispatch_worker_launch_failure_does_not_rotate(worker_env, monkeypatch, capsys):
    # sudo refuses both the launch and the sweep: "a password is required"
    _patch_prepare(monkeypatch, worker_env, _Run("", 1))
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    target = worker_env["target"]
    coordinator = _Coordinator(worker_env["home"])

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        write_boundary.before_launch()
        write_boundary._launched = True
        write_boundary._tracker = _Tracker(())
        return 1, "", "sudo: a password is required\n", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=coordinator,
        run_agy_fn=runner,
        run_as_user="_cairnwork_worker",
        max_calls=3,
    )
    meta = _metas(capsys.readouterr().err)[-1]
    assert code == 1
    assert meta["failure_kind"] == "AGY_WORKER_LAUNCH_FAILED:wrapper_did_not_start"
    assert meta["rotations"] == 0 and coordinator.acquire_count == 1
    assert meta["reconciliation_required"] is False


def test_run_as_user_requires_accept_edits(tmp_path, capsys):
    code = dispatch.dispatch_run(
        prompt="plan",
        cwd=str(tmp_path),
        mode="plan",
        coordinator=_Coordinator(tmp_path),
        run_agy_fn=lambda **_k: (0, "", "", False, 1),
        run_as_user="_cairnwork_worker",
    )
    assert code == 64
    assert _metas(capsys.readouterr().err)[-1]["failure_kind"] == (
        "DISPATCH_CONTRACT_REJECTED:RUN_AS_USER_REQUIRES_ACCEPT_EDITS"
    )


# ---------------------------------------------------------------------------
# without --run-as-user nothing changes
# ---------------------------------------------------------------------------


def test_default_dispatch_uses_the_unchanged_boundary(tmp_path, monkeypatch, capsys):
    if not admission.seatbelt_available():
        monkeypatch.setattr(boundary_mod, "seatbelt_available", lambda: True)
    worker_calls: list = []
    monkeypatch.setattr(
        worker_mod, "prepare_worker_account_boundary", lambda **k: worker_calls.append(k)
    )
    home = tmp_path.resolve() / "home"
    (home / TOKEN).parent.mkdir(parents=True)
    (home / TOKEN).write_text("token", encoding="utf-8")
    target = tmp_path.resolve() / "work"
    target.mkdir()
    seen: dict = {}

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        seen["cwd"] = cwd
        seen["boundary"] = write_boundary
        seen["argv"] = write_boundary.wrap_argv(["agy", "--x"])
        return 0, "ok", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "a.py")],
        coordinator=_Coordinator(home),
        run_agy_fn=runner,
    )
    assert code == 0
    assert worker_calls == []
    assert type(seen["boundary"]) is boundary_mod.AgyDispatchBoundary
    assert seen["cwd"] == str(target)
    assert seen["argv"] == [
        admission.SANDBOX_EXEC_PATH,
        "-f",
        str(seen["boundary"].profile_path),
        "agy",
        "--x",
    ]
    assert not hasattr(seen["boundary"], "launch_env")
    # #2888: the Owner-uid profile denies the worker-runs tree right after the head
    # (and never allows a path inside it); the worker profile has its own rules.
    head = "(version 1)\n(allow default)\n"
    deny = f'(deny file-read* file-write* (subpath "{boundary_mod.WORKER_RUNS_DIR}"))\n'
    profile = seen["boundary"].profile
    assert profile.startswith(head) and deny in profile
    assert profile[len(head) :].splitlines(keepends=True)[1] == deny
    assert profile.count(str(boundary_mod.WORKER_RUNS_DIR)) == 1
    assert dispatch._popen_env(seen["boundary"], {"A": "1"}) == {"A": "1"}
    assert dispatch._popen_env(None, {"A": "1"}) == {"A": "1"}
    # #2888: no worker receipt line without --run-as-user
    assert "WORKER_" not in capsys.readouterr().err


def test_background_argv_carries_run_as_user_only_when_set(tmp_path, monkeypatch):
    captured: list[list[str]] = []

    class _Proc:
        pid = 4321

    real_popen = subprocess.Popen

    def fake_popen(argv, **kwargs):
        if "--operation-run" not in argv:
            return real_popen(argv, **kwargs)
        captured.append(list(argv))
        return _Proc()

    monkeypatch.setattr(dispatch.subprocess, "Popen", fake_popen)
    common = dict(
        prompt="p",
        cwd=str(tmp_path),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=60,
        max_calls=1,
        pool_wait_timeout=None,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=tmp_path / "ops",
    )
    dispatch._spawn_background_operation(**common)
    dispatch._spawn_background_operation(**common, run_as_user="_cairnwork_worker")
    assert "--run-as-user" not in captured[0]
    assert captured[1][-2:] == ["--run-as-user", "_cairnwork_worker"]


def test_installer_copies_wrapper_and_agy_owner_0755(tmp_path):
    bin_dir = tmp_path.resolve() / "bin"
    bin_dir.mkdir()
    os.chmod(bin_dir, 0o755)
    agy = tmp_path.resolve() / "agy"
    agy.write_text("#!/bin/sh\necho agy\n", encoding="utf-8")
    os.chmod(agy, 0o755)
    env = {
        "PATH": "/usr/bin:/bin",
        "NEXUS_AGY_WORKER_BIN": str(bin_dir),
        "NEXUS_AGY_SOURCE_BINARY": str(agy),
    }
    done = subprocess.run(
        ["bash", str(INSTALLER)], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    for name, source in (("agy-worker-exec", WRAPPER), ("agy", agy)):
        installed = bin_dir / name
        assert installed.read_bytes() == source.read_bytes()
        assert stat.S_IMODE(installed.stat().st_mode) == 0o755
        assert installed.stat().st_uid == os.getuid()
    os.chmod(bin_dir, 0o775)
    done = subprocess.run(
        ["bash", str(INSTALLER)], env=env, capture_output=True, text=True, check=False
    )
    assert done.returncode != 0 and "bin_mode_775" in done.stderr


def test_wrapper_sweep_waits_out_zombies(tmp_path):
    """A killed child of ours lingers as a zombie until reaped; it never counts as live."""
    zombie = _spawn_sleeper()
    try:
        w = _wrapper_copy(tmp_path)
        (token,) = worker_mod.pid_start_tokens([zombie.pid], since=None)
        zombie.kill()
        time.sleep(0.2)  # killed, not yet reaped: a zombie
        done = _run_wrapper(w, "--sweep", str(w["run_root"]), token)
        assert done.stdout.strip() == "AGY_WORKER_SWEEP clean", done.stderr
    finally:
        zombie.wait()


# ---------------------------------------------------------------------------
# review r1 (#2885): a swapped workdir or source file never reaches the target
# ---------------------------------------------------------------------------


def _secret_dir(tmp_path: Path) -> Path:
    secret = tmp_path.resolve() / "owner-secret"
    secret.mkdir()
    (secret / "id_ed25519").write_text("PRIVATE KEY\n", encoding="utf-8")
    return secret


def _assert_target_untouched(target: Path) -> None:
    assert sorted(p.name for p in target.iterdir()) == [".agents", ".git", "README.md", "src"]
    assert (target / "src" / "a.py").read_text() == "print('a')\n"
    assert (target / "README.md").read_text() == "readme\n"
    assert not (target / "id_ed25519").exists()


@pytest.mark.parametrize("swap", ["symlink", "renamed_away", "new_directory"])
def test_swapped_workdir_is_refused_and_target_untouched(worker_env, monkeypatch, tmp_path, swap):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    work = boundary.target
    (work / "src" / "a.py").write_text("edited\n", encoding="utf-8")
    work.rename(work.with_name("w2"))
    if swap == "symlink":
        work.symlink_to(_secret_dir(tmp_path))
    elif swap == "new_directory":
        shutil.copytree(work.with_name("w2"), work, symlinks=True)
        (work / "id_ed25519").write_text("PRIVATE KEY\n", encoding="utf-8")
    assert boundary.sweep() is True
    boundary.cleanup()
    assert boundary.worker_failure == "AGY_WORKER_COPY_BACK_REFUSED:workdir_replaced"
    _assert_target_untouched(worker_env["target"])
    assert not os.path.lexists(boundary.run_root)


@pytest.mark.parametrize("swap", ["symlink", "rewritten", "hard_link"])
def test_source_swapped_between_plan_and_apply_is_refused(worker_env, monkeypatch, tmp_path, swap):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    work = boundary.target
    (work / "src" / "a.py").write_text("edited\n", encoding="utf-8")
    secret = _secret_dir(tmp_path) / "id_ed25519"
    real_plan = worker_mod._plan

    def plan_then_swap(*args, **kwargs):
        ops = real_plan(*args, **kwargs)
        victim = work / "src" / "a.py"
        victim.unlink()
        if swap == "symlink":
            victim.symlink_to(secret)
        elif swap == "rewritten":
            victim.write_text("something else\n", encoding="utf-8")
        else:
            os.link(secret, victim)
        return ops

    monkeypatch.setattr(worker_mod, "_plan", plan_then_swap)
    boundary.cleanup()
    assert boundary.worker_failure is not None
    assert boundary.worker_failure.startswith("AGY_WORKER_COPY_BACK_REFUSED:")
    assert "a.py" in boundary.worker_failure
    _assert_target_untouched(worker_env["target"])
    assert not any(
        p.name.startswith(".agy-worker-staging-") for p in worker_env["target"].iterdir()
    )


def test_hard_linked_worker_file_is_refused(worker_env, monkeypatch, tmp_path):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    os.link(_secret_dir(tmp_path) / "id_ed25519", boundary.target / "src" / "key.txt")
    boundary.cleanup()
    assert boundary.worker_failure == "AGY_WORKER_COPY_BACK_REFUSED:hard_link:src/key.txt"
    _assert_target_untouched(worker_env["target"])


def test_target_changed_meanwhile_is_not_overwritten(worker_env, monkeypatch):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    (boundary.target / "src" / "a.py").write_text("worker\n", encoding="utf-8")
    (boundary.target / "README.md").write_text("worker readme\n", encoding="utf-8")
    (worker_env["target"] / "src" / "a.py").write_text("someone else\n", encoding="utf-8")
    boundary.cleanup()
    assert boundary.worker_failure == "AGY_WORKER_COPY_BACK_REFUSED:target_changed:src/a.py"
    assert (worker_env["target"] / "src" / "a.py").read_text() == "someone else\n"
    assert (worker_env["target"] / "README.md").read_text() == "readme\n"  # all or nothing


def test_nested_git_is_neither_copied_in_nor_back(worker_env, monkeypatch):
    nested = worker_env["target"] / "vendor" / "lib" / ".git"
    nested.mkdir(parents=True)
    (nested / "config").write_text("[core]\n", encoding="utf-8")
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    work = boundary.target
    assert (work / "vendor" / "lib").is_dir() and not (work / "vendor" / "lib" / ".git").exists()
    (work / "vendor" / "lib" / ".git").mkdir()
    (work / "vendor" / "lib" / ".git" / "hooks").mkdir()
    (work / "vendor" / "lib" / ".git" / "hooks" / "post-checkout").write_text("#!/bin/sh\n")
    boundary.cleanup()
    assert boundary.worker_failure is None
    assert not (nested / "hooks").exists()
    assert (nested / "config").read_text() == "[core]\n"


def test_copy_back_size_cap(worker_env, monkeypatch):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    monkeypatch.setattr(worker_mod, "MAX_COPY_BACK_BYTES", 32)
    (boundary.target / "src" / "a.py").write_text("x" * 64, encoding="utf-8")
    boundary.cleanup()
    assert boundary.worker_failure == "AGY_WORKER_COPY_BACK_REFUSED:copy_back_too_large"
    _assert_target_untouched(worker_env["target"])


def test_profile_pins_the_run_entries_against_rename(worker_env):
    boundary = _prepare(worker_env)
    try:
        profile, run_root = boundary.profile, boundary.run_root
        for entry in (
            boundary.target,
            boundary.run_home,
            boundary.run_tmp,
            boundary.profile_path,
            run_root,
        ):
            assert _effective(profile, "file-write*", entry) == "deny", entry
        # files inside them stay writable for agy
        assert _effective(profile, "file-write*", boundary.target / "src" / "new.py") == "allow"
        assert _effective(profile, "file-write*", boundary.run_tmp / "x") == "allow"
        # a new entry next to them in the run root is harmless and still allowed
        assert _effective(profile, "file-write*", run_root / "scratch") == "allow"
    finally:
        boundary.cleanup()


def test_leftover_run_dir_is_reported(worker_env, monkeypatch, capsys):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    monkeypatch.setattr(worker_mod.shutil, "rmtree", lambda *a, **k: None)
    boundary.cleanup()
    assert boundary.leftover_run_root == str(boundary.run_root)
    assert f"worker run dir left behind: {boundary.run_root}" in capsys.readouterr().err
    monkeypatch.undo()
    shutil.rmtree(boundary.run_root)


# ---------------------------------------------------------------------------
# review r2 (#2885)
# ---------------------------------------------------------------------------


def _seatbelt_usable() -> bool:
    if not admission.seatbelt_available():
        return False
    probe = subprocess.run(
        [admission.SANDBOX_EXEC_PATH, "-p", "(version 1) (allow default)", "/usr/bin/true"],
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def test_absolute_cd_and_mkdir_p_work_under_the_full_profile(worker_env):
    """stat of worker-runs itself is allowed; its listing and other runs stay denied."""
    boundary = _prepare(worker_env)
    runs = worker_env["runs"]
    other = runs / ("0" * 32)
    other.mkdir()
    (other / "secret").write_text("S", encoding="utf-8")
    try:
        profile, work = boundary.profile, boundary.target
        assert f'(allow file-read-metadata (literal "{runs}"))' in profile.splitlines()
        assert _effective(profile, "file-read-metadata", runs) == "allow"
        assert _effective(profile, "file-read-data", runs) == "deny"
        assert _effective(profile, "file-read-metadata", other) == "deny"
        assert _effective(profile, "file-read-data", other / "secret") == "deny"
        if not _seatbelt_usable():
            return  # off macOS the rules above are the witness
        script = (
            f"cd '{work}' && echo CD_OK; "
            f"mkdir -p '{work}/deep/er/dir' && echo MKDIR_OK; "
            f"ls '{runs}' >/dev/null 2>&1 && echo LIST_LEAK || echo LIST_DENIED; "
            f"cat '{other}/secret' 2>/dev/null && echo OTHER_LEAK || echo OTHER_DENIED"
        )
        done = subprocess.run(
            [
                admission.SANDBOX_EXEC_PATH,
                "-f",
                str(boundary.profile_path),
                "/bin/sh",
                "-c",
                script,
            ],
            cwd="/",
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        assert done.stdout.split() == ["CD_OK", "MKDIR_OK", "LIST_DENIED", "OTHER_DENIED"], (
            done.stderr
        )
        assert (work / "deep" / "er" / "dir").is_dir()
    finally:
        boundary.cleanup()


def test_existing_staging_name_is_never_removed(worker_env, monkeypatch):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    (boundary.target / "src" / "a.py").write_text("edited\n", encoding="utf-8")
    clash = worker_env["target"] / (worker_mod._STAGING_PREFIX + "ab" * 8)
    clash.mkdir()
    (clash / "keep.txt").write_text("keep", encoding="utf-8")
    monkeypatch.setattr(worker_mod.secrets, "token_hex", lambda n=16: "ab" * n)
    boundary.cleanup()
    assert (
        boundary.worker_failure
        == "AGY_WORKER_COPY_BACK_REFUSED:staging_unavailable:FileExistsError"
    )
    assert (clash / "keep.txt").read_text() == "keep"
    assert (worker_env["target"] / "src" / "a.py").read_text() == "print('a')\n"


def test_caps_are_checked_before_agy_runs(worker_env, monkeypatch):
    monkeypatch.setattr(worker_mod, "MAX_COPY_BACK_BYTES", 4)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_too_large"):
        _prepare(worker_env)
    monkeypatch.setattr(worker_mod, "MAX_COPY_BACK_BYTES", 2 << 30)
    monkeypatch.setattr(worker_mod, "MAX_COPY_BACK_ENTRIES", 2)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_too_large"):
        _prepare(worker_env)
    assert list(worker_env["runs"].iterdir()) == []


@pytest.mark.parametrize(
    "changed, expected",
    [
        ("README.md", "AGY_WORKER_COPY_BACK_REFUSED:target_changed:README.md"),
        ("src/a.py", "AGY_WORKER_COPY_BACK_FAILED:target_changed:src/a.py"),
    ],
)
def test_target_rechecked_before_each_replace(worker_env, monkeypatch, changed, expected):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    (boundary.target / "README.md").write_text("worker readme\n", encoding="utf-8")
    (boundary.target / "src" / "a.py").write_text("worker\n", encoding="utf-8")
    real_plan = worker_mod._plan

    def plan_then_other_writer(*args, **kwargs):
        ops = real_plan(*args, **kwargs)
        (worker_env["target"] / changed).write_text("other writer\n", encoding="utf-8")
        return ops

    monkeypatch.setattr(worker_mod, "_plan", plan_then_other_writer)
    boundary.cleanup()
    assert boundary.worker_failure == expected
    assert (worker_env["target"] / changed).read_text() == "other writer\n"  # never overwritten


def test_dispatch_copy_back_refusal_needs_no_reconciliation(worker_env, monkeypatch, capsys):
    _patch_prepare(monkeypatch, worker_env, _Run("AGY_WORKER_SWEEP clean\n"))
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    target = worker_env["target"]

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        write_boundary.before_launch()
        write_boundary._launched = True
        write_boundary._tracker = _Tracker(())
        (write_boundary.run_root / worker_mod.WRAPPER_STARTED_MARKER).write_text("")
        (Path(cwd) / "src" / "link").symlink_to("/etc/passwd")
        return 0, "done", "", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=_Coordinator(worker_env["home"]),
        run_agy_fn=runner,
        run_as_user="_cairnwork_worker",
    )
    meta = _metas(capsys.readouterr().err)[-1]
    assert code == 1
    assert meta["failure_kind"] == "AGY_WORKER_COPY_BACK_REFUSED:symlink_created:src/link"
    assert meta["reconciliation_required"] is False and meta["provider_effect"] is False
    assert meta["rotations"] == 0


# ---------------------------------------------------------------------------
# #2888: fail-closed copy-in and durable worker reconciliation
# ---------------------------------------------------------------------------


@pytest.fixture
def worker_preflight(worker_env, monkeypatch):
    # Layout validation has its own tests above. These unit tests isolate it
    # because some test hosts strip setgid even after a successful chmod.
    monkeypatch.setattr(worker_mod, "_check_runs_dir", lambda path, gid: path)


@pytest.mark.usefixtures("worker_preflight")
def test_prepare_refuses_a_missing_wrapper_reference(worker_env, tmp_path):
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="wrapper_reference_missing"):
        _prepare(worker_env, repo_wrapper=tmp_path / "missing-wrapper")
    assert list(worker_env["runs"].iterdir()) == []


@pytest.mark.parametrize("cap", ["MAX_COPY_BACK_ENTRIES", "MAX_COPY_BACK_BYTES"])
@pytest.mark.usefixtures("worker_preflight")
def test_oversized_copy_in_is_refused_before_creating_files(worker_env, monkeypatch, cap):
    monkeypatch.setattr(worker_mod, cap, 2)
    real_write = os.write
    writes = []

    def observe_write(fd, data):
        writes.append(len(data))
        return real_write(fd, data)

    monkeypatch.setattr(worker_mod.os, "write", observe_write)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_too_large"):
        _prepare(worker_env)
    assert writes == []
    assert list(worker_env["runs"].iterdir()) == []


@pytest.mark.parametrize(
    "cap, grown_size, expected_writes",
    [(32, 30, [7]), ((1 << 20) + 10, (1 << 20) + 16, [7, 1 << 20])],
)
@pytest.mark.usefixtures("worker_preflight")
def test_copy_in_counts_actual_bytes_when_a_source_file_grows(
    worker_env, monkeypatch, cap, grown_size, expected_writes
):
    monkeypatch.setattr(worker_mod, "MAX_COPY_BACK_BYTES", cap)
    real_check = worker_mod._check_copy_caps

    def grow_after_preflight(manifest, source):
        real_check(manifest, source)
        (source / "src" / "a.py").write_bytes(b"x" * grown_size)

    monkeypatch.setattr(worker_mod, "_check_copy_caps", grow_after_preflight)
    real_write = os.write
    written = []

    def observe_write(fd, data):
        written.append(len(data))
        assert sum(written) <= worker_mod.MAX_COPY_BACK_BYTES
        return real_write(fd, data)

    monkeypatch.setattr(worker_mod.os, "write", observe_write)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_too_large"):
        _prepare(worker_env)
    assert written == expected_writes  # neither an individual file nor their sum crosses the cap
    assert list(worker_env["runs"].iterdir()) == []


def _worker_reconcile_operation(tmp_path, monkeypatch, **fields):
    journal = dispatch.AgyOperationJournal(tmp_path / "operations")
    operation_id = dispatch.new_operation_id()
    journal.create(
        operation_id=operation_id,
        attempt_id=dispatch.new_attempt_id(),
        cwd=str(tmp_path),
        provider="agy",
        model="gemini-test",
        effort="medium",
        prompt_sha256="0" * 64,
        runtime_revision="a" * 40,
    )
    journal.mark_started(operation_id, pid=999_999_999)
    journal.heartbeat(
        operation_id,
        attempts=1,
        descendant_sweep_clean=None,
        descendant_sweep_attempt=1,
        **fields,
    )
    monkeypatch.setattr(dispatch._agy_operation_journal, "_process_alive", lambda pid: False)
    monkeypatch.setattr(dispatch, "LEASES_DIR", tmp_path / "leases")
    return journal, operation_id


def test_reconcile_worker_sweeps_exact_wrapper_argv_before_owner_check(
    worker_env, tmp_path, monkeypatch
):
    run_root = worker_env["runs"] / ("a" * 32)
    run_root.mkdir()
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", worker_env["runs"])
    journal, operation_id = _worker_reconcile_operation(
        tmp_path,
        monkeypatch,
        worker_run_as_user=worker_mod.WORKER_USER,
        worker_run_root=str(run_root),
        worker_run_root_id=[run_root.lstat().st_dev, run_root.lstat().st_ino],
    )
    worker_mod.write_operation_marker(run_root, operation_id)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        assert argv == worker_mod.sweep_argv(run_root, [])
        assert kwargs == {
            "cwd": "/",
            "env": worker_mod.LAUNCH_ENV,
            "stdin": subprocess.DEVNULL,
            "capture_output": True,
            "text": True,
            "timeout": worker_mod.SWEEP_TIMEOUT_SECONDS,
            "check": False,
        }
        return subprocess.CompletedProcess(argv, 0, "diagnostic\nAGY_WORKER_SWEEP clean\n", "")

    monkeypatch.setattr(worker_mod.subprocess, "run", run)
    real_reconcile = journal.reconcile

    def owner_reconcile(operation_id):
        assert calls == [worker_mod.sweep_argv(run_root, [])]
        return real_reconcile(operation_id)

    monkeypatch.setattr(journal, "reconcile", owner_reconcile)
    record = dispatch._reconcile_operation(journal, operation_id)
    assert record["reconciliation"]["worker_sweep"] == {
        "result": "CLEAN",
        "run_root": str(run_root),
    }
    assert journal.read(operation_id)["reconciliation"] == record["reconciliation"]


@pytest.mark.parametrize(
    "case, expected",
    [
        ("gone", "RUN_ROOT_GONE_UNPROVEN"),
        ("wrong_user", "RECORD_INVALID"),
        ("outside", "RECORD_INVALID"),
        ("parent", "RECORD_INVALID"),
        ("nested", "RECORD_INVALID"),
        ("dotdot", "RECORD_INVALID"),
        ("symlink", "RECORD_INVALID"),
        ("missing_root", "RECORD_INVALID"),
    ],
)
def test_reconcile_worker_validates_record_without_sudo(
    worker_env, tmp_path, monkeypatch, case, expected
):
    runs = worker_env["runs"]
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", runs)
    run_root = runs / ("b" * 32)
    user = "root" if case == "wrong_user" else worker_mod.WORKER_USER
    raw_root = str(run_root)
    if case == "outside":
        raw_root = str(tmp_path.resolve() / ("b" * 32))
    elif case == "parent":
        raw_root = str(runs)
    elif case == "nested":
        raw_root = str(run_root / "work")
    elif case == "dotdot":
        raw_root = f"{runs}/../worker-runs/{run_root.name}"
    elif case == "symlink":
        run_root.symlink_to(worker_env["target"], target_is_directory=True)
    elif case == "missing_root":
        raw_root = None
    journal, operation_id = _worker_reconcile_operation(
        tmp_path, monkeypatch, worker_run_as_user=user, worker_run_root=raw_root
    )

    def no_sudo(*args, **kwargs):
        pytest.fail("invalid or missing worker run must not invoke sudo")

    monkeypatch.setattr(worker_mod.subprocess, "run", no_sudo)
    record = dispatch._reconcile_operation(journal, operation_id)
    assert record["reconciliation"]["worker_sweep"] == {
        "result": expected,
        "run_root": raw_root,
    }


@pytest.mark.parametrize(
    "stdout, returncode, error, expected",
    [
        ("AGY_WORKER_SWEEP unclean 42\n", 0, None, "UNCLEAN"),
        ("AGY_WORKER_SWEEP clean\n", 1, None, "UNCLEAN"),
        ("AGY_WORKER_SWEEP clean\nlater diagnostic\n", 0, None, "UNCLEAN"),
        ("", 0, OSError("sudo unavailable"), "SWEEP_ERROR"),
        ("", 0, subprocess.TimeoutExpired("stub-sudo", 30), "SWEEP_ERROR"),
    ],
)
@pytest.mark.parametrize("provider_alive_after", [True, False, None])
def test_reconcile_worker_sweep_failure_holds_and_blocks_retry(
    worker_env, tmp_path, monkeypatch, stdout, returncode, error, expected, provider_alive_after
):
    run_root = worker_env["runs"] / ("c" * 32)
    run_root.mkdir()
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", worker_env["runs"])
    journal, operation_id = _worker_reconcile_operation(
        tmp_path,
        monkeypatch,
        worker_run_as_user=worker_mod.WORKER_USER,
        worker_run_root=str(run_root),
        worker_run_root_id=[run_root.lstat().st_dev, run_root.lstat().st_ino],
    )
    worker_mod.write_operation_marker(run_root, operation_id)
    # Exercise the completed-provider projection too: it must preserve the
    # existing provider truth when the worker sweep cannot confirm cleanup.
    journal.update(
        operation_id,
        status="COMPLETED",
        phase="TERMINAL",
        exit_code=0,
        provider_process_state="EXITED",
        has_unresolved_external_effect=False,
        reconciliation={"provider_alive_after": provider_alive_after, "retry_permitted": True},
    )

    def run(argv, **kwargs):
        assert argv == worker_mod.sweep_argv(run_root, [])
        if error is not None:
            raise error
        return subprocess.CompletedProcess(argv, returncode, stdout, "")

    monkeypatch.setattr(worker_mod.subprocess, "run", run)
    record = dispatch._reconcile_operation(journal, operation_id)
    reconciliation = record["reconciliation"]
    assert reconciliation["worker_sweep"] == {"result": expected, "run_root": str(run_root)}
    assert reconciliation["result"] == "WORKER_SWEEP_UNPROVEN_HELD"
    assert reconciliation["provider_alive_after"] is None  # never releasable
    assert reconciliation["retry_permitted"] is False
    assert record["phase"] == "RECONCILE_REQUIRED"


def test_reconcile_non_worker_never_calls_worker_sweep(tmp_path, monkeypatch):
    journal, operation_id = _worker_reconcile_operation(tmp_path, monkeypatch)

    def no_sweep(record):
        pytest.fail("non-worker operation must not sweep the worker uid")

    monkeypatch.setattr(dispatch, "_run_worker_sweep", no_sweep)
    record = dispatch._reconcile_operation(journal, operation_id)
    assert "worker_sweep" not in record["reconciliation"]


@pytest.mark.parametrize("run_as_user", [None, worker_mod.WORKER_USER])
@pytest.mark.usefixtures("worker_preflight")
def test_background_pending_marker_records_worker_fields_only_for_worker_runs(
    worker_env, tmp_path, monkeypatch, run_as_user
):
    _patch_prepare(monkeypatch, worker_env, _Run("AGY_WORKER_SWEEP clean\n"))
    for module in (worker_mod, boundary_mod):
        monkeypatch.setattr(module, "_prepare_run_home_keychain", lambda home: "NOT_APPLICABLE")
    journal, operation_id = _worker_reconcile_operation(tmp_path, monkeypatch)
    # Start with a fresh marker, as a newly queued background operation would.
    journal.update(operation_id, descendant_sweep_clean=True)
    prompt_path = journal.prompt_path(operation_id)
    dispatch._write_private_prompt(prompt_path, "edit")
    seen = []

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        record = journal.read(operation_id)  # the marker is durable before launch
        assert record["descendant_sweep_clean"] is None
        if run_as_user is not None:
            assert record["worker_run_as_user"] == worker_mod.WORKER_USER
            assert record["worker_run_root"] == str(write_boundary.run_root)
            assert write_boundary.receipt_context == {"operation_id": operation_id, "attempt": 1}
        else:
            assert "worker_run_as_user" not in record
            assert "worker_run_root" not in record
        seen.append(record)
        return 0, "done", "", False, 1

    monkeypatch.setattr(
        dispatch,
        "dispatch_run",
        functools.partial(
            dispatch.dispatch_run,
            coordinator=_Coordinator(worker_env["home"]),
            run_agy_fn=runner,
        ),
    )
    monkeypatch.setattr(dispatch, "_runtime_revision", lambda: "a" * 40)
    code = dispatch._run_background_operation(
        operation_id=operation_id,
        prompt_file=str(prompt_path),
        cwd=str(worker_env["target"]),
        mode="accept-edits",
        model=None,
        effort=None,
        timeout=30,
        max_calls=1,
        pool_wait_timeout=None,
        allow=[],
        deny=[],
        temp_command_permissions=False,
        operation_root=journal.root,
        write_paths=[str(worker_env["target"] / "src" / "a.py")],
        run_as_user=run_as_user,
    )
    assert code == 0
    assert len(seen) == 1


def test_reconcile_vanished_run_root_is_proven_only_by_a_recorded_clean_sweep(
    worker_env, tmp_path, monkeypatch
):
    runs = worker_env["runs"]
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", runs)
    run_root = runs / ("d" * 32)
    journal, operation_id = _worker_reconcile_operation(
        tmp_path,
        monkeypatch,
        worker_run_as_user=worker_mod.WORKER_USER,
        worker_run_root=str(run_root),
    )
    real_run = subprocess.run

    def no_sudo(argv, *a, **k):
        assert "sudo" not in str(argv[0]), "no sudo for a vanished run root"
        return real_run(argv, *a, **k)

    monkeypatch.setattr(worker_mod.subprocess, "run", no_sudo)
    held = dispatch._reconcile_operation(journal, operation_id)
    assert held["reconciliation"]["worker_sweep"]["result"] == "RUN_ROOT_GONE_UNPROVEN"
    assert held["reconciliation"]["retry_permitted"] is False
    assert held["reconciliation"]["provider_alive_after"] is None
    journal.heartbeat(operation_id, descendant_sweep_clean=True, descendant_sweep_attempt=1)
    proven = dispatch._reconcile_operation(journal, operation_id)
    assert proven["reconciliation"]["worker_sweep"]["result"] == "RUN_ROOT_GONE"


def test_reconcile_refuses_another_operations_valid_run_root(worker_env, tmp_path, monkeypatch):
    runs = worker_env["runs"]
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", runs)
    run_root = runs / ("e" * 32)
    run_root.mkdir()
    journal, operation_id = _worker_reconcile_operation(
        tmp_path,
        monkeypatch,
        worker_run_as_user=worker_mod.WORKER_USER,
        worker_run_root=str(run_root),
        worker_run_root_id=[run_root.lstat().st_dev, run_root.lstat().st_ino],
    )
    worker_mod.write_operation_marker(run_root, "someone-elses-operation")
    monkeypatch.setattr(worker_mod.subprocess, "run", lambda *a, **k: pytest.fail("no sudo"))
    record = dispatch._reconcile_operation(journal, operation_id)
    assert record["reconciliation"]["worker_sweep"]["result"] == "RECORD_INVALID"
    assert record["reconciliation"]["provider_alive_after"] is None
    # No marker at all is refused too.
    (run_root / worker_mod.OPERATION_MARKER).unlink()
    record = dispatch._reconcile_operation(journal, operation_id)
    assert record["reconciliation"]["worker_sweep"]["result"] == "RECORD_INVALID"


@pytest.mark.usefixtures("worker_preflight")
def test_copy_in_refuses_a_file_swapped_for_a_symlink_after_the_walk(worker_env, monkeypatch):
    secret = worker_env["home"] / "secret.txt"
    secret.write_text("top secret")
    real_check = worker_mod._check_copy_caps

    def swap_after_manifest(manifest, source):
        real_check(manifest, source)
        victim = source / "src" / "a.py"
        victim.unlink()
        victim.symlink_to(secret)

    monkeypatch.setattr(worker_mod, "_check_copy_caps", swap_after_manifest)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_changed_during_copy"):
        _prepare(worker_env)
    assert list(worker_env["runs"].iterdir()) == []


@pytest.mark.usefixtures("worker_preflight")
def test_copy_in_refuses_an_ancestor_swapped_for_a_symlink_after_the_walk(worker_env, monkeypatch):
    real_dir = worker_env["home"] / "elsewhere"
    real_dir.mkdir()
    (real_dir / "a.py").write_text(worker_env["target"].joinpath("src", "a.py").read_text())
    real_check = worker_mod._check_copy_caps

    def swap_dir(manifest, source):
        real_check(manifest, source)
        shutil.rmtree(source / "src")
        (source / "src").symlink_to(real_dir, target_is_directory=True)

    monkeypatch.setattr(worker_mod, "_check_copy_caps", swap_dir)
    with pytest.raises(boundary_mod.AgyWriteBoundaryError, match="target_changed_during_copy"):
        _prepare(worker_env)
    assert list(worker_env["runs"].iterdir()) == []


def test_reconcile_refuses_a_transplanted_marker_and_a_replaced_root(
    worker_env, tmp_path, monkeypatch
):
    runs = worker_env["runs"]
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", runs)
    root_a, root_b = runs / ("a" * 32), runs / ("b" * 32)
    root_a.mkdir()
    root_b.mkdir()
    journal, operation_id = _worker_reconcile_operation(
        tmp_path,
        monkeypatch,
        worker_run_as_user=worker_mod.WORKER_USER,
        worker_run_root=str(root_a),
        worker_run_root_id=[root_a.lstat().st_dev, root_a.lstat().st_ino],
    )
    worker_mod.write_operation_marker(root_a, operation_id)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, "AGY_WORKER_SWEEP clean\n", "")

    monkeypatch.setattr(worker_mod.subprocess, "run", run)
    # The record now points at B, the marker is renamed in from A.
    (root_a / worker_mod.OPERATION_MARKER).rename(root_b / worker_mod.OPERATION_MARKER)
    journal.update(operation_id, worker_run_root=str(root_b))
    record = dispatch._reconcile_operation(journal, operation_id)
    assert record["reconciliation"]["worker_sweep"]["result"] == "RECORD_INVALID"
    # A new directory under the original name with another inode.  ext4
    # hands a freshly freed inode number straight back, so park any reuse
    # under a decoy name and allocate again (APFS never reuses here).
    journal.update(operation_id, worker_run_root=str(root_a))
    recorded_ino = root_a.lstat().st_ino
    shutil.rmtree(root_a)
    for attempt in range(64):
        root_a.mkdir()
        if root_a.lstat().st_ino != recorded_ino:
            break
        root_a.rename(runs / f"decoy-{attempt}")
    else:
        pytest.fail("could not allocate a directory with a fresh inode")
    worker_mod.write_operation_marker(root_a, operation_id)
    record = dispatch._reconcile_operation(journal, operation_id)
    assert record["reconciliation"]["worker_sweep"]["result"] == "RECORD_INVALID"
    assert calls == []


@pytest.mark.parametrize(
    "stdout, error, receipt_survives, sweep_result",
    [
        ("AGY_WORKER_SWEEP unclean 42\n", None, True, "UNCLEAN"),
        ("", OSError("sudo unavailable"), True, "SWEEP_ERROR"),
        ("AGY_WORKER_SWEEP clean\n", None, False, "CLEAN"),
    ],
)
def test_reconcile_keeps_the_lease_receipt_unless_the_worker_sweep_is_clean(
    worker_env, tmp_path, monkeypatch, stdout, error, receipt_survives, sweep_result
):
    run_root = worker_env["runs"] / ("f" * 32)
    run_root.mkdir()
    monkeypatch.setattr(worker_mod, "WORKER_RUNS", worker_env["runs"])
    journal, operation_id = _worker_reconcile_operation(
        tmp_path,
        monkeypatch,
        worker_run_as_user=worker_mod.WORKER_USER,
        worker_run_root=str(run_root),
        worker_run_root_id=[run_root.lstat().st_dev, run_root.lstat().st_ino],
    )
    worker_mod.write_operation_marker(run_root, operation_id)
    alias_hash, lease_hash, owner_pid = "a" * 12, "b" * 12, 999_999_999
    journal.update(
        operation_id,
        account_alias_hash=alias_hash,
        lease_id_hash=lease_hash,
        status="COMPLETED",
        phase="TERMINAL",
        exit_code=0,
        provider_process_state="EXITED",
        has_unresolved_external_effect=False,
    )
    leases = tmp_path / "leases"
    leases.mkdir()
    receipt = leases / f"{alias_hash}.receipt.json"
    receipt.write_text(
        json.dumps({
            "account_alias_hash": alias_hash,
            "lease_id_hash": lease_hash,
            "consumer_id": "agy-operation",
            "claimed_at": 1.0,
            "pid": owner_pid,
        })
    )

    def run(argv, **kwargs):
        if error is not None:
            raise error
        return subprocess.CompletedProcess(argv, 0, stdout, "")

    monkeypatch.setattr(worker_mod.subprocess, "run", run)
    record = dispatch._reconcile_operation(journal, operation_id)
    assert record["reconciliation"]["worker_sweep"]["result"] == sweep_result
    assert receipt.exists() is receipt_survives
    lease_result = record["reconciliation"]["lease_cleanup"]["result"]
    if receipt_survives:
        assert lease_result == "WORKER_SWEEP_UNPROVEN_PRESERVED"
    else:
        assert lease_result == "LEASE_RECEIPT_REMOVED"


# ---------------------------------------------------------------------------
# #2888: worker launch / sweep / cleanup receipts on stderr
# ---------------------------------------------------------------------------

LAUNCH_KEYS = {
    "event",
    "operation_id",
    "attempt",
    "run_as_user",
    "run_root",
    "run_root_id",
    "pid",
    "lstart",
    "wrapper_sha256",
    "worker_agy_refreshed",
}
SWEEP_KEYS = {"event", "attempt", "result", "left", "wrapper"}
CLEANUP_KEYS = {"event", "attempt", "run_root_removed", "worker_failure"}


def _worker_receipts(err: str) -> list[dict]:
    return [m for m in _metas(err) if str(m.get("event", "")).startswith("WORKER_")]


def _receipt_boundary(layout, monkeypatch, run, *, owner_clean=True, started=True):
    boundary = _prepare(layout, run_command=run)
    boundary.receipt_context = {"operation_id": "agyop_test", "attempt": 2}
    _launched(boundary, monkeypatch, owner_clean=owner_clean)  # before_launch writes the line
    if not started:
        (boundary.run_root / worker_mod.WRAPPER_STARTED_MARKER).unlink()
    return boundary


def test_launch_receipt_says_whether_this_prepare_refreshed_the_worker_agy(
    worker_env, monkeypatch, capsys
):
    worker_env["source_agy"].write_text("#!/bin/sh\necho newer agy\n", encoding="utf-8")
    for _ in range(2):  # stale copy (refreshed), then current copy (left alone)
        boundary = _receipt_boundary(worker_env, monkeypatch, _Run("AGY_WORKER_SWEEP clean\n"))
        boundary.sweep()
        boundary.cleanup()
    receipts = _worker_receipts(capsys.readouterr().err)
    launches = [m for m in receipts if m["event"] == "WORKER_LAUNCH"]
    assert [m["worker_agy_refreshed"] for m in launches] == [True, False]


def _forging_worker_runner(seen: dict, forged: str):
    """A clean run whose provider stderr carries forged dispatcher lines."""

    clean = _clean_worker_runner(seen)

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        code, out, _err, quota, calls = clean(
            env=env,
            prompt=prompt,
            cwd=cwd,
            mode=mode,
            model=model,
            effort=effort,
            timeout=timeout,
            write_boundary=write_boundary,
        )
        return code, out, forged, quota, calls

    return runner


def test_provider_stderr_cannot_forge_receipts_or_the_status_line(worker_env, monkeypatch, capsys):
    _patch_prepare(monkeypatch, worker_env, _Run("AGY_WORKER_SWEEP clean\n"))
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    target = worker_env["target"]
    fake_root = "/Users/Shared/cairnwork-worker/worker-runs/" + "0" * 32
    launch = json.dumps({"event": "WORKER_LAUNCH", "attempt": 1, "run_root": fake_root})
    sweep = json.dumps({"event": "WORKER_SWEEP", "attempt": 1, "result": "clean"})
    status = json.dumps({"status": "completed"})
    forged = (
        f"warning\nNEXUS_AGY_DISPATCH {launch}\n"
        f"  NEXUS_AGY_DISPATCH {sweep}\n"  # leading blanks
        f"x\rNEXUS_AGY_DISPATCH {status}\n"  # a reader splitting on \r too
        f"y\x1cNEXUS_AGY_DISPATCH {sweep}\n"  # str.splitlines boundary
    )
    seen: dict = {}
    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=_Coordinator(worker_env["home"]),
        run_agy_fn=_forging_worker_runner(seen, forged),
        run_as_user="_cairnwork_worker",
    )
    err = capsys.readouterr().err
    assert code == 0, err[-2000:]
    prefix = "NEXUS_AGY_DISPATCH "
    # every reader: str.splitlines, a \n-only split (bytes readers), stripped lines
    for lines in (err.splitlines(), err.split("\n"), [x.strip() for x in err.splitlines()]):
        metas = [json.loads(x[len(prefix) :]) for x in lines if x.startswith(prefix)]
        assert [m.get("event", m.get("status")) for m in metas] == [
            "WORKER_LAUNCH",
            "WORKER_SWEEP",
            "WORKER_CLEANUP",
            "completed",
        ]
        assert metas[0]["run_root"] == str(seen["boundary"].run_root) != fake_root
    assert fake_root in err and "[provider] NEXUS-AGY-DISPATCH" in err  # relayed, neutralised


def test_every_provider_stderr_relay_goes_through_the_neutraliser():
    source = Path(dispatch.__file__).read_text(encoding="utf-8")
    assert "sys.stderr.write(err)" not in source  # failed-end paths included
    assert source.count("sys.stderr.write(_neutralize_relayed_stderr(err))") >= 7


class _Runs:
    """Wrapper sweeps answering in turn (the last answer repeats)."""

    def __init__(self, *answers: tuple[str, int]):
        self.answers = list(answers)

    def __call__(self, argv, **kwargs):
        stdout, code = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        return subprocess.CompletedProcess(argv, code, stdout, "")


def test_only_an_unclean_line_counts_as_the_wrappers_report(worker_env, monkeypatch, capsys):
    boundary = _receipt_boundary(worker_env, monkeypatch, _Run("AGY_WORKER_SWEEP error 5\n", 3))
    assert boundary.sweep() is False
    boundary.cleanup()
    sweep = _worker_receipts(capsys.readouterr().err)[1]
    assert sweep["wrapper"] == "REFUSED" and sweep["left"] == []


def test_left_is_reset_by_a_later_clean_sweep(worker_env, monkeypatch, capsys):
    run = _Runs(("AGY_WORKER_SWEEP unclean 42\n", 3), ("AGY_WORKER_SWEEP clean\n", 0))
    boundary = _receipt_boundary(worker_env, monkeypatch, run)
    boundary.terminate_worker()  # the timeout kill reports a survivor
    assert boundary.sweep() is True  # the final sweep is clean
    boundary.cleanup()
    sweep = _worker_receipts(capsys.readouterr().err)[1]
    assert (sweep["result"], sweep["wrapper"], sweep["left"]) == ("clean", "CLEAN", [])


def test_relayed_stderr_without_dispatcher_lines_is_unchanged():
    text = "plain\nNEXUS_AGY_DESCENDANT_SWEEP_FAILED\nNEXUS_AGY_DISPATC\n"
    assert dispatch._neutralize_relayed_stderr("plain\n") == "plain\n"
    assert dispatch._neutralize_relayed_stderr(text) == text


def test_relayed_token_is_broken_anywhere_so_no_cut_forges_a_line():
    # #2888: a reader cutting an over-long line at a fixed size could start a line
    # mid-line; the token must not survive anywhere in the relayed text.
    status = json.dumps({"status": "completed"})
    pad = "A" * 65530
    text = f"{pad}NEXUS_AGY_DISPATCH {status}\nx NEXUS_AGY_DISPATCHNEXUS_AGY_DISPATCH y\n"
    out = dispatch._neutralize_relayed_stderr(text)
    assert "NEXUS_AGY_DISPATCH" not in out
    assert out.count("NEXUS-AGY-DISPATCH") == 3
    for size in (1, 7, 4096, 65530, 65536):
        chunks = [out[i : i + size] for i in range(0, len(out), size)]
        assert not any(c.lstrip().startswith("NEXUS_AGY_DISPATCH") for c in chunks)


def _clean_worker_runner(seen: dict):
    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        seen["boundary"] = write_boundary
        seen["lstat"] = os.lstat(write_boundary.run_root)
        write_boundary.before_launch()
        write_boundary._launched = True
        write_boundary._tracker = _Tracker(())
        (write_boundary.run_root / worker_mod.WRAPPER_STARTED_MARKER).write_text("")
        return 0, "edited", "", False, 1

    return runner


def test_dispatch_writes_one_launch_sweep_cleanup_receipt_in_order(worker_env, monkeypatch, capsys):
    _patch_prepare(monkeypatch, worker_env, _Run("AGY_WORKER_SWEEP clean\n"))
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    target = worker_env["target"]
    seen: dict = {}
    hook_events: list[dict] = []
    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=_Coordinator(worker_env["home"]),
        run_agy_fn=_clean_worker_runner(seen),
        run_as_user="_cairnwork_worker",
        operation_hook=hook_events.append,
    )
    err = capsys.readouterr().err
    assert code == 0
    metas = _metas(err)
    assert [m.get("event", m.get("status")) for m in metas] == [
        "WORKER_LAUNCH",
        "WORKER_SWEEP",
        "WORKER_CLEANUP",
        metas[-1]["status"],
    ]
    launch, sweep, cleanup, final = metas
    assert set(launch) == LAUNCH_KEYS and set(sweep) == SWEEP_KEYS
    assert set(cleanup) == CLEANUP_KEYS
    # the final status line keeps its shape and stays the last NEXUS_AGY_DISPATCH line
    assert "event" not in final and final["status"] == "completed"
    boundary = seen["boundary"]
    assert launch["operation_id"] is None  # foreground: no journal operation
    assert launch["attempt"] == sweep["attempt"] == cleanup["attempt"] == 1
    assert launch["run_as_user"] == worker_mod.WORKER_USER
    assert launch["run_root"] == str(boundary.run_root)
    assert launch["run_root_id"] == [seen["lstat"].st_dev, seen["lstat"].st_ino]
    assert launch["pid"] is None and launch["lstart"] is None
    assert launch["wrapper_sha256"] == hashlib.sha256(WRAPPER.read_bytes()).hexdigest()
    assert sweep["result"] == "clean" and sweep["left"] == []
    assert cleanup["run_root_removed"] is True and cleanup["worker_failure"] is None
    # consistent with the journal's sweep verdict
    verdicts = [e["descendant_sweep_clean"] for e in hook_events if "descendant_sweep_clean" in e]
    assert verdicts[-1] is True
    # owner-side only: no pool HOME, env or token in any receipt line
    receipt_text = "".join(line for line in err.splitlines(keepends=True) if '"WORKER_' in line)
    assert str(worker_env["home"]) not in receipt_text and "GH_TOKEN" not in receipt_text
    assert str(boundary.run_home) not in receipt_text


def test_dispatch_unclean_sweep_receipt_matches_the_journal_verdict(
    worker_env, monkeypatch, capsys
):
    _patch_prepare(monkeypatch, worker_env, _Run("AGY_WORKER_SWEEP unclean 4242\n", 3))
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    target = worker_env["target"]
    hook_events: list[dict] = []
    dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=_Coordinator(worker_env["home"]),
        run_agy_fn=_clean_worker_runner({}),
        run_as_user="_cairnwork_worker",
        operation_hook=hook_events.append,
    )
    err = capsys.readouterr().err
    sweeps = [m for m in _worker_receipts(err) if m["event"] == "WORKER_SWEEP"]
    assert [m["result"] for m in sweeps] == ["unclean"]
    verdicts = [e["descendant_sweep_clean"] for e in hook_events if "descendant_sweep_clean" in e]
    assert verdicts[-1] is False
    assert _metas(err)[-1].get("event") is None  # the status line is still last


def test_dispatch_launch_failure_receipts_say_not_started(worker_env, monkeypatch, capsys):
    # sudo refuses both the launch and the sweep: the wrapper never wrote its marker
    _patch_prepare(monkeypatch, worker_env, _Run("", 1))
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    target = worker_env["target"]

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        write_boundary.before_launch()
        write_boundary._launched = True
        write_boundary._tracker = _Tracker(())
        return 1, "", "sudo: a password is required\n", False, 1

    code = dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=_Coordinator(worker_env["home"]),
        run_agy_fn=runner,
        run_as_user="_cairnwork_worker",
        max_calls=3,
    )
    metas = _metas(capsys.readouterr().err)
    assert code == 1
    assert [m.get("event") for m in metas[:-1]] == [
        "WORKER_LAUNCH",
        "WORKER_SWEEP",
        "WORKER_CLEANUP",
    ]
    assert metas[-2]["worker_failure"] == "AGY_WORKER_LAUNCH_FAILED:wrapper_did_not_start"
    assert metas[-3]["result"] == "not_started" and metas[-3]["left"] == []
    assert "event" not in metas[-1] and metas[-1]["failure_kind"].startswith("AGY_WORKER_LAUNCH")


def test_dispatch_copy_back_refusal_receipt_names_no_worker_chosen_path(
    worker_env, monkeypatch, capsys
):
    _patch_prepare(monkeypatch, worker_env, _Run("AGY_WORKER_SWEEP clean\n"))
    monkeypatch.setattr(cli_worker, "sweep_run", lambda *a, **k: True)
    target = worker_env["target"]

    def runner(*, env, prompt, cwd, mode, model, effort, timeout, write_boundary):
        write_boundary.before_launch()
        write_boundary._launched = True
        write_boundary._tracker = _Tracker(())
        (write_boundary.run_root / worker_mod.WRAPPER_STARTED_MARKER).write_text("")
        (Path(cwd) / "src" / "worker-chosen-name").symlink_to("/etc/passwd")
        return 0, "done", "", False, 1

    dispatch.dispatch_run(
        prompt="edit",
        cwd=str(target),
        mode="accept-edits",
        write_paths=[str(target / "src" / "a.py")],
        coordinator=_Coordinator(worker_env["home"]),
        run_agy_fn=runner,
        run_as_user="_cairnwork_worker",
    )
    err = capsys.readouterr().err
    cleanup = [m for m in _worker_receipts(err) if m["event"] == "WORKER_CLEANUP"]
    assert [m["worker_failure"] for m in cleanup] == [
        "AGY_WORKER_COPY_BACK_REFUSED:symlink_created"
    ]
    assert "worker-chosen-name" not in "".join(
        line for line in err.splitlines() if '"WORKER_' in line
    )


@pytest.mark.parametrize(
    ("run", "owner_clean", "expected"),
    [
        (_Run("AGY_WORKER_SWEEP clean\n"), True, "clean"),
        (_Run("AGY_WORKER_SWEEP unclean 4242\n", 3), True, "unclean"),
        (_Run("AGY_WORKER_SWEEP clean\n"), False, "unclean"),  # owner-side check unclean
        (_Run("", 1), True, "unclean"),  # sudo refused after the wrapper started
    ],
)
def test_sweep_receipt_is_clean_only_when_the_sweep_verdict_is_clean(
    worker_env, monkeypatch, capsys, run, owner_clean, expected
):
    boundary = _receipt_boundary(worker_env, monkeypatch, run, owner_clean=owner_clean)
    assert boundary.sweep() is (expected == "clean")
    boundary.cleanup()
    receipts = _worker_receipts(capsys.readouterr().err)
    assert [m["event"] for m in receipts] == ["WORKER_LAUNCH", "WORKER_SWEEP", "WORKER_CLEANUP"]
    assert receipts[0]["operation_id"] == "agyop_test"
    assert {m["attempt"] for m in receipts} == {2}
    assert receipts[1]["result"] == expected
    # left: only the pids the wrapper itself reported as surviving
    assert receipts[1]["left"] == (["4242"] if "unclean 4242" in run.stdout else [])
    assert boundary.receipts == receipts  # what the dispatcher can read back


def test_sweep_receipt_error_when_the_wrapper_sweep_cannot_run(worker_env, monkeypatch, capsys):
    def run(argv, **kwargs):
        raise OSError("sudo missing")

    boundary = _receipt_boundary(worker_env, monkeypatch, run)
    assert boundary.sweep() is False
    boundary.cleanup()
    assert [m["result"] for m in _worker_receipts(capsys.readouterr().err)[1:2]] == ["error"]


def test_sweep_that_raises_is_reported_as_error_never_clean(worker_env, monkeypatch, capsys):
    boundary = _receipt_boundary(worker_env, monkeypatch, _Run("AGY_WORKER_SWEEP clean\n"))

    def boom(*args, **kwargs):
        raise RuntimeError("sweep blew up")

    monkeypatch.setattr(cli_worker, "sweep_run", boom)
    with pytest.raises(RuntimeError):
        boundary.sweep()
    shutil.rmtree(boundary.run_root)
    receipts = _worker_receipts(capsys.readouterr().err)
    assert [(m["event"], m.get("result")) for m in receipts] == [
        ("WORKER_LAUNCH", None),
        ("WORKER_SWEEP", "error"),
    ]


@pytest.mark.parametrize("owner_clean", [True, False])
def test_wrapper_that_never_started_is_not_started_unless_the_owner_sweep_is_unclean(
    worker_env, monkeypatch, capsys, owner_clean
):
    boundary = _receipt_boundary(
        worker_env, monkeypatch, _Run("", 1), owner_clean=owner_clean, started=False
    )
    assert boundary.sweep() is owner_clean
    boundary.cleanup()
    receipts = _worker_receipts(capsys.readouterr().err)
    assert receipts[1]["result"] == ("not_started" if owner_clean else "unclean")
    assert receipts[1]["wrapper"] == "REFUSED"  # sudo refused: no wrapper report line
    assert receipts[2]["worker_failure"] == "AGY_WORKER_LAUNCH_FAILED:wrapper_did_not_start"
    assert receipts[2]["run_root_removed"] is owner_clean  # unclean: kept (#2888)
    if not owner_clean:
        shutil.rmtree(boundary.run_root)


def test_launch_that_never_happened_still_closes_with_not_started_and_cleanup(
    worker_env, monkeypatch, capsys
):
    boundary = _prepare(worker_env, run_command=_Run("", 1))
    boundary.receipt_context = {"operation_id": None, "attempt": 1}
    boundary.before_launch()  # Popen then raised: after_launch never ran
    boundary.cleanup()
    receipts = _worker_receipts(capsys.readouterr().err)
    assert [(m["event"], m.get("result")) for m in receipts] == [
        ("WORKER_LAUNCH", None),
        ("WORKER_SWEEP", "not_started"),
        ("WORKER_CLEANUP", None),
    ]
    assert receipts[2]["worker_failure"] is None and receipts[2]["run_root_removed"] is True


@pytest.mark.parametrize("how", ["keep_env", "rmtree_stub"])
def test_cleanup_receipt_says_the_run_root_was_not_removed(worker_env, monkeypatch, capsys, how):
    boundary = _receipt_boundary(worker_env, monkeypatch, _Run("AGY_WORKER_SWEEP clean\n"))
    if how == "keep_env":
        monkeypatch.setenv(boundary_mod.KEEP_RUN_ROOT_ENV, "1")
    else:
        monkeypatch.setattr(worker_mod.shutil, "rmtree", lambda *a, **k: None)
    boundary.cleanup()
    monkeypatch.undo()
    try:
        cleanup = _worker_receipts(capsys.readouterr().err)[-1]
        assert cleanup["event"] == "WORKER_CLEANUP" and cleanup["run_root_removed"] is False
    finally:
        shutil.rmtree(boundary.run_root, ignore_errors=True)


def test_each_receipt_is_written_once_per_attempt(worker_env, monkeypatch, capsys):
    boundary = _receipt_boundary(worker_env, monkeypatch, _Run("AGY_WORKER_SWEEP clean\n"))
    boundary.before_launch()
    assert boundary.sweep() is True and boundary.sweep() is True
    boundary.cleanup()
    boundary.cleanup()
    events = [m["event"] for m in _worker_receipts(capsys.readouterr().err)]
    assert events == ["WORKER_LAUNCH", "WORKER_SWEEP", "WORKER_CLEANUP"]


def test_a_boundary_without_a_receipt_context_writes_nothing(worker_env, monkeypatch, capsys):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    _launched(boundary, monkeypatch)
    assert boundary.sweep() is True
    boundary.cleanup()
    assert "NEXUS_AGY_DISPATCH" not in capsys.readouterr().err
    assert boundary.receipts == []


class _BrokenStderr:
    def write(self, text):
        raise ValueError("I/O operation on closed file")

    def flush(self):
        raise ValueError("I/O operation on closed file")


def test_a_failing_stderr_never_breaks_launch_sweep_or_cleanup(worker_env, monkeypatch):
    run = _Run("AGY_WORKER_SWEEP clean\n")
    boundary = _prepare(worker_env, run_command=run)
    boundary.receipt_context = {"operation_id": None, "attempt": 1}
    monkeypatch.setattr(sys, "stderr", _BrokenStderr())
    _launched(boundary, monkeypatch)
    (boundary.target / "src" / "a.py").write_text("worker edit\n", encoding="utf-8")
    assert boundary.sweep() is True
    boundary.cleanup()
    monkeypatch.undo()
    assert boundary.worker_failure is None and not boundary.run_root.exists()
    # the work still came back; nothing was written, so nothing is recorded
    assert (worker_env["target"] / "src" / "a.py").read_text() == "worker edit\n"
    assert boundary.receipts == []


class _FirstWriteFails:
    """stderr whose first write fails (the launch line), then works."""

    def __init__(self, real):
        self.real, self.failed = real, False

    def write(self, text):
        if not self.failed:
            self.failed = True
            raise ValueError("I/O operation on closed file")
        return self.real.write(text)

    def flush(self):
        self.real.flush()


def test_an_unwritten_launch_line_keeps_sweep_and_cleanup_lines_out(
    worker_env, monkeypatch, capsys
):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    boundary.receipt_context = {"operation_id": None, "attempt": 1}
    monkeypatch.setattr(sys, "stderr", _FirstWriteFails(sys.stderr))
    _launched(boundary, monkeypatch)
    assert boundary.sweep() is True
    boundary.cleanup()
    # no orphan WORKER_SWEEP / WORKER_CLEANUP without the launch line that names run_root
    assert _worker_receipts(capsys.readouterr().err) == []
    assert boundary.receipts == []


def test_a_deleted_start_marker_never_hides_the_wrappers_unclean_report(
    worker_env, monkeypatch, capsys
):
    # The worker account can write the run root and delete the marker; the
    # wrapper's own report of surviving processes must still make it unclean.
    boundary = _receipt_boundary(
        worker_env, monkeypatch, _Run("AGY_WORKER_SWEEP unclean 4242 77\n", 3), started=False
    )
    assert boundary.sweep() is False
    boundary.cleanup()
    receipts = _worker_receipts(capsys.readouterr().err)
    assert receipts[1]["result"] == "unclean" and receipts[1]["left"] == ["4242", "77"]
    assert receipts[1]["wrapper"] == "UNCLEAN"


@pytest.mark.parametrize(
    "failure", [OSError("sudo missing"), subprocess.TimeoutExpired("stub-sudo", 30)]
)
def test_a_deleted_start_marker_never_excuses_a_sweep_that_errored(
    worker_env, monkeypatch, capsys, failure
):
    def run(argv, **kwargs):
        raise failure

    boundary = _receipt_boundary(worker_env, monkeypatch, run, started=False)
    assert boundary.sweep() is False
    boundary.cleanup()
    receipts = _worker_receipts(capsys.readouterr().err)
    assert receipts[1]["result"] == "error" and receipts[1]["wrapper"] == "SWEEP_ERROR"


def test_left_lists_only_ascii_pids(worker_env, monkeypatch, capsys):
    run = _Run("AGY_WORKER_SWEEP unclean 12 \u00b2 x9 99999999999 7\n", 3)
    boundary = _receipt_boundary(worker_env, monkeypatch, run)
    assert boundary.sweep() is False
    boundary.cleanup()
    assert _worker_receipts(capsys.readouterr().err)[1]["left"] == ["12", "7"]


def test_sweep_report_returns_the_wrappers_last_line(tmp_path):
    run = _Run("noise\nAGY_WORKER_SWEEP unclean 9\n", 3)
    assert worker_mod.sweep_run_root_report(tmp_path, run_command=run) == (
        "UNCLEAN",
        "AGY_WORKER_SWEEP unclean 9",
    )
    assert worker_mod.sweep_run_root(tmp_path, run_command=run) == "UNCLEAN"
    refused = _Run("", 1)
    assert worker_mod.sweep_run_root_report(tmp_path, run_command=refused) == ("UNCLEAN", "")


def test_an_unserialisable_receipt_value_is_swallowed(worker_env, monkeypatch, capsys):
    boundary = _prepare(worker_env, run_command=_Run("AGY_WORKER_SWEEP clean\n"))
    boundary.receipt_context = {"operation_id": None, "attempt": 1}
    boundary.wrapper_sha256 = object()  # json.dumps raises TypeError
    _launched(boundary, monkeypatch)
    assert boundary.sweep() is True
    boundary.cleanup()
    events = [m["event"] for m in _worker_receipts(capsys.readouterr().err)]
    assert "WORKER_LAUNCH" not in events  # the caller rejects a run without a launch line
    assert not boundary.run_root.exists()
