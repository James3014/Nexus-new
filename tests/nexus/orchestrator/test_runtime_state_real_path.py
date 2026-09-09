"""Real entrypoint regression: every operation has a subprocess deadlock deadline."""

import json
import os
import subprocess
import sys
from pathlib import Path

SCENARIO = "import json\nfrom pathlib import Path\nfrom tempfile import TemporaryDirectory\nfrom nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService\nwith TemporaryDirectory() as directory:\n    root = Path(directory).resolve()/'state'\n    service = SelfHostedTaskService(root, ephemeral=True, auto_reconcile=False)\n    results = []\n    results.append(service._write_state('t', {'task_id':'t','status':'FAILED_EXECUTION','value':('relative',)}))\n    results.append(service._mutate_state('t', lambda state: state.update(value=('changed',))))\n    restarted = SelfHostedTaskService(root, ephemeral=True, auto_reconcile=False)\n    results.append(restarted._read_state('t'))\n    archive = root.parent/'nexus-state-archive'\n    archive.mkdir()\n    (root/'t.json').replace(archive/'t--attempt-a.json')\n    results.append(restarted._read_state_snapshot('t'))\n    results.append(restarted._mutate_state('t', lambda state: state.update(status='FAILED_EXECUTION')))\n    results.append(restarted._create_state('t', {'task_id':'t','status':'FAILED_EXECUTION'}))\n    for payload in ['{','[]','{\"task_id\":\"wrong\",\"status\":\"FAILED\"}']:\n        (root/'t.json').write_text(payload)\n        results.append(restarted._read_state('t'))\n    print('PARITY='+json.dumps(results, sort_keys=True, default=str).replace(str(root.parent), '<ROOT>'))\n"


def _run(repo):
    result = subprocess.run(
        [sys.executable, "-c", SCENARIO],
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


def test_real_service_state_roundtrip_deadlock_and_error_receipts():
    result = _run(Path(__file__).resolve().parents[3])
    assert result[1]["value"] == ["changed"]
    assert result[4] is None
    assert result[5][1] is False
    assert [item["blocker"]["code"] for item in result[-3:]] == [
        "STATE_JSON_INVALID",
        "STATE_NOT_OBJECT",
        "STATE_FIELD_INVALID",
    ]


def test_frozen_donor_parity_when_available():
    donor = Path(
        os.environ.get("NEXUS_STATE_DONOR", "/private/tmp/astra-production-integrated-20260909")
    )
    if not donor.exists():
        import pytest

        pytest.skip("frozen donor comparison requires NEXUS_STATE_DONOR")
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=donor, text=True).strip()
    assert revision == "471a281badda342ccab26606e0c46cbca6867cbb"
    assert _run(donor) == _run(Path(__file__).resolve().parents[3])
