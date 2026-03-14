from dataclasses import dataclass, field

from nexus.core.escalation import EscalationDecision, TaskMetadata


@dataclass(frozen=True)
class ActionBrief:
    action: str
    actor: str
    title: str
    instructions: str
    context: dict[str, str] = field(default_factory=dict)


def build_action_brief(
    *,
    decision: EscalationDecision,
    task: TaskMetadata,
    failure_summary: str,
    files: list[str],
    violations: list[dict],
) -> ActionBrief:
    if decision.action == "felo_research":
        return ActionBrief(
            action=decision.action,
            actor=decision.actor,
            title="Research external behavior before more retries",
            instructions=_build_felo_instructions(task, failure_summary, violations),
            context=_build_felo_context(task, failure_summary, violations),
        )

    if decision.action == "codex_patch":
        return ActionBrief(
            action=decision.action,
            actor=decision.actor,
            title="Escalate to Codex definitive patch",
            instructions=(
                "Provide a definitive compile-ready patch for the remaining issues. "
                "Do not return general advice. Focus only on the failing files and keep changes minimal."
            ),
            context={
                "failure_summary": failure_summary,
                "target_files": ", ".join(files[:8]),
            },
        )

    return ActionBrief(
        action=decision.action,
        actor=decision.actor,
        title="Continue Gemini repair with focused feedback",
        instructions=_build_gemini_instructions(failure_summary, violations),
        context={
            "failure_summary": failure_summary,
            "target_files": ", ".join(files[:8]),
        },
    )


def _build_gemini_instructions(failure_summary: str, violations: list[dict]) -> str:
    if not violations:
        return (
            "Retry the repair with minimal changes. Re-check the failing logic and avoid broad refactors. "
            f"Current failure summary: {failure_summary}"
        )

    top_items = []
    for violation in violations[:3]:
        top_items.append(
            f"{violation.get('file', 'unknown')}:{violation.get('line', 1)} -> "
            f"{violation.get('reason', 'unspecified issue')} | "
            f"suggestion={violation.get('suggestion', 'n/a')}"
        )
    joined = " | ".join(top_items)
    return (
        "Retry the repair using the review feedback below. "
        "Keep the diff minimal, preserve passing behavior, and do not re-try already failed blind fixes. "
        f"Feedback: {joined}"
    )


def _build_felo_instructions(
    task: TaskMetadata, failure_summary: str, violations: list[dict]
) -> str:
    return (
        "Research the external/framework behavior before another repair attempt. "
        "Use the provided context to confirm official behavior or current-world behavior, then summarize only the actionable facts."
    )


def _build_felo_context(
    task: TaskMetadata, failure_summary: str, violations: list[dict]
) -> dict[str, str]:
    observed = failure_summary or "Review failed, but the exact runtime mismatch is still unclear."
    tried = "; ".join(
        violation.get("suggestion", "") for violation in violations[:3] if violation.get("suggestion")
    ) or "Previous repair attempts did not pass review."
    need = (
        "Confirm official behavior for the suspected framework / API / protocol area "
        "and identify whether the current assumption is incorrect."
    )
    return {
        "system": task.language,
        "observed": observed,
        "expected": "A repair that passes review without repeated retries.",
        "tried": tried,
        "need": need,
        "stacktrace_pattern": task.stacktrace_pattern[:400],
    }
