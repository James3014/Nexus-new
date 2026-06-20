"""Strategy-conditioned prompt renderer — shadow mode only."""

from typing import Optional
from .strategy_envelope import StrategyEnvelope


class StrategyConditionedPromptBlock:
    """A strategy-conditioned prompt block. Shadow-only, never replaces baseline."""

    def __init__(self, strategy_id: str, block: str, block_hash: str):
        self.strategy_id = strategy_id
        self.block = block
        self.block_hash = block_hash


class StrategyPromptRenderer:
    """Render StrategyEnvelope into a prompt block. Shadow mode only."""

    TEMPLATE = """[STRATEGY CONTEXT — trace-only, shadow mode]
Strategy ID: {strategy_id}
Task Goal: {task_goal}
Bug Hypothesis: {bug_hypothesis}
Repair Strategy: {repair_strategy}
Target Symbols: {target_symbols}
Allowed Paths: {allowed_paths}
Forbidden Paths: {forbidden_paths}
Candidate Files: {candidate_files}
Canonical Span Hint: {canonical_span_hint}
Max Files: {max_files_to_modify}
Allowed Patch Styles: {allowed_patch_styles}
Require Effective Change: {require_effective_change}
Require Source Snapshot: {require_source_snapshot}
Require Canonical Search Lock: {require_canonical_search_lock}
Abort Conditions: {abort_conditions}
[END STRATEGY CONTEXT]
"""

    def render(self, envelope: StrategyEnvelope) -> StrategyConditionedPromptBlock:
        """Render StrategyEnvelope into a prompt block."""
        import hashlib

        block = self.TEMPLATE.format(
            strategy_id=envelope.strategy_id,
            task_goal=envelope.task_goal,
            bug_hypothesis=envelope.bug_hypothesis,
            repair_strategy=envelope.repair_strategy,
            target_symbols=", ".join(envelope.target_symbols) or "none",
            allowed_paths=", ".join(envelope.allowed_paths) or "none",
            forbidden_paths=", ".join(envelope.forbidden_paths) or "none",
            candidate_files=", ".join(envelope.candidate_files) or "none",
            canonical_span_hint=envelope.canonical_span_hint or "none",
            max_files_to_modify=envelope.max_files_to_modify,
            allowed_patch_styles=", ".join(envelope.allowed_patch_styles),
            require_effective_change=envelope.require_effective_change,
            require_source_snapshot=envelope.require_source_snapshot,
            require_canonical_search_lock=envelope.require_canonical_search_lock,
            abort_conditions=", ".join(envelope.abort_conditions),
        )

        block_hash = hashlib.sha256(block.encode()).hexdigest()[:16]

        return StrategyConditionedPromptBlock(
            strategy_id=envelope.strategy_id,
            block=block,
            block_hash=block_hash,
        )
