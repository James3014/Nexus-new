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
    learn_actions = Path("/Users/jameschen/Workspace/nexus/scripts/engine/commands/learn_actions.py").read_text(
        encoding="utf-8"
    )
    research_actions = Path("/Users/jameschen/Workspace/nexus/scripts/engine/commands/research_actions.py").read_text(
        encoding="utf-8"
    )
    required_in_cli = {
        "run": ("build_completion_envelope(", "write_completion_envelope(", "ensure_verified_completion("),
        "delegate": ("build_completion_envelope(", "write_completion_envelope(", "ensure_verified_completion("),
        "learn:ingest": ("run_learn_ingest(", "enforce_learn_ingest_semantic_contract("),
        "learn:register-source": ("run_learn_register_source(", "verify_learn_source_lifecycle_completion("),
        "learn:refresh": ("run_learn_refresh(", "verify_learn_source_lifecycle_completion("),
        "learn:refresh-plan": ("run_learn_refresh_plan(", "verify_learn_source_lifecycle_completion("),
        "learn:report": ("run_learn_report(", "enforce_learn_report_semantic_contract("),
        "learn:phase-slo": ("run_learn_phase_slo(", "verify_learn_phase_report_completion("),
        "learn:phase-kpi": ("run_learn_phase_kpi(", "verify_learn_phase_report_completion("),
        "learn:converge": (
            "evidence_file",
            "evidence_writer=_write_hallucination_evidence",
            "hallucination_gate=_enforce_hallucination_gate",
        ),
        "research:auto-flow": ("run_research_auto_flow(",),
        "research:run": ("run_research_run(",),
    }
    for command_name, tokens in required_in_cli.items():
        block = _command_block(source, command_name)
        for token in tokens:
            assert token in block, f"{command_name} missing semantic contract token: {token}"

    delegated_contracts = {
        "learn lifecycle actions": (
            learn_actions,
            ("_finalize_learn_semantic_payload(", "completion_verifier(result.payload, context=result.command_name)"),
        ),
        "learn report/ingest actions": (
            learn_actions,
            ("semantic_status", "report_file", "enforce_learn_report_semantic_contract", "enforce_learn_ingest_semantic_contract"),
        ),
        "research:auto-flow action": (
            research_actions,
            ("build_completion_envelope(", "semantic_status", "_default_completion_verifier"),
        ),
        "research:run action": (
            research_actions,
            ("build_completion_envelope(", "semantic_status", "_default_completion_verifier"),
        ),
    }
    for label, (action_source, tokens) in delegated_contracts.items():
        for token in tokens:
            assert token in action_source, f"{label} missing semantic contract token: {token}"


def test_swarm_command_path_emits_semantic_contract_fields():
    source = Path("/Users/jameschen/Workspace/nexus/scripts/engine/commands/swarm.py").read_text(encoding="utf-8")
    assert "build_completion_envelope(" in source
    assert "write_completion_envelope(" in source
    assert "ensure_verified_completion(" in source
    assert "semantic_failures=[f\"swarm_exception:" in source
