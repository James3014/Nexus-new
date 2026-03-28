from __future__ import annotations

from pathlib import Path


def _has(path: Path, name: str) -> bool:
    return (path / name).exists()


def _contains_any(text: str, candidates: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(candidate in lowered for candidate in candidates)


def detect_verification_language(project_root: Path, task_name: str) -> str:
    task_hint = task_name.lower()

    if _contains_any(task_hint, ("rust", ".rs", "cargo", "nexus-core", "nexus-rust", "reflex")):
        return "rust"
    if _contains_any(task_hint, ("golang", " go ", ".go", "go.mod", "nexus-swarm", "etcd")):
        return "go"
    if _contains_any(task_hint, ("python", "pytest", ".py", "uv run", "pyproject")):
        return "python"

    if _has(project_root, "pyproject.toml") or _has(project_root, "pytest.ini"):
        return "python"
    if _has(project_root, "Cargo.toml"):
        return "rust"
    if _has(project_root, "go.mod"):
        return "go"
    return "python"


def suggest_verification_commands(project_root: Path, task_name: str) -> list[str]:
    language = detect_verification_language(project_root, task_name)

    if language == "rust":
        if _has(project_root, "Cargo.toml"):
            return ["cargo test --manifest-path Cargo.toml"]
        if (project_root / "nexus-core" / "Cargo.toml").exists():
            return ["cargo test --manifest-path nexus-core/Cargo.toml"]
        return ["cargo test"]

    if language == "go":
        if _has(project_root, "go.mod"):
            return ["go test ./..."]
        if (project_root / "nexus-swarm" / "go.mod").exists():
            return ["cd nexus-swarm && go test ./..."]
        return ["go test ./..."]

    if _has(project_root, "pytest.ini"):
        return ["uv run pytest -q"]
    if _has(project_root, "pyproject.toml"):
        return ["uv run pytest -q"]
    return ["python3 -m pytest -q"]
