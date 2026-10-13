"""Opt-in contract test against an installed nexus-open-swe-runtime.

Not collected by default (``pytest.ini`` collects only ``test_*.py``) because CI
has no installed runtime. Run explicitly on a host that has one:

    NEXUS_OPEN_SWE_RUNTIME_PYTHON=<runtime venv>/bin/python \
        python -m pytest -q tests/services/contract_installed_open_swe_runtime.py
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from nexus.services.external_intelligence_core_binding import envelope_sha256
from tests.services.test_external_intelligence_core_binding import (
    bound_unit_mapping,
    make_bound_repo,
)

RUNTIME_PYTHON = Path(
    os.environ.get(
        "NEXUS_OPEN_SWE_RUNTIME_PYTHON",
        str(Path.home() / ".local/share/nexus-open-swe-runtime/venv/bin/python"),
    )
)


# ---------------------------------------------------------------------------
# Contract test against the installed nexus-open-swe-runtime
# ---------------------------------------------------------------------------

_ADMISSION_SCRIPT = r"""
import json, sys
from pathlib import Path
import nexus_open_swe_runtime.cli as cli
request = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
prompt = request["prompt"]
allowed = tuple(json.loads(cli._prompt_field(prompt, "authorized_mutation_paths")))
admission = cli._semantic_v2_admission(
    request, Path(request["workspace_path"]), Path(request["artifact_path"]), prompt, allowed
)
print(json.dumps({"decision": admission.decision, "reason": admission.reason_code}))
"""


def runtime_admission(request: dict[str, Any], scratch: Path) -> dict[str, Any]:
    """Run the installed runtime's admission gate on a Nexus-built worker_run request."""
    request_path = scratch / f"admission-request-{len(list(scratch.glob('admission-*')))}.json"
    request_path.write_text(json.dumps(request), encoding="utf-8")
    result = subprocess.run(
        [str(RUNTIME_PYTHON), "-I", "-c", _ADMISSION_SCRIPT, str(request_path)],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.strip().splitlines()[-1])


def _runtime_available() -> bool:
    if not RUNTIME_PYTHON.is_file():
        return False
    probe = subprocess.run(
        [
            str(RUNTIME_PYTHON),
            "-I",
            "-c",
            "import nexus_open_swe_runtime.cli as c; c._validate_repository_mutation_binding",
        ],
        capture_output=True,
        timeout=60,
        check=False,
    )
    return probe.returncode == 0


def _bound_fanout_requests(tmp_path: Path, monkeypatch) -> tuple[dict[str, Any], Any]:
    """Drive the real fanout + Open SWE transport and capture the worker_run request."""
    import nexus.services.open_swe_external_intelligence as module
    from nexus.services.external_intelligence_fanout import (
        AdaptiveWorkerFanoutRuntime,
        CapacityLease,
        FanoutStore,
        GitWorktreeAllocator,
    )

    scenario = make_bound_repo(tmp_path)
    unit = bound_unit_mapping(tmp_path, scenario)
    captured: list[dict[str, Any]] = []

    def runtime_call(_executable, payload, **_kwargs):
        if payload["operation"] == "identity":
            from tests.services.test_open_swe_worker_transport import _completed

            return _completed(module, payload), "", False, ""
        captured.append(json.loads(json.dumps(payload)))
        return None, "", False, "runtime_not_found"

    monkeypatch.setattr(module, "_runtime_call", runtime_call)
    transport = module.OpenSWEWorkerTransport(
        model_provider="google_genai",
        model_id="gemini-test",
        executable="/opt/nexus-open-swe-runtime/bin/nexus-open-swe-runtime",
        expected_artifact_sha256="a" * 64,
        require_worker_binding=True,
    )
    runtime = AdaptiveWorkerFanoutRuntime(
        allocator=GitWorktreeAllocator(scenario.repo, tmp_path / "workspaces"),
        store=FanoutStore(tmp_path / "state"),
        transport=transport,
    )
    runtime.run([unit], CapacityLease(1, 1, 1, 1))
    assert len(captured) == 1
    return captured[0], scenario


def test_installed_runtime_admits_nexus_minted_binding_and_rejects_variants(tmp_path, monkeypatch):
    assert _runtime_available(), f"installed nexus-open-swe-runtime not usable at {RUNTIME_PYTHON}"
    request, _scenario = _bound_fanout_requests(tmp_path, monkeypatch)
    scratch = tmp_path / "admission"
    scratch.mkdir()
    assert runtime_admission(request, scratch) == {"decision": "ADMIT", "reason": None}

    artifact = Path(request["artifact_path"])
    bound = json.loads(artifact.read_text(encoding="utf-8"))

    def variant(envelope: dict[str, Any], *, prompt_sha: str | None = None) -> dict[str, Any]:
        path = scratch / f"variant-{len(list(scratch.glob('variant-*')))}.json"
        path.write_text(json.dumps(envelope), encoding="utf-8")
        sha = prompt_sha or envelope_sha256(envelope)
        prompt = "\n".join(
            f"envelope_sha256={sha}" if line.startswith("envelope_sha256=") else line
            for line in request["prompt"].splitlines()
        )
        return {**request, "artifact_path": str(path), "prompt": prompt}

    unbound = {key: value for key, value in bound.items() if key != "repository_mutation_binding"}
    assert runtime_admission(variant(unbound), scratch)["reason"] == "envelope_keys"
    wrong_op = {**request, "operation_id": "0" * 64}
    assert runtime_admission(wrong_op, scratch)["reason"] == "core_binding_operation"
    tampered = json.loads(json.dumps(bound))
    tampered["repository_mutation_binding"]["integration_authority"]["execution_lane"] = (
        "DIRECT_CANONICAL"
    )
    assert runtime_admission(variant(tampered), scratch)["reason"] == "core_binding_hash"
