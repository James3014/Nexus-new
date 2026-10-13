from __future__ import annotations

import re
from pathlib import Path

import yaml

WORKFLOW = Path(".github/workflows/hybrid-replication-capture-reusable.yml")
CALLER = Path(".github/workflows/hybrid-replication-capture.yml")
TEMPLATE = Path("docs/research/hybrid_replication_v2/capture_caller.template.yml")
INPUT_NAMES = {
    "activation_state": "NEXUS_HYBRID_REPLICATION_ACTIVATION_STATE",
    "t_auto": "NEXUS_HYBRID_REPLICATION_T_AUTO",
    "excluded_tasks": "NEXUS_HYBRID_REPLICATION_EXCLUDED_TASKS",
    "exclusion_set_sha256": "NEXUS_HYBRID_REPLICATION_EXCLUSION_SET_SHA256",
    "readiness_control_token": "NEXUS_HYBRID_REPLICATION_READINESS_CONTROL_TOKEN",
}
TEMPLATE_USES = re.compile(
    r"^James3014/Nexus-new/\.github/workflows/hybrid-replication-capture-reusable\.yml"
    r"@(__PIN_SHA__|[0-9a-f]{40})$"
)


def _load(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML (YAML 1.1) parses the bare key ``on`` as boolean True.
    if True in data and "on" not in data:
        data["on"] = data.pop(True)
    return data


def _capture_job(path: Path) -> dict:
    return _load(path)["jobs"]["capture"]


def test_hybrid_replication_capture_workflow_is_event_driven_and_fail_closed() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "workflow_call:" in text
    assert "NEXUS_HYBRID_REPLICATION_CAPTURE_V1" not in text
    assert "EVENT_PATH: ${{ github.event_path }}" not in text
    assert 'os.environ["GITHUB_EVENT_PATH"]' in text
    assert "NEXUS-HYBRID-REPLICATION-CAPTURE-V1" in text
    assert "NEXUS-HYBRID-REPLICATION-ADMISSION-V1" in text
    assert "NEXUS-HYBRID-REPLICATION-CONTRACT-DELTA-V1" in text
    assert "NEXUS-HYBRID-REPLICATION-INTAKE-GAP-V1" in text
    assert "${{ inputs.activation_state }}" in text
    assert "${{ inputs.t_auto }}" in text
    assert "${{ inputs.exclusion_set_sha256 }}" in text
    assert "${{ inputs.readiness_control_token }}" in text
    assert "NEXUS-HYBRID-REPLICATION-READINESS-CONTROL-V1:" in text
    assert 'issue_author == repository.split("/", 1)[0]' in text
    assert 'disposition = "READINESS_CONTROL_EXCLUDED"' in text
    assert 'admission_activation_state = "READINESS_CONTROL_PENDING"' in text
    assert "not is_readiness_control" in text
    assert 'activation_state != "AUTOMATIC_CAPTURE_READY"' in text
    assert "activation exclusion-set hash mismatch; admission blocked" in text
    assert "implementation_pr_numbers" in text
    assert "INTAKE_PROTOCOL_LOSS_IMPLEMENTATION_PRESENT" in text
    assert "INTAKE_PROTOCOL_LOSS_TERMINAL_BEFORE_ADMISSION" in text
    assert "EXCLUDE_PARENT_TASK_PRE_BOUNDARY" in text
    assert "opening_capture_missing_or_ambiguous_before_edit" in text


def test_capture_workflow_has_no_routing_or_merge_authority() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    assert "RESEARCH_OBSERVATION_ONLY / NO_ENGINEERING_AUTHORITY" in text
    assert "pull-requests: write" not in text
    assert "contents: write" not in text
    assert "actions: write" not in text
    assert "issues: write" in text


def test_capture_workflow_excludes_campaign_meta_work_in_disposition_chain() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    chain = text[text.index('disposition = "CONTAMINATION_EXCLUDED"') :]
    chain = chain[: chain.index('disposition = "EXCLUDED_PRE_BOUNDARY"')]

    assert 'disposition = "CAMPAIGN_META_WORK_EXCLUDED"' in chain
    assert "CAMPAIGN_MARKERS" in chain
    assert '"NEXUS-HYBRID-REPLICATION"' in text
    assert '"#1216"' in text
    assert '"#1196"' in text


def test_reusable_declares_workflow_call_with_exactly_the_five_inputs() -> None:
    on = _load(WORKFLOW)["on"]

    assert set(on) == {"workflow_call"}
    inputs = on["workflow_call"]["inputs"]
    assert set(inputs) == set(INPUT_NAMES)
    for name, spec in inputs.items():
        assert spec == {"type": "string", "required": False, "default": ""}, name
    assert "concurrency" not in _load(WORKFLOW)
    assert _capture_job(WORKFLOW)["permissions"] == {"contents": "read", "issues": "write"}
    env = _capture_job(WORKFLOW)["env"]
    for name in INPUT_NAMES:
        assert f"${{{{ inputs.{name} }}}}" in env.values()


def test_reusable_contains_no_vars_reference() -> None:
    assert "vars." not in WORKFLOW.read_text(encoding="utf-8")


def test_callers_pass_exactly_the_reusable_inputs_mapped_to_matching_vars() -> None:
    declared = set(_load(WORKFLOW)["on"]["workflow_call"]["inputs"])
    for path in (CALLER, TEMPLATE):
        data = _load(path)
        assert data["on"] == {"issues": {"types": ["opened", "edited"]}}, path
        assert data["permissions"] == {}, path
        job = data["jobs"]["capture"]
        assert job["permissions"] == {"contents": "read", "issues": "write"}, path
        assert set(job["with"]) == declared, path
        for name, var in INPUT_NAMES.items():
            assert job["with"][name] == f"${{{{ vars.{var} }}}}", (path, name)

    caller_lines = CALLER.read_text(encoding="utf-8").splitlines()
    template_lines = TEMPLATE.read_text(encoding="utf-8").splitlines()
    assert len(caller_lines) == len(template_lines)
    differing = [(a, b) for a, b in zip(caller_lines, template_lines, strict=True) if a != b]
    assert len(differing) == 1
    assert differing[0][0].strip().startswith("uses:")
    assert differing[0][1].strip().startswith("uses:")
    assert _load(CALLER)["jobs"]["capture"]["uses"] == (
        "./.github/workflows/hybrid-replication-capture-reusable.yml"
    )


def test_template_uses_is_pinned_to_reusable_in_nexus_new() -> None:
    uses = _load(TEMPLATE)["jobs"]["capture"]["uses"]

    assert TEMPLATE_USES.match(uses)
    assert TEMPLATE_USES.match(
        uses.replace("__PIN_SHA__", "0123456789abcdef0123456789abcdef01234567")
    )
    assert not TEMPLATE_USES.match(uses.replace("__PIN_SHA__", "main"))
