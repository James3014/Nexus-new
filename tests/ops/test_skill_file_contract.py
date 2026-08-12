from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_SUPPORT_DIRECTORIES = frozenset({"agents", "references", "scripts"})


def _mapping(value: Any, source: Path) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{source}: descriptor must be a YAML mapping")
    return value


def _non_empty_string(mapping: dict[str, Any], key: str, source: Path) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{source}: {key} must be a non-empty string")
    return value.strip()


def _skill_frontmatter(path: Path) -> dict[str, Any]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError(f"{path}: missing opening frontmatter delimiter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError(f"{path}: missing closing frontmatter delimiter") from exc
    if closing == 1:
        raise ValueError(f"{path}: empty frontmatter")
    try:
        loaded = yaml.safe_load("\n".join(lines[1:closing]))
    except yaml.YAMLError as exc:
        raise ValueError(f"{path}: malformed YAML frontmatter") from exc
    return _mapping(loaded, path)


def validate_skill_descriptor(skill_path: Path) -> dict[str, Any]:
    frontmatter = _skill_frontmatter(skill_path)
    name = _non_empty_string(frontmatter, "name", skill_path)
    _non_empty_string(frontmatter, "description", skill_path)
    if name != skill_path.parent.name:
        raise ValueError(f"{skill_path}: name must match parent directory")

    skill_id = frontmatter.get("id")
    if skill_id is not None and (not isinstance(skill_id, str) or not _SAFE_ID.fullmatch(skill_id)):
        raise ValueError(f"{skill_path}: id must be a safe non-empty token")
    runtime_eligible = frontmatter.get("runtime_eligible")
    if runtime_eligible is not None and not isinstance(runtime_eligible, bool):
        raise ValueError(f"{skill_path}: runtime_eligible must be boolean")

    unexpected_dirs = sorted(
        child.name
        for child in skill_path.parent.iterdir()
        if child.is_dir() and child.name not in _SUPPORT_DIRECTORIES
    )
    if unexpected_dirs:
        raise ValueError(f"{skill_path}: unexpected support directories {unexpected_dirs}")

    openai_path = skill_path.parent / "agents" / "openai.yaml"
    if openai_path.exists():
        try:
            descriptor = _mapping(yaml.safe_load(openai_path.read_text()), openai_path)
        except yaml.YAMLError as exc:
            raise ValueError(f"{openai_path}: malformed YAML") from exc
        interface = _mapping(descriptor.get("interface"), openai_path)
        for field in ("display_name", "short_description", "default_prompt"):
            _non_empty_string(interface, field, openai_path)
        policy = _mapping(descriptor.get("policy"), openai_path)
        if not isinstance(policy.get("allow_implicit_invocation"), bool):
            raise ValueError(f"{openai_path}: policy.allow_implicit_invocation must be boolean")

    return {
        "path": skill_path.as_posix(),
        "name": name,
        "id": skill_id,
        "runtime_eligible": runtime_eligible,
        "openai_descriptor": openai_path.exists(),
    }


def scan_skill_descriptors(repo_root: Path) -> list[dict[str, Any]]:
    skills_root = repo_root / ".agents" / "skills"
    paths = sorted(skills_root.glob("**/SKILL.md"))
    if not paths:
        raise ValueError("no repository skill descriptors found")
    return [validate_skill_descriptor(path) for path in paths]


def _write_skill(root: Path, frontmatter: str, *, openai: str | None = None) -> Path:
    skill_dir = root / ".agents" / "skills" / "example"
    skill_dir.mkdir(parents=True)
    skill = skill_dir / "SKILL.md"
    skill.write_text(frontmatter, encoding="utf-8")
    if openai is not None:
        descriptor = skill_dir / "agents" / "openai.yaml"
        descriptor.parent.mkdir()
        descriptor.write_text(openai, encoding="utf-8")
    return skill


def test_current_repository_skill_descriptors_pass_contract() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    skills_root = repo_root / ".agents" / "skills"
    skill_paths = sorted(skills_root.glob("**/SKILL.md"))
    openai_paths = sorted(skills_root.glob("**/agents/openai.yaml"))

    rows = scan_skill_descriptors(repo_root)

    assert len(rows) == len(skill_paths)
    assert sum(bool(row["openai_descriptor"]) for row in rows) == len(openai_paths)
    yang = next(row for row in rows if row["name"] == "yang-ding-yi-nexus-eternal")
    assert yang["id"] == "nexus-yang-ding-yi-eternal-v5"


@pytest.mark.parametrize(
    "document",
    [
        "name: example\ndescription: missing delimiters\n",
        "---\nname: example\ndescription: missing closing delimiter\n",
        "---\nname: [\ndescription: malformed\n---\n",
        "---\nname: example\n---\n",
        "---\nname: wrong-name\ndescription: mismatch\n---\n",
        "---\nname: example\ndescription: valid\nid: ../unsafe\n---\n",
        '---\nname: example\ndescription: valid\nruntime_eligible: "yes"\n---\n',
    ],
)
def test_skill_frontmatter_failures_are_rejected(tmp_path: Path, document: str) -> None:
    skill = _write_skill(tmp_path, document)
    with pytest.raises(ValueError):
        validate_skill_descriptor(skill)


@pytest.mark.parametrize(
    "descriptor",
    [
        "interface: [\n",
        "interface: {}\npolicy:\n  allow_implicit_invocation: false\n",
        "interface:\n  display_name: Example\n  short_description: Short\n  default_prompt: Prompt\npolicy: {}\n",
        'interface:\n  display_name: Example\n  short_description: Short\n  default_prompt: Prompt\npolicy:\n  allow_implicit_invocation: "no"\n',
    ],
)
def test_openai_descriptor_failures_are_rejected(tmp_path: Path, descriptor: str) -> None:
    skill = _write_skill(
        tmp_path,
        "---\nname: example\ndescription: valid\n---\n",
        openai=descriptor,
    )
    with pytest.raises(ValueError):
        validate_skill_descriptor(skill)


def test_supported_layouts_and_optional_openai_descriptor(tmp_path: Path) -> None:
    skill = _write_skill(
        tmp_path,
        "---\nname: example\ndescription: valid\n---\n",
    )
    for directory in _SUPPORT_DIRECTORIES:
        (skill.parent / directory).mkdir(exist_ok=True)
    assert validate_skill_descriptor(skill)["openai_descriptor"] is False

    (skill.parent / "unexpected").mkdir()
    with pytest.raises(ValueError, match="unexpected support directories"):
        validate_skill_descriptor(skill)
