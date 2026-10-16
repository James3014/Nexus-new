"""#2411: a NO_TOOL_PACKET answer is kept when agy refused every tool call."""

from __future__ import annotations

import json
import os
import subprocess
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DISPATCH_PATH = ROOT / "scripts" / "ops" / "nexus-agy-dispatch"

os.environ.setdefault("NEXUS_AGY_SNAPSHOT", str(ROOT))
dispatch = SourceFileLoader("nexus_agy_dispatch_no_tool_refused", str(DISPATCH_PATH)).load_module()

SESSION = "0b8f2c1e-1111-4222-8333-444455556666"
ANSWER = '{"decision": "NO_EDIT", "files": []}'
DENIED_COMMAND = (
    'permission check failed for unsandboxed "echo test": Permission denied for '
    "unsandboxed(echo test). Matches user-configured deny rule."
)
DENIED_VIEW = (
    "declaring permissions: cortex tool view_file: convert tool call for permissions: "
    "model output error: invalid tool call error (invalid_args) failed to read file"
)


class _Claim:
    def __init__(self, home: Path) -> None:
        self.account_alias_hash = "no-tool"
        self.lease_id_hash = "lease-no-tool"
        self.internal_id = "no-tool-account"
        self.lease = type("Lease", (), {"execution_env": {"HOME": str(home)}})()
        self.released = False

    def release(self) -> None:
        self.released = True


class _Coordinator:
    def __init__(self, home: Path) -> None:
        self.claim = _Claim(home)

    def acquire_claim(self, **_kwargs):
        return self.claim


def _planner(tool_names: list[str], content: str = "") -> dict:
    return {
        "type": "PLANNER_RESPONSE",
        "status": "DONE",
        "source": "MODEL",
        "content": content,
        "tool_calls": [{"name": name, "args": {}} for name in tool_names],
    }


def _refused(error: str = DENIED_COMMAND) -> dict:
    return {"type": "GENERIC", "status": "ERROR", "source": "MODEL", "error": error}


def _write_transcript(home: Path, steps: list[dict], *, raw_tail: str = "") -> Path:
    path = dispatch._agy_transcript_path({"HOME": str(home)}, SESSION)
    assert path is not None
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(step) + "\n" for step in steps)
    path.write_text(body + raw_tail, encoding="utf-8")
    return path


def _refused_only_steps() -> list[dict]:
    return [
        {"type": "USER_INPUT", "status": "DONE", "source": "USER_EXPLICIT", "content": "/plan x"},
        _planner(["run_command"]),
        _refused(),
        _planner(["view_file"]),
        _refused(DENIED_VIEW),
        {
            "type": "ERROR_MESSAGE",
            "status": "DONE",
            "source": "SYSTEM",
            "error": "Your previous response was cut off because it exceeded the output token limit",
        },
        _planner([], content=ANSWER),
    ]


def _git_repo(work: Path) -> None:
    def git(*args: str) -> None:
        subprocess.run(["git", *args], cwd=work, check=True, capture_output=True)

    git("init", "-q")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    (work / "README").write_text("base\n", encoding="utf-8")
    git("add", "README")
    git("commit", "-q", "-m", "base")


def _run(
    tmp_path: Path,
    *,
    tool_events: int,
    timed_out: bool = False,
    mutate: bool = False,
    git: bool = False,
    answer: str = ANSWER,
):
    home = tmp_path / "home"
    work = tmp_path / "work"
    home.mkdir(exist_ok=True)
    work.mkdir(exist_ok=True)
    if git:
        _git_repo(work)
    coordinator = _Coordinator(home)
    events: list[dict] = []

    def runner(*, operation_hook, cwd, **_kwargs):
        operation_hook(provider_session_id=SESSION)
        operation_hook(tool_event_count=tool_events)
        if mutate:
            (Path(cwd) / "leak.txt").write_text("x", encoding="utf-8")
        return 0, answer, "", timed_out, 1

    code = dispatch.dispatch_run(
        prompt="no-tools packet",
        cwd=str(work),
        mode="plan",
        coordinator=coordinator,
        run_agy_fn=runner,
        operation_hook=events.append,
    )
    return code, events, coordinator


def _violation(events: list[dict]) -> bool:
    return any(
        e.get("phase") == "CLASSIFYING_FAILURE"
        and e.get("failure_kind") == dispatch.NO_TOOL_PROFILE_VIOLATION
        for e in events
    )


