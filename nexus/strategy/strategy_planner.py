"""Deterministic strategy planner stub — no LLM, no prompt injection."""

from .strategy_envelope import StrategyEnvelope, create_strategy_envelope


class StrategyPlanner:
    """Generate StrategyEnvelope from task metadata without LLM."""

    def plan(self, instance_id: str, issue_summary: str = "",
             target_files: list = None, canonical_span_source: str = "",
             verification_command: str = "", **kwargs) -> StrategyEnvelope:
        """Create a StrategyEnvelope deterministically."""

        bug_hypothesis = "unknown"
        if issue_summary:
            bug_hypothesis = issue_summary[:200]

        repair_strategy = f"Apply deterministic repair for {instance_id}"

        target_symbols = kwargs.get("target_symbols", [])
        allowed_paths = kwargs.get("allowed_paths", [])
        forbidden_paths = kwargs.get("forbidden_paths", [])

        envelope = create_strategy_envelope(
            strategy_family="deterministic_repair",
            repair_strategy=repair_strategy,
            search_policy="verbatim_first",
            model_roles={"primary": "local"},
            target_symbols=target_symbols,
            forbidden_paths=forbidden_paths,
            invariants=[],
            abort_conditions=["target_file_missing", "canonical_search_unlocked"],
            context_budget=4096,
        )
        # Set legacy fields
        envelope.instance_id = instance_id
        envelope.task_goal = f"Repair issue for {instance_id}"
        envelope.issue_summary = issue_summary
        envelope.bug_hypothesis = bug_hypothesis
        envelope.strategy_quality = "normal" if issue_summary else "low"
        envelope.allowed_paths = allowed_paths
        envelope.candidate_files = target_files or []
        envelope.canonical_span_hint = canonical_span_source

        return envelope
