from unittest.mock import MagicMock

from scripts.replay_case import execute_replay_case


def test_execute_replay_case_routes_bug_through_service():
    cli = MagicMock()
    cli.service.execute_bug.return_value = True

    success = execute_replay_case(
        cli,
        case_type="bug",
        case_id="OFF-001",
        goal="fix login callback",
        delivery_mode="high",
        verify_commands=["/bin/echo ok"],
        artifact_paths=["dist/report.json"],
    )

    assert success is True
    cli.service.execute_bug.assert_called_once_with(
        "fix login callback",
        delivery_mode="high",
        verify_commands=["/bin/echo ok"],
        artifact_paths=["dist/report.json"],
        bug_id="OFF-001",
    )


def test_execute_replay_case_routes_feature_through_service():
    cli = MagicMock()
    cli.service.execute_feature.return_value = True

    success = execute_replay_case(
        cli,
        case_type="feature",
        case_id="OFF-002",
        goal="add SSO",
        delivery_mode="standard",
        verify_commands=[],
        artifact_paths=[],
    )

    assert success is True
    cli.service.execute_feature.assert_called_once_with(
        "add SSO",
        delivery_mode="standard",
        verify_commands=[],
        artifact_paths=[],
    )