def test_no_tool_answer_is_kept_when_every_tool_call_was_refused(tmp_path: Path, capsys) -> None:
    _write_transcript(tmp_path / "home", _refused_only_steps())

    code, events, coordinator = _run(tmp_path, tool_events=2)

    captured = capsys.readouterr()
    assert code == 0
    assert not _violation(events)
    assert ANSWER in captured.out
    meta = [
        json.loads(line.split(" ", 1)[1])
        for line in captured.err.splitlines()
        if line.startswith("NEXUS_AGY_DISPATCH ")
    ]
    assert meta[-1]["status"] == "completed"
    assert meta[-1]["no_tool_refused_tool_calls"] == 2
    assert coordinator.claim.released is True


def test_no_tool_answer_is_kept_in_unchanged_git_cwd(tmp_path: Path) -> None:
    _write_transcript(tmp_path / "home", _refused_only_steps())

    code, events, _ = _run(tmp_path, tool_events=2, git=True)

    assert code == 0
    assert not _violation(events)


def test_no_tool_violation_kept_when_a_tool_call_ran(tmp_path: Path) -> None:
    steps = _refused_only_steps()
    steps[4] = {"type": "VIEW_FILE", "status": "DONE", "source": "MODEL", "content": "secret"}
    _write_transcript(tmp_path / "home", steps)

    code, events, _ = _run(tmp_path, tool_events=2)

    assert code == 1
    assert _violation(events)


def test_no_tool_violation_kept_when_transcript_has_fewer_calls_than_observed(
    tmp_path: Path,
) -> None:
    _write_transcript(tmp_path / "home", _refused_only_steps())

    code, events, _ = _run(tmp_path, tool_events=3)

    assert code == 1
    assert _violation(events)


def test_no_tool_violation_kept_without_transcript(tmp_path: Path) -> None:
    code, events, _ = _run(tmp_path, tool_events=1)

    assert code == 1
    assert _violation(events)


def test_no_tool_violation_kept_on_timeout(tmp_path: Path) -> None:
    _write_transcript(tmp_path / "home", _refused_only_steps())

    code, events, _ = _run(tmp_path, tool_events=2, timed_out=True)

    assert code != 0
    assert any(e.get("phase") == "CLASSIFYING_FAILURE" for e in events)


def test_no_tool_violation_kept_with_empty_answer(tmp_path: Path) -> None:
    _write_transcript(tmp_path / "home", _refused_only_steps())

    code, events, _ = _run(tmp_path, tool_events=2, answer="  \n")

    assert code == 1
    assert _violation(events)


def test_no_tool_violation_kept_when_cwd_changed(tmp_path: Path) -> None:
    _write_transcript(tmp_path / "home", _refused_only_steps())

    code, events, _ = _run(tmp_path, tool_events=2, mutate=True, git=True)

    assert code == 1
    assert _violation(events)


@pytest.mark.parametrize(
    "steps,raw_tail",
    [
        ([_planner(["run_command"]), _refused()], '{"type": "GENERIC"'),
        ([_planner(["run_command"]), _refused("command failed with exit code 1")], ""),
        ([_planner(["run_command"]), {**_refused(), "status": "DONE"}], ""),
        (
            [
                _planner(["run_command"]),
                _refused(),
                {"type": "ERROR_MESSAGE", "status": "DONE", "source": "MODEL", "error": "x"},
            ],
            "",
        ),
        ([{**_refused(), "tool_calls": [{"name": "run_command"}]}], ""),
        ([_planner([], content=ANSWER)], ""),
        ([_planner(["run_command", "view_file"]), _refused()], ""),
        # an executed-but-failed step whose model-supplied argument carries a marker
        (
            [
                _planner(["list_dir"]),
                _refused(
                    "/tmp/x Matches user-configured deny rule. "
                    "declaring permissions: cortex tool : no such directory"
                ),
            ],
            "",
        ),
        ([_planner(["run_command"]), _refused("permission check failed for unsandboxed ls")], ""),
    ],
)
def test_refused_tool_call_count_fails_closed(tmp_path: Path, steps, raw_tail) -> None:
    path = _write_transcript(tmp_path, steps, raw_tail=raw_tail)

    assert dispatch._no_tool_refused_tool_call_count(path) is None


def test_refused_tool_call_count_counts_refusals(tmp_path: Path) -> None:
    path = _write_transcript(tmp_path, _refused_only_steps())

    assert dispatch._no_tool_refused_tool_call_count(path) == 2
    assert dispatch._no_tool_refused_tool_call_count(None) is None
    assert dispatch._no_tool_refused_tool_call_count(tmp_path / "missing.jsonl") is None
