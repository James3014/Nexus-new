from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from nexus_open_swe_runtime import cli


def _request(tmp_path: Path) -> dict:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.py").write_text("VALUE = 1\n", encoding="utf-8")
    artifact = tmp_path / "evidence.json"
    artifact.write_text('{"failure":"VALUE must be 2"}\n', encoding="utf-8")
    return {
        "schema": cli.REQUEST_SCHEMA,
        "operation": "worker_run",
        "operation_id": "e" * 64,
        "provider_id": "google_genai",
        "model_id": "gemini-test",
        "runtime_state_root": str(tmp_path / "state"),
        "workspace_path": str(workspace),
        "artifact_path": str(artifact),
        "prompt": "\n".join(
            [
                "task_id=task-process-death",
                "unit_id=u1",
                'authorized_mutation_paths=["a.py"]',
                "bounded repair",
            ]
        ),
        "session_id": "",
        "worker_identity_sha256": "f" * 64,
    }


def test_process_death_after_external_effect_reconciles_without_second_dispatch(tmp_path):
    request = _request(tmp_path)
    request_path = tmp_path / "request.json"
    counter_path = tmp_path / "external-effect-counter"
    result_path = tmp_path / "restart-result.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")

    killed_child = subprocess.run(
        [
            sys.executable,
            "-c",
            _KILL_AFTER_EFFECT,
            str(request_path),
            str(counter_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert killed_child.returncode < 0
    assert counter_path.read_text(encoding="utf-8") == "effect\n"
    operation_path = (
        Path(request["runtime_state_root"])
        / "operations"
        / f"{request['operation_id']}.json"
    )
    assert json.loads(operation_path.read_text(encoding="utf-8"))["status"] == "STARTED"

    restarted_child = subprocess.run(
        [
            sys.executable,
            "-c",
            _RESTART_AND_RECONCILE,
            str(request_path),
            str(counter_path),
            str(result_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert restarted_child.returncode == 0, restarted_child.stderr
    result = json.loads(result_path.read_text(encoding="utf-8"))
    assert result["status"] == "OPEN_SWE_OUTCOME_UNKNOWN"
    assert result["outcome_unknown"] is True
    assert result["retry_safe"] is False
    assert "response_text" not in result
    assert counter_path.read_text(encoding="utf-8") == "effect\n"
    assert [path.name for path in operation_path.parent.iterdir()] == [
        f"{request['operation_id']}.json"
    ]
    assert json.loads(operation_path.read_text(encoding="utf-8"))["status"] == "STARTED"


_KILL_AFTER_EFFECT = r'''
import json
import os
import signal
import sys
from pathlib import Path
from types import SimpleNamespace

from nexus_open_swe_runtime import cli


class Graph:
    def __init__(self, surface, output=None, effect=None):
        self.surface = tuple(surface)
        self.output = output
        self.effect = effect

    def get_graph(self):
        tools = {name: object() for name in self.surface}
        return SimpleNamespace(
            nodes={"tools": SimpleNamespace(data=SimpleNamespace(tools_by_name=tools))}
        )

    def invoke(self, _payload, config=None):
        if self.effect is not None:
            self.effect()
        return self.output


def recorded(name, envelope):
    return {
        "messages": [
            SimpleNamespace(tool_calls=[{"name": name, "args": {"envelope": envelope}}])
        ]
    }


request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
counter = Path(sys.argv[2])
diagnosis = Graph(
    cli.DIAGNOSIS_TOOLS,
    recorded(
        "record_diagnosis",
        {
            "status": "ROOT_CAUSE_SUPPORTED",
            "summary": "supported",
            "evidence_paths": ["a.py"],
        },
    ),
)


def effect_then_die():
    with counter.open("a", encoding="utf-8") as stream:
        stream.write("effect\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.kill(os.getpid(), signal.SIGKILL)


repair = Graph(cli.REPAIR_TOOLS, effect=effect_then_die)
cli._worker_run(
    request,
    runtime_loader=lambda: {"human_message": lambda content: content},
    model_factory=lambda *_args: object(),
    diagnosis_factory=lambda *_args: diagnosis,
    repair_factory=lambda *_args: repair,
)
'''


_RESTART_AND_RECONCILE = r'''
import json
import sys
from pathlib import Path

from nexus_open_swe_runtime import cli


request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
counter = Path(sys.argv[2])
before = counter.read_text(encoding="utf-8")
result = cli._worker_run(
    request,
    runtime_loader=lambda: (_ for _ in ()).throw(AssertionError("runtime redispatched")),
)
assert counter.read_text(encoding="utf-8") == before
Path(sys.argv[3]).write_text(json.dumps(result), encoding="utf-8")
'''
