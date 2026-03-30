from pathlib import Path
from unittest.mock import MagicMock

from nexus.core.state_contracts import NexusState
from nexus.engine.phases.repair import RepairPhaseHandler


def test_repair_phase_uses_local_import_fix_for_benchmark(tmp_path):
    target = tmp_path / "nexus" / "engine" / "phases"
    target.mkdir(parents=True)
    research_file = target / "research.py"
    research_file.write_text(
        "#!/usr/bin/env python3\nimport json\n\nprint(os.getcwd())\n",
        encoding="utf-8",
    )

    state = NexusState(task_id="OFF-001")
    state.metadata.update(
        {
            "benchmark_run": True,
            "task_description": "Fix missing 'os' import in nexus/engine/phases/research.py",
            "benchmark_target_files": ["nexus/engine/phases/research.py"],
        }
    )

    orchestrator_factory = MagicMock()
    handler = RepairPhaseHandler(
        project_root=tmp_path,
        run_dir=tmp_path / ".nexus" / "runs" / "repair",
        router=MagicMock(route_candidates=lambda *_args, **_kwargs: []),
        orchestrator_factory=orchestrator_factory,
    )

    result = handler.run(state, {"task": state.metadata["task_description"]})

    assert result["status"] == "APPROVED"
    assert result["token_capture_status"] == "internal"
    assert result["result_object"]["patch_generated"] is True
    assert result["result_object"]["proof_type"] == "checksum"
    assert result["result_object"]["proof_value"]
    assert "import os" in research_file.read_text(encoding="utf-8")
    orchestrator_factory.assert_not_called()


def test_repair_phase_resolves_benchmark_target_by_basename(tmp_path):
    target = tmp_path / "nexus" / "engine" / "phases"
    target.mkdir(parents=True)
    research_file = target / "research.py"
    research_file.write_text(
        "#!/usr/bin/env python3\nimport json\n\nprint(os.getcwd())\n",
        encoding="utf-8",
    )

    state = NexusState(task_id="OFF-001")
    state.metadata.update(
        {
            "benchmark_run": True,
            "task_description": "Fix missing 'os' import in research.py",
            "benchmark_target_files": ["nexus/engine/phases/research.py"],
        }
    )

    handler = RepairPhaseHandler(
        project_root=tmp_path,
        run_dir=tmp_path / ".nexus" / "runs" / "repair",
        router=MagicMock(route_candidates=lambda *_args, **_kwargs: []),
        orchestrator_factory=MagicMock(),
    )

    result = handler.run(state, {"task": state.metadata["task_description"]})

    assert result["status"] == "APPROVED"
    assert "import os" in research_file.read_text(encoding="utf-8")


def test_repair_phase_benchmark_never_falls_back_to_external_review(tmp_path):
    target = tmp_path / "nexus" / "engine" / "phases"
    target.mkdir(parents=True)
    research_file = target / "research.py"
    research_file.write_text("import json\n", encoding="utf-8")

    state = NexusState(task_id="OFF-002")
    state.metadata.update(
        {
            "benchmark_run": True,
            "task_description": "Handle mysterious failure in research.py",
            "benchmark_target_files": ["nexus/engine/phases/research.py"],
        }
    )

    orchestrator_factory = MagicMock()
    handler = RepairPhaseHandler(
        project_root=tmp_path,
        run_dir=tmp_path / ".nexus" / "runs" / "repair",
        router=MagicMock(route_candidates=lambda *_args, **_kwargs: []),
        orchestrator_factory=orchestrator_factory,
    )

    result = handler.run(state, {"task": state.metadata["task_description"]})

    assert result["status"] == "REJECTED"
    assert result["token_capture_status"] == "internal"
    assert result["result_object"]["no_change_reason"] in {
        "unsupported_benchmark_repair_pattern",
        "benchmark_requires_local_repair",
    }
    orchestrator_factory.assert_not_called()
