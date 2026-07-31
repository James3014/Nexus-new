from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_FILES = (
    "AGENTS.md",
    "MUSE_PROTO.md",
    "GEMINI.md",
    ".gemini/GEMINI.md",
    "CLAUDE.md",
    "MEMORY.md",
    "SOUL.md",
    ".cursorrules",
)
FORBIDDEN_TOKENS = (
    "nexus-sync",
    "STATE.yaml",
    "Nexus-Singularity-V17",
    "Nexus-Singularity-V26",
    "AGENT_MANDATORY_PROTOCOL.md",
    "/Users/jameschen/Workspace/nexus/",
    '--filter "domain=tech"',
)


def test_bootstrap_files_use_current_worktree_authority():
    contents = {path: (ROOT / path).read_text(encoding="utf-8") for path in BOOTSTRAP_FILES}
    for path, content in contents.items():
        assert not any(token in content for token in FORBIDDEN_TOKENS), path

    assert "active Git-tracked Task Card" in contents["AGENTS.md"]
    assert "MUSE_PROTO.md` is only" in contents["MUSE_PROTO.md"]
    assert "../GEMINI.md" in contents[".gemini/GEMINI.md"]


def test_bootstrap_file_set_is_complete_and_tracked():
    for path in BOOTSTRAP_FILES:
        assert (ROOT / path).is_file(), path
