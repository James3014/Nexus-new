"""Real-process state bridge parity and lock-deadlock regression coverage."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

SCENARIO = r"""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService
with TemporaryDirectory() as directory:
    root = Path(directory).resolve() / "state"
    service = SelfHostedTaskService(root, ephemeral=True, auto_reconcile=False)
    results = []
    results.append(service._write_state("t", {"task_id": "t", "status": "FINAL_BLOCK", "value": ("relative",)}))
    results.append(service._mutate_state("t", lambda state: state.update(value=("changed",))))
    restarted = SelfHostedTaskService(root, ephemeral=True, auto_reconcile=False)
    results.append(restarted._read_state("t"))
    archive = root.parent / "nexus-state-archive"
    archive.mkdir()
    (root / "t.json").replace(archive / "t--attempt-a.json")
    results.append(restarted._read_state_snapshot("t"))
    results.append(restarted._mutate_state("t", lambda state: state.update(status="FINAL_BLOCK")))
    results.append(restarted._create_state("t", {"task_id": "t", "status": "FINAL_BLOCK"}))
    for payload in ["{", "[]", '{"task_id":"wrong","status":"FINAL_BLOCK"}']:
        (root / "t.json").write_text(payload)
        results.append(restarted._read_state("t"))
    print("PARITY=" + json.dumps(results, sort_keys=True, default=str).replace(str(root.parent), "<ROOT>"))
"""


def _run(repo: Path, *, frozen_source: Path | None = None) -> list[dict]:
    source_setup = ""
    if frozen_source is not None:
        source_setup = f"""
import types
from pathlib import Path
module_name = 'nexus.orchestrator.self_hosted_task_service'
module = types.ModuleType(module_name)
module.__file__ = {str(frozen_source)!r}
module.__package__ = 'nexus.orchestrator'
import sys
sys.modules[module_name] = module
exec(compile(Path({str(frozen_source)!r}).read_text(), {str(frozen_source)!r}, 'exec'), module.__dict__)
"""
    script = source_setup + SCENARIO
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=repo,
        env={**os.environ, "PYTHONPATH": str(repo)},
        capture_output=True,
        text=True,
        timeout=45,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(
        next(line[7:] for line in result.stdout.splitlines() if line.startswith("PARITY="))
    )


def test_real_service_state_roundtrip_restart_archive_and_error_receipts():
    repo = Path(__file__).resolve().parents[3]
    result = _run(repo)
    assert result[1]["value"] == ["changed"]
    assert result[2]["status"] == "FINAL_BLOCK"
    assert result[2]["value"] == ["changed"]
    assert result[3] == result[2]
    assert result[4] is None
    assert result[5][1] is False
    assert [item["blocker"]["code"] for item in result[-3:]] == [
        "STATE_JSON_INVALID",
        "STATE_NOT_OBJECT",
        "STATE_FIELD_INVALID",
    ]


def test_real_service_state_matches_frozen_source(tmp_path):
    repo = Path(__file__).resolve().parents[3]
    frozen = tmp_path / "self_hosted_task_service.py"
    frozen.write_bytes(
        subprocess.check_output(
            ["git", "show", "4ecec9409:nexus/orchestrator/self_hosted_task_service.py"], cwd=repo
        )
    )
    assert _run(repo) == _run(repo, frozen_source=frozen)
