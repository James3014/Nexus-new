# Skill Bridge Quickstart

## Purpose

Keep the full local skill library archived while exposing a small active set to
agent CLIs. This prevents startup skill-index context overflow while preserving
access to the full library.

## Paths

- Library: `~/.agents/skills.archived-20260426-context-budget`
- Codex active root: `~/.agents/skills`
- Gemini active root: `~/.gemini/skills`
- Antigravity active root: `~/.antigravity/skills`
- Hermes active root: `~/.hermes/skills`
- OpenClaw active root: `~/.openclaw/skills`
- Manager: `scripts/ops/nexus_skill_bridge.py`
- Installed commands: `nexus-skills`, `skills`

## Commands

List library skills:

```bash
nexus-skills list
nexus-skills list frontend
```

List active skills per tool:

```bash
nexus-skills active
nexus-skills active --tool gemini
```

Activate one skill for one tool:

```bash
nexus-skills activate apple-notes --tool gemini
```

Activate one skill for all tools:

```bash
nexus-skills activate apple-notes
```

Remove a managed symlink:

```bash
nexus-skills deactivate apple-notes --tool gemini
```

Reinstall the curated core set:

```bash
nexus-skills install-core
```

## Hermes Verification

Avoid `hermes skills list` for bridge verification on large installs because it
also scans bundled and hub skills. Use the Hermes loader directly:

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, "/Users/jameschen/Workspace/hermes-agent")
from tools.skills_tool import _find_all_skills
skills = _find_all_skills()
for name in ["brain-skill-router", "frontend-design", "healthcheck"]:
    print(name, any(s.get("name") == name for s in skills))
print("total", len(skills))
PY
```

`hermes skills inspect <name>` previews registry/hub sources and does not prove
that a local active skill is installed.

## Safety

The bridge creates symlinks from active roots to the archived library. It does
not overwrite unmanaged skill directories unless `--replace` is explicitly used.
Hermes is the exception: its scanner does not traverse symlinked directories, so
the bridge installs managed copies for Hermes and marks them with
`.nexus-skill-bridge`.
