from pathlib import Path


LEGACY_SEAM_TOKENS = (
    "Compat-Fallback",
    "materialize_test_scripts",
    "_run_engine_flow(",
)

WORK_COMMANDS = (
    "run",
    "content:rewrite",
    "learn:ingest",
    "learn:register-source",
    "learn:refresh",
    "learn:refresh-plan",
    "learn:converge",
    "learn:report",
    "learn:benchmark-legacy",
    "learn:benchmark-curate",
    "learn:gate",
    "distill",
    "resume",
    "delegate",
    "research:route",
    "research:report",
    "research:auto-flow",
    "research:run",
    "research:benchmark",
    "research:meta-opt",
    "learn:phase-policy",
    "learn:benchmark",
    "oracle:apply",
)


def _command_block(source: str, command_name: str) -> str:
    marker = f'@nexus_group.command(name="{command_name}")'
    start = source.index(marker)
    next_pos = source.find("@nexus_group.command(", start + len(marker))
    next_top = source.find("@nexus.command(", start + len(marker))
    candidates = [pos for pos in (next_pos, next_top) if pos != -1]
    end = min(candidates) if candidates else len(source)
    return source[start:end]


def test_all_work_commands_do_not_reference_legacy_run_seam():
    source = Path("/Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py").read_text(encoding="utf-8")
    for command_name in WORK_COMMANDS:
        block = _command_block(source, command_name)
        for token in LEGACY_SEAM_TOKENS:
            assert token not in block, f"{command_name} still references legacy seam token: {token}"


def test_run_family_uses_canonical_seams():
    source = Path("/Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py").read_text(encoding="utf-8")
    run_block = _command_block(source, "run")
    assert "execute_single_task_via_service(" in run_block
    assert "class _CompatService" not in source

    async_runner = Path("/Users/jameschen/Workspace/nexus/nexus/engine/cli_runner_async.py").read_text(encoding="utf-8")
    assert "execute_single_task_via_service(" in async_runner
    assert "materialize_test_scripts" not in async_runner
    assert "_run_engine_flow(" not in async_runner
