from pathlib import Path

from nexus.services.local_heal.context import (
    GovernanceContext,
    HealContext,
    OperationalContext,
)
from nexus.services.local_heal.parser import SearchReplaceParser
from nexus.services.local_heal.patcher import Patcher
from nexus.services.local_heal.phases.patch_synthesis import PatchSynthesisPhase


def test_patch_synthesis_phase_applies_valid_search_replace(tmp_path):
    target = tmp_path / "hello.py"
    target.write_text("def hello():\n    return False\n", encoding="utf-8")

    def model_client(system_prompt, user_prompt, model=None, timeout=None):
        return (
            "FILE: hello.py\n"
            "SEARCH:\n"
            "def hello():\n"
            "    return False\n"
            "REPLACE:\n"
            "def hello():\n"
            "    return True\n"
            "END"
        )

    ctx = HealContext(
        op=OperationalContext(
            instance_id="patch-phase",
            repo_dir=tmp_path,
            problem_statement="Change hello to return True",
            repro_evidence="AssertionError: hello returned False",
            localized_files=[("hello.py", target.read_text(encoding="utf-8"))],
            plan={"search_symbols": ["hello"], "repair_strategy": "rewrite hello"},
            max_tries=1,
        ),
        gov=GovernanceContext(),
    )

    phase = PatchSynthesisPhase(
        parser=SearchReplaceParser(),
        patcher=Patcher(),
        model_client=model_client,
    )

    result = phase.execute(ctx)

    assert result.success is True
    assert target.read_text(encoding="utf-8") == "def hello():\n    return True\n"
    assert "return True" in ctx.op.final_patch
    assert "--- a/hello.py" in ctx.op.final_patch


def test_patch_synthesis_phase_rejects_duplicate_top_level_redefinition(tmp_path):
    original = (
        "class InventoryCounter:\n"
        "    def __init__(self):\n"
        "        self.count = 0\n"
        "\n"
        "    def increment(self):\n"
        "        self.count += 1\n"
    )
    target = tmp_path / "counter_bug.py"
    target.write_text(original, encoding="utf-8")

    def model_client(system_prompt, user_prompt, model=None, timeout=None):
        return (
            "FILE: counter_bug.py\n"
            "SEARCH:\n"
            f"{original}"
            "REPLACE:\n"
            f"{original}\n"
            "class InventoryCounter:\n"
            "    def __init__(self):\n"
            "        self.count = 0\n"
            "        self.lock = None\n"
            "END"
        )

    ctx = HealContext(
        op=OperationalContext(
            instance_id="patch-phase-duplicate",
            repo_dir=tmp_path,
            problem_statement="Fix duplicate class issue",
            repro_evidence="AssertionError",
            localized_files=[("counter_bug.py", original)],
            plan={"search_symbols": ["InventoryCounter"]},
            max_tries=1,
        ),
        gov=GovernanceContext(),
    )

    phase = PatchSynthesisPhase(
        parser=SearchReplaceParser(),
        patcher=Patcher(),
        model_client=model_client,
    )

    result = phase.execute(ctx)

    assert result.success is False
    assert result.error_reason == "NAME_SANITY_ERROR"
    assert target.read_text(encoding="utf-8") == original
