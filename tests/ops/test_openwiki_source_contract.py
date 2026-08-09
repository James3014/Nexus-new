import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
OPENWIKI_ROOT = REPO_ROOT / "openwiki"


def _metadata(page: Path) -> dict:
    parts = page.read_text(encoding="utf-8").split("---", 2)
    if len(parts) < 3:
        return {}
    return yaml.safe_load(parts[1]) or {}


def test_openwiki_metadata_paths_are_source_verified() -> None:
    missing: list[str] = []
    for page in OPENWIKI_ROOT.rglob("*.md"):
        metadata = _metadata(page).get("openwiki", {})
        for field in ("source_paths", "test_paths"):
            for path in metadata.get(field, []):
                if not (REPO_ROOT / path).exists():
                    missing.append(f"{page.relative_to(REPO_ROOT)}:{field}:{path}")

    assert missing == []


def test_openwiki_has_no_degraded_generated_diagram_markers() -> None:
    degraded: list[str] = []
    for page in OPENWIKI_ROOT.rglob("*.md"):
        if page.name == "INSTRUCTIONS.md":
            continue
        text = page.read_text(encoding="utf-8")
        if "mermaid parse failed" in text or "converted to a text fence" in text:
            degraded.append(str(page.relative_to(REPO_ROOT)))

    assert degraded == []


def test_openwiki_issue10_claims_match_current_inventory() -> None:
    quickstart = (OPENWIKI_ROOT / "quickstart.md").read_text(encoding="utf-8")
    workflows = (OPENWIKI_ROOT / "workflows" / "github-actions.md").read_text(
        encoding="utf-8"
    )
    mcp = (OPENWIKI_ROOT / "runtime" / "mcp-gateway.md").read_text(encoding="utf-8")
    routing = (OPENWIKI_ROOT / "routing" / "capability-planner.md").read_text(
        encoding="utf-8"
    )

    workflow_files = sorted((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    listed_files = re.findall(r"\| `([^`]+\.yml)` \|", workflows)
    expected_workflow_names = {
        path.name: re.search(
            r"^name:\s*[\"']?(.*?)[\"']?\s*$",
            path.read_text(encoding="utf-8"),
            flags=re.MULTILINE,
        ).group(1)
        for path in workflow_files
    }
    listed_workflow_names = {
        filename: display_name.strip().strip("`")
        for filename, display_name in re.findall(
            r"\| `([^`]+\.yml)` \| ([^|]+) \|",
            workflows,
        )
    }

    assert len(workflow_files) == 9
    assert sorted(listed_files) == sorted(path.name for path in workflow_files)
    assert listed_workflow_names == expected_workflow_names
    assert "all 9 GitHub Actions workflows" in workflows
    assert "all 12 GitHub Actions workflows" not in workflows

    assert "seven core concept domains" in quickstart
    assert quickstart.count("**[") == 7
    assert "tests/test_battlesuit_gateway.py" not in mcp
    assert "_register_default_tools" not in mcp
    assert "tests/nexus/orchestrator/test_unified_mcp_gateway.py" in mcp
    assert "Direct status, inspection" in mcp
    assert "must not invent a Planner route" in mcp
    assert "component: MainchainEntry" not in routing
    assert "mainchain_entry.py:MainchainEntry" not in routing
    assert "```mermaid\nflowchart TD" in routing
    assert "mermaid parse failed" not in routing
    assert re.search(r"sole route and\s+capability-selection authority", routing)
    assert re.search(r"not a second selector, router, or planner", routing)

    evidence_blocks = re.findall(r"```yaml\n(.*?)```", mcp, flags=re.DOTALL)
    assert evidence_blocks
    for block in evidence_blocks:
        parsed = yaml.safe_load(block)
        assert isinstance(parsed, dict)
        assert "runtime_surfaces" in parsed
        assert "authority_roles" in parsed
        assert "evidence_basis" in parsed

    workflow_blocks = [
        yaml.safe_load(block)
        for block in re.findall(r"```yaml\n(.*?)```", workflows, flags=re.DOTALL)
    ]
    openwiki_workflow = next(
        block for block in workflow_blocks if block.get("component") == "OpenWikiUpdateWorkflow"
    )
    assert openwiki_workflow["runtime_surfaces"] == ["CI"]


def test_unwired_requires_bounded_negative_evidence() -> None:
    instructions = (OPENWIKI_ROOT / "INSTRUCTIONS.md").read_text(encoding="utf-8")

    assert "closed and complete wiring contract" in instructions
    assert "dynamic, external" in instructions
    assert "configuration-driven, plugin, and runtime-discovery" in instructions
    assert "ordinary negative repository" in instructions
    assert "Use `CI` for workflow-runner execution" in instructions
    assert "otherwise use `UNKNOWN`" in instructions
