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


def test_core_command_paths_emit_semantic_contract_fields():
    source = Path("/Users/jameschen/Workspace/nexus/scripts/engine/nexus_cli.py").read_text(encoding="utf-8")
    required = {
        "run": ("build_completion_envelope(", "write_completion_envelope(", "ensure_verified_completion("),
        "research:auto-flow": ("build_completion_envelope(", "semantic_status", "ensure_verified_completion("),
        "research:run": ("build_completion_envelope(", "semantic_status", "ensure_verified_completion("),
        "delegate": ("build_completion_envelope(", "write_completion_envelope(", "ensure_verified_completion("),
        "learn:ingest": ("semantic_status", "report_file"),
        "learn:report": ("semantic_status", "report_file"),
        "learn:converge": ("evidence_file", "_write_hallucination_evidence(", "_enforce_hallucination_gate("),
    }
    for command_name, tokens in required.items():
        block = _command_block(source, command_name)
        for token in tokens:
            assert token in block, f"{command_name} missing semantic contract token: {token}"


def test_swarm_command_path_emits_semantic_contract_fields():
    source = Path("/Users/jameschen/Workspace/nexus/scripts/engine/commands/swarm.py").read_text(encoding="utf-8")
    assert "build_completion_envelope(" in source
    assert "write_completion_envelope(" in source
    assert "ensure_verified_completion(" in source
    assert "semantic_failures=[f\"swarm_exception:" in source
