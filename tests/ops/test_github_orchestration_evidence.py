import json
import subprocess

from scripts.ops import github_orchestration_evidence as cli
from tests.nexus.orchestrator.test_github_orchestration import _compat_projection_inputs


def test_gh_provider_uses_read_only_get(monkeypatch):
    seen = []

    def fake_run(command, **kwargs):
        seen.append(command)
        return subprocess.CompletedProcess(command, 0, stdout='{"ok": true}', stderr="")

    monkeypatch.setattr(cli.subprocess, "run", fake_run)
    assert cli._gh_json("repos/James3014/Nexus-new") == {"ok": True}
    assert seen == [["gh", "api", "--method", "GET", "repos/James3014/Nexus-new"]]


def test_collect_from_github_calls_canonical_builder_with_raw_evidence(monkeypatch):
    values = _compat_projection_inputs()
    manifest = json.loads(values["controller_manifest_bytes"])
    head = manifest["head_sha"]
    checks = [
        {**item, "id": 8000 + index, "details_url": ""}
        for index, item in enumerate(values["check_observations"], start=1)
    ] + [
        {
            "id": 9001,
            "name": "Trusted controller (default branch)",
            "status": "completed",
            "conclusion": "success",
            "head_sha": head,
            "details_url": "https://github.com/James3014/Nexus-new/actions/runs/123/job/9001",
        }
    ]

    def fake_gh(endpoint, *fields):
        if endpoint.endswith("/pulls/1210"):
            return {
                "body": values["pr_body"],
                "head": {"sha": head},
            }
        if endpoint.endswith(f"/commits/{head}/check-runs"):
            return {"check_runs": checks}
        if endpoint.endswith("/actions/runs/123/artifacts"):
            return {
                "artifacts": [
                    {"id": 11, "name": "trusted-anchor-controller-123", "expired": False},
                    {"id": 12, "name": "trusted-anchor-executor-123", "expired": False},
                ]
            }
        if endpoint.endswith("/actions/artifacts"):
            return {
                "artifacts": [
                    {
                        "id": 13,
                        "name": f"exact-base-impact-{head}",
                        "expired": False,
                        "workflow_run": {"head_sha": head},
                    }
                ]
            }
        if endpoint.endswith("/issues/comments/5891783503"):
            return {
                "body": values["acceptance_comment_body"],
                "user": {"login": "James3014"},
            }
        if endpoint.endswith("/rulesets"):
            return [{"id": 77, "enforcement": "active"}]
        if endpoint.endswith("/rulesets/77"):
            return {
                "rules": [
                    {
                        "type": "required_status_checks",
                        "parameters": {
                            "required_status_checks": [
                                {"context": name} for name in values["required_check_names"]
                            ]
                        },
                    }
                ]
            }
        raise AssertionError(endpoint)

    def fake_member(_repository, artifact_id, member):
        if (artifact_id, member) == (11, "manifest.json"):
            return values["controller_manifest_bytes"]
        if (artifact_id, member) == (12, "raw-evidence.json"):
            return values["verifier_evidence_bytes"]
        if (artifact_id, member) == (13, "plan.json"):
            return json.dumps(values["impact_plan"]).encode()
        if (artifact_id, member) == (13, "classification.json"):
            return json.dumps(values["impact_classification"]).encode()
        raise AssertionError((artifact_id, member))

    monkeypatch.setattr(cli, "_gh_json", fake_gh)
    monkeypatch.setattr(cli, "_artifact_member", fake_member)
    monkeypatch.setattr(
        cli,
        "_content_bytes",
        lambda repository, path, ref: values["task_card_bytes"],
    )

    projected = cli.collect_from_github(
        repository="James3014/Nexus-new",
        issue_number=1211,
        pull_request_number=1210,
        acceptance_comment_id=5891783503,
        implementer="coordinator-implementer",
    )
    assert projected.schema == "nexus.github_orchestration_evidence.v2"
    assert projected.head_sha == head
    assert projected.current_main_sha == manifest["base_sha"]
    assert projected.candidate.reviewer == "review-session-1"


def test_required_check_discovery_fails_when_ruleset_has_no_checks(monkeypatch):
    monkeypatch.setattr(cli, "_gh_json", lambda endpoint, *fields: [])
    try:
        cli._required_check_names("James3014/Nexus-new")
    except ValueError as exc:
        assert str(exc) == "REQUIRED_CHECK_STATE_UNPROVEN"
    else:
        raise AssertionError("missing required checks must fail closed")
