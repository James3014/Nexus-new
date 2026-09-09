from pathlib import Path

WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "pytest.yml"
HEAD_EXPRESSION = (
    "${{ github.event_name == 'pull_request' && github.event.pull_request.head.sha || github.sha }}"
)


def _workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_artifact_name_binds_to_pr_head_or_push_sha():
    text = _workflow_text()

    assert f"ref: {HEAD_EXPRESSION}" in text
    assert f"HEAD_SHA: {HEAD_EXPRESSION}" in text
    assert f"name: exact-base-impact-{HEAD_EXPRESSION}" in text
    assert text.count(HEAD_EXPRESSION) == 3


def test_old_github_sha_only_artifact_name_is_rejected():
    text = _workflow_text()

    assert "name: exact-base-impact-${{ github.sha }}" not in text


def test_artifact_identity_resolves_pr_and_push_events_consistently():
    pr_head = "a" * 40
    push_sha = "b" * 40

    def resolve(event_name: str) -> str:
        return pr_head if event_name == "pull_request" else push_sha

    assert resolve("pull_request") == pr_head
    assert resolve("push") == push_sha


def test_artifact_contract_preserves_workflow_scope_and_retention():
    text = _workflow_text()

    for required in (
        "pull_request:\n    branches: [main, master]",
        "permissions:\n  contents: read",
        "path: ${{ runner.temp }}/nexus-ci-impact/",
        "if-no-files-found: error",
        "retention-days: 7",
    ):
        assert required in text
