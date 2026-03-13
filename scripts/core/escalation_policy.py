from dataclasses import dataclass, field


@dataclass(frozen=True)
class TaskMetadata:
    language: str = "unknown"
    task_scale: str = "medium"
    is_new_feature: bool = False
    is_large_refactor: bool = False
    has_external_dependency_signal: bool = False
    stacktrace_pattern: str = ""
    source_kind: str = "manual"


@dataclass(frozen=True)
class EscalationDecision:
    action: str
    actor: str
    allow_codex_patch: bool
    reason_codes: list[str] = field(default_factory=list)


class EscalationPolicy:
    def __init__(
        self,
        *,
        codex_patch_threshold: int = 3,
        research_threshold: int = 2,
        external_signal_threshold: float = 0.8,
    ):
        self.codex_patch_threshold = codex_patch_threshold
        self.research_threshold = research_threshold
        self.external_signal_threshold = external_signal_threshold

    def score_task(self, *, phase: str, task: TaskMetadata) -> dict[str, int]:
        phase_weight = 3 if phase in {"P", "D", "R", "A", "C"} else 0
        language_match = 2 if task.language == "python" else 1 if task.language != "unknown" else 0
        task_scale_weight = 2 if task.task_scale == "large" else 1 if task.task_scale == "medium" else 0
        new_feature_weight = 1 if task.is_new_feature else 0
        refactor_weight = 2 if task.is_large_refactor else 0
        stacktrace_match_weight = 3 if self._stacktrace_strength(task.stacktrace_pattern) >= self.external_signal_threshold else 0
        external_dependency_weight = 2 if task.has_external_dependency_signal else 0
        return {
            "phase_weight": phase_weight,
            "language_match": language_match,
            "task_scale_weight": task_scale_weight,
            "new_feature_weight": new_feature_weight,
            "refactor_weight": refactor_weight,
            "stacktrace_match_weight": stacktrace_match_weight,
            "external_dependency_weight": external_dependency_weight,
        }

    def decide(
        self,
        *,
        attempt: int,
        task: TaskMetadata,
        failure_summary: str,
        repeated_failure: bool,
        phase: str = "R",
    ) -> EscalationDecision:
        reasons: list[str] = []
        if task.source_kind == "docs":
            reasons.append("source_docs")

        external_signal = task.has_external_dependency_signal or self._stacktrace_strength(
            f"{task.stacktrace_pattern} {failure_summary}"
        ) >= self.external_signal_threshold

        if external_signal and attempt >= self.research_threshold:
            reasons.extend(["external_signal", "research_before_more_retries"])
            return EscalationDecision(
                action="felo_research",
                actor="felo",
                allow_codex_patch=False,
                reason_codes=reasons,
            )

        if repeated_failure and attempt >= self.codex_patch_threshold:
            reasons.extend(["repeated_failure", "codex_patch_threshold_reached"])
            return EscalationDecision(
                action="codex_patch",
                actor="codex",
                allow_codex_patch=True,
                reason_codes=reasons,
            )

        reasons.append("default_gemini_repair")
        return EscalationDecision(
            action="gemini_repair",
            actor="gemini",
            allow_codex_patch=False,
            reason_codes=reasons,
        )

    def _stacktrace_strength(self, text: str) -> float:
        lowered = text.lower()
        keywords = (
            "api",
            "sdk",
            "http",
            "oauth",
            "jwt",
            "rfc",
            "protocol",
            "fastapi",
            "react",
            "django",
            "framework",
            "cloud",
        )
        hits = sum(1 for keyword in keywords if keyword in lowered)
        return min(1.0, hits / 3.0)


def derive_task_metadata(files, diff_text: str) -> TaskMetadata:
    normalized_files = [str(f) for f in files]
    lowered = diff_text.lower()
    language = "python" if any(f.endswith(".py") for f in normalized_files) else "unknown"
    task_scale = (
        "large"
        if len(normalized_files) >= 8 or len(diff_text) >= 8000
        else "medium"
        if len(normalized_files) >= 3 or len(diff_text) >= 2000
        else "small"
    )
    return TaskMetadata(
        language=language,
        task_scale=task_scale,
        is_new_feature=any(token in lowered for token in ("new ", "feature", "add ", "implement")),
        is_large_refactor=any(token in lowered for token in ("refactor", "restructure", "rename", "extract")),
        has_external_dependency_signal=any(
            token in lowered
            for token in ("api", "sdk", "http", "oauth", "jwt", "protocol", "framework", "fastapi", "react", "django")
        ),
        stacktrace_pattern=diff_text[:1000],
        source_kind="docs" if normalized_files and all(f.endswith(".md") for f in normalized_files) else "manual",
    )
