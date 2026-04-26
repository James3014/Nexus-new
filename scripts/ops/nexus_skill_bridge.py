#!/usr/bin/env python3
"""Bridge a large local skill library into small active tool-specific roots.

The archived library can contain hundreds of skills. Agent CLIs should only see
the active set, otherwise their startup skill index can exceed context budget.
This tool keeps one canonical library and symlinks selected skills into each
tool's active skill directory.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


HOME = Path.home()
DEFAULT_LIBRARY = HOME / ".agents" / "skills.archived-20260426-context-budget"
DEFAULT_STATE = HOME / ".agents" / "skill-bridge-state.json"


@dataclass(frozen=True)
class ToolRoot:
    name: str
    path: Path
    mode: str = "symlink"


TOOL_ROOTS = {
    "codex": ToolRoot("codex", HOME / ".agents" / "skills"),
    "gemini": ToolRoot("gemini", HOME / ".gemini" / "skills"),
    "antigravity": ToolRoot("antigravity", HOME / ".antigravity" / "skills"),
    # Hermes scans with pathlib rglob(), which does not traverse symlinked
    # directories. Use copy mode for Hermes active skills.
    "hermes": ToolRoot("hermes", HOME / ".hermes" / "skills", mode="copy"),
    "openclaw": ToolRoot("openclaw", HOME / ".openclaw" / "skills"),
}

CORE_SKILLS = [
    "brain-skill-router",
    "as-code-review-and-quality",
    "as-debugging-and-error-recovery",
    "as-documentation-and-adrs",
    "as-frontend-ui-engineering",
    "as-git-workflow-and-versioning",
    "as-incremental-implementation",
    "as-planning-and-task-breakdown",
    "as-security-and-hardening",
    "as-test-driven-development",
    "audit",
    "autoresearch",
    "brainstorming",
    "clarify",
    "common.git.commit",
    "common.git.tree",
    "copy-editing",
    "critique",
    "distill",
    "extract",
    "felo-cli",
    "finishing-a-development-branch",
    "frontend-design",
    "gemini-bridge",
    "git-manager",
    "harden",
    "healthcheck",
]


def expand(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"links": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"links": []}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def skill_dirs(library: Path) -> list[Path]:
    if not library.exists():
        return []
    return sorted(p for p in library.iterdir() if (p / "SKILL.md").exists())


def read_description(skill_dir: Path) -> str:
    skill_md = skill_dir / "SKILL.md"
    try:
        text = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for line in text.splitlines():
        if line.lower().startswith("description:"):
            return line.split(":", 1)[1].strip().strip('"')
    return ""


def select_tools(names: Iterable[str]) -> list[ToolRoot]:
    requested = list(names)
    if not requested or "all" in requested:
        return list(TOOL_ROOTS.values())
    unknown = sorted(set(requested) - set(TOOL_ROOTS))
    if unknown:
        raise SystemExit(f"unknown tool(s): {', '.join(unknown)}")
    return [TOOL_ROOTS[name] for name in requested]


def resolve_skill_names(library: Path, names: Iterable[str], core: bool) -> list[str]:
    requested = list(names)
    if core:
        requested.extend(CORE_SKILLS)
    if not requested:
        raise SystemExit("no skills requested")
    available = {p.name for p in skill_dirs(library)}
    missing = sorted(set(requested) - available)
    if missing:
        raise SystemExit(f"skill(s) not found in {library}: {', '.join(missing)}")
    return sorted(set(requested))


def is_managed_link(path: Path, library: Path) -> bool:
    if not path.is_symlink():
        return False
    try:
        return path.resolve().is_relative_to(library)
    except OSError:
        return False


def is_managed_copy(path: Path) -> bool:
    return path.is_dir() and (path / ".nexus-skill-bridge").exists()


def write_copy_marker(dst: Path, src: Path) -> None:
    marker = {"source": str(src), "managed_by": "nexus_skill_bridge"}
    (dst / ".nexus-skill-bridge").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def link_skill(skill: str, root: ToolRoot, library: Path, state: dict, replace: bool) -> str:
    src = library / skill
    dst = root.path / skill
    root.path.mkdir(parents=True, exist_ok=True)

    if dst.exists() or dst.is_symlink():
        if root.mode == "copy" and is_managed_link(dst, library):
            dst.unlink()
        elif is_managed_link(dst, library) or is_managed_copy(dst):
            return "already-active"
        elif not replace:
            return "exists-unmanaged"
        else:
            if dst.is_dir() and not dst.is_symlink():
                shutil.rmtree(dst)
            else:
                dst.unlink()

    if root.mode == "copy":
        shutil.copytree(src, dst, symlinks=True)
        write_copy_marker(dst, src)
        status = "copied"
    else:
        os.symlink(src, dst, target_is_directory=True)
        status = "linked"
    state.setdefault("links", []).append({"tool": root.name, "skill": skill, "path": str(dst)})
    return status


def unlink_skill(skill: str, root: ToolRoot, library: Path) -> str:
    dst = root.path / skill
    if not dst.exists() and not dst.is_symlink():
        return "absent"
    if is_managed_link(dst, library):
        dst.unlink()
        return "unlinked"
    if is_managed_copy(dst):
        shutil.rmtree(dst)
        return "removed-copy"
    if not is_managed_link(dst, library):
        return "exists-unmanaged"
    return "exists-unmanaged"


def cmd_list(args: argparse.Namespace) -> int:
    library = expand(args.library)
    rows = []
    for p in skill_dirs(library):
        desc = read_description(p)
        if args.query:
            haystack = f"{p.name} {desc}".lower()
            if args.query.lower() not in haystack:
                continue
        rows.append((p.name, desc))
    for name, desc in rows:
        print(f"{name}\t{desc}" if desc else name)
    print(f"\ncount={len(rows)}")
    return 0


def cmd_active(args: argparse.Namespace) -> int:
    library = expand(args.library)
    for root in select_tools(args.tool):
        active = []
        if root.path.exists():
            for p in sorted(root.path.iterdir()):
                if (p / "SKILL.md").exists() or is_managed_link(p, library):
                    marker = " -> " + str(p.resolve()) if p.is_symlink() else ""
                    active.append(f"{p.name}{marker}")
        print(f"[{root.name}] {root.path}")
        for item in active:
            print(f"  {item}")
        print(f"  count={len(active)}")
    return 0


def cmd_activate(args: argparse.Namespace) -> int:
    library = expand(args.library)
    state_path = expand(args.state)
    state = load_state(state_path)
    skills = resolve_skill_names(library, args.skills, args.core)
    roots = select_tools(args.tool)
    for root in roots:
        for skill in skills:
            status = link_skill(skill, root, library, state, args.replace)
            print(f"{root.name}:{skill}:{status}")
    save_state(state_path, state)
    return 0


def cmd_deactivate(args: argparse.Namespace) -> int:
    library = expand(args.library)
    skills = list(args.skills)
    if not skills:
        raise SystemExit("no skills requested")
    roots = select_tools(args.tool)
    for root in roots:
        for skill in skills:
            status = unlink_skill(skill, root, library)
            print(f"{root.name}:{skill}:{status}")
    return 0


def cmd_install_core(args: argparse.Namespace) -> int:
    args.core = True
    args.skills = []
    return cmd_activate(args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Activate archived skills across agent CLIs")
    parser.add_argument("--library", default=str(DEFAULT_LIBRARY))
    parser.add_argument("--state", default=str(DEFAULT_STATE))
    sub = parser.add_subparsers(dest="command", required=True)

    list_p = sub.add_parser("list", help="List skills in the archive")
    list_p.add_argument("query", nargs="?")
    list_p.set_defaults(func=cmd_list)

    active_p = sub.add_parser("active", help="List active skills per tool")
    active_p.add_argument("--tool", action="append", default=[])
    active_p.set_defaults(func=cmd_active)

    act_p = sub.add_parser("activate", help="Symlink skills into active roots")
    act_p.add_argument("skills", nargs="*")
    act_p.add_argument("--tool", action="append", default=[])
    act_p.add_argument("--core", action="store_true")
    act_p.add_argument("--replace", action="store_true", help="Replace unmanaged skill directories")
    act_p.set_defaults(func=cmd_activate)

    deact_p = sub.add_parser("deactivate", help="Remove managed symlinks from active roots")
    deact_p.add_argument("skills", nargs="*")
    deact_p.add_argument("--tool", action="append", default=[])
    deact_p.set_defaults(func=cmd_deactivate)

    core_p = sub.add_parser("install-core", help="Activate the curated core set")
    core_p.add_argument("--tool", action="append", default=[])
    core_p.add_argument("--replace", action="store_true")
    core_p.set_defaults(func=cmd_install_core)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
