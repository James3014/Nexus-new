from typing import Iterable, List


def execute_replay_case(
    cli,
    *,
    case_type: str,
    case_id: str,
    goal: str,
    delivery_mode: str,
    verify_commands: Iterable[str],
    artifact_paths: Iterable[str],
) -> bool:
    """Route an offline replay case through the existing service entrypoints."""
    verify_list: List[str] = list(verify_commands)
    artifact_list: List[str] = list(artifact_paths)

    if case_type == "bug":
        return bool(
            cli.service.execute_bug(
                goal,
                delivery_mode=delivery_mode,
                verify_commands=verify_list,
                artifact_paths=artifact_list,
                bug_id=case_id,
            )
        )

    if case_type == "feature":
        return bool(
            cli.service.execute_feature(
                goal,
                delivery_mode=delivery_mode,
                verify_commands=verify_list,
                artifact_paths=artifact_list,
            )
        )

    raise ValueError(f"unsupported case_type: {case_type}")

