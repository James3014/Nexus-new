from pathlib import Path


def _command_block(source: str, command_name: str) -> str:
    for marker in (
        f'@nexus_group.command(name="{command_name}")',
        f'@nexus.command(name="{command_name}")',
    ):
        if marker in source:
            start = source.index(marker)
            break
    else:
        raise AssertionError(f"command not found: {command_name}")

    def_pos = source.find("\ndef ", start)
    assert def_pos != -1, f"function def not found for {command_name}"
    block_start = def_pos + 1
    search_from = block_start
    next_def = source.find("\ndef ", search_from + 1)
    next_group = source.find("\n@nexus_group.command(", search_from)
    next_top = source.find("\n@nexus.command(", search_from)
    candidates = [pos for pos in (next_def, next_group, next_top) if pos != -1]
    end = min(candidates) if candidates else len(source)
    return source[block_start:end]


MUTATING_COMMANDS_REQUIRING_ARTIFACTS = {
    "run": ("output_file", "_render_run_classification"),
    "content:rewrite": ("report_file", "write_text("),
    "learn:ingest": ("report_file", "evidence_file", "_write_hallucination_evidence"),
    "learn:register-source": ("report_file", "write_text("),
    "learn:refresh": ("report_file", "write_text("),
    "learn:refresh-plan": ("report_file", "write_text("),
    "learn:converge": ("report_file", "evidence_file", "_write_hallucination_evidence"),
    "learn:report": ("report_file", "write_text("),
    "learn:phase-slo": ("report_file", "write_text("),
    "learn:phase-kpi": ("report_file", "write_text("),
    "learn:benchmark-legacy": ("report_file", "write_text("),
    "learn:benchmark-curate": ("manifest_file", "write_text("),
    "learn:gate": ("report_file", "evidence_file", "acceptance-check", "contract-check"),
    "contract-snapshot": ("output_path", "write_text("),
    "distill": ("report_file", "write_text("),
    "delegate": ("report_file", "write_completion_envelope"),
    "research:report": ("output", "write_text("),
    "research:auto-flow": ("report_file", "semantic_status"),
    "research:run": ("report_file", "semantic_status", "write_text("),
    "research:benchmark": ("report_file", "ResearchBenchmarkService"),
    "research:meta-opt": ("report_file", "write_text("),
    "fed-init": ("report_file", "write_text("),
    "fed-run": ("report_file", "write_text("),
    "meta-run": ("report_file", "write_text("),
    "run-bug": ("report_file",),
    "learn:benchmark": ("output", "json.dump("),
    "oracle:apply": ("report_file", "write_text("),
}

READ_ONLY_OR_ROUTING_COMMANDS = (
    "status",
    "delivery-receipt",
    "ask",
    "contract-check",
    "resume",
    "research:route",
    "learn:phase-policy",
    "learn:scheduler-status",
)


def test_mutating_commands_expose_artifact_or_gate_contracts():
    source = Path("/Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py").read_text(encoding="utf-8")
    for command_name, required_tokens in MUTATING_COMMANDS_REQUIRING_ARTIFACTS.items():
        block = _command_block(source, command_name)
        for token in required_tokens:
            assert token in block, f"{command_name} missing required artifact/gate token: {token}"


def test_read_only_commands_do_not_require_write_contracts():
    source = Path("/Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py").read_text(encoding="utf-8")
    for command_name in READ_ONLY_OR_ROUTING_COMMANDS:
        block = _command_block(source, command_name)
        assert "write_text(" not in block, f"{command_name} unexpectedly writes artifacts"
