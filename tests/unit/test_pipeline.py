import pytest
from pathlib import Path
import json
import sys
from nexus.services.local_heal.evaluation_gate import TestResult
from nexus.services.local_heal.pipeline import HealPipeline, HealContext

def test_pipeline_successful_flow(tmp_path):
    # 建立目標模擬檔案
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    # 模擬 LLM 完美輸出
    def mock_generate(system, prompt):
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

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_id",
        repo_dir=tmp_path,
        problem_statement="Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )

    # 手動塞入定位檔案避免 BM25 檢索不到
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)
    assert not res_ctx.errors
    assert res_ctx.runner_completed is True
    assert res_ctx.solve_eligible is True
    assert "return True" in res_ctx.final_patch
    assert "--- a/hello.py" in res_ctx.final_patch
    assert "--- a/file" not in res_ctx.final_patch
    assert res_ctx.receipt_path
    assert file_path.read_text(encoding="utf-8") == "def hello():\n    return True\n"


def test_pipeline_fails_closed_when_repro_does_not_reproduce(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    pipeline = HealPipeline(ollama_generate_fn=lambda system, prompt: "")
    ctx = HealContext(
        instance_id="mock_no_repro",
        repo_dir=tmp_path,
        problem_statement="No physical reproduction",
        max_tries=1,
        repro_script="print('bug not reproduced')\n",
    )
    ctx.localized_files = [("hello.py", file_path.read_text(encoding="utf-8"))]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.runner_completed is True
    assert res_ctx.solve_eligible is False
    assert res_ctx.final_patch == ""
    assert res_ctx.receipt_path
    receipt = json.loads(Path(res_ctx.receipt_path).read_text(encoding="utf-8"))
    assert receipt["reproduced"] is False
    assert receipt["failure_reason"] == "REPRO_NOT_REPRODUCED"


def test_pipeline_classifies_repro_environment_failure(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    pipeline = HealPipeline(ollama_generate_fn=lambda system, prompt: "")
    ctx = HealContext(
        instance_id="mock_repro_env_failure",
        repo_dir=tmp_path,
        problem_statement="Astropy import fails before the issue runs",
        max_tries=1,
        repro_script=(
            "raise ImportError('You appear to be trying to import astropy from within "
            "a source checkout without building the extension modules first')\n"
        ),
    )
    ctx.localized_files = [("hello.py", file_path.read_text(encoding="utf-8"))]

    res_ctx = pipeline.run(ctx)
    receipt = json.loads(Path(res_ctx.receipt_path).read_text(encoding="utf-8"))

    assert res_ctx.solve_eligible is False
    assert res_ctx.failure_reason == "REPRO_ENVIRONMENT_FAILURE"
    assert receipt["failure_reason"] == "REPRO_ENVIRONMENT_FAILURE"


def test_pipeline_retries_reproduction_after_env_denoise(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")
    calls = {"repro": 0, "denoise": 0}
    astropy_failure = (
        "ImportError: You appear to be trying to import astropy from within "
        "a source checkout without building the extension modules first"
    )

    def fake_run_repro(script):
        calls["repro"] += 1
        if calls["repro"] == 1:
            return False, astropy_failure
        return True, "AssertionError: semantic bug reproduced"

    def mock_generate(system, prompt, model=None, timeout=None):
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
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

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_env_denoise_retry",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        auto_heal_enabled=True,
    )
    ctx.localized_files = [("hello.py", file_path.read_text(encoding="utf-8"))]

    class FakeDenoiser:
        def prepare_from_evidence(self, evidence):
            calls["denoise"] += 1

            class Result:
                attempted = True
                succeeded = True
                reason = "ASTROPY_BUILD_EXT_INPLACE"
                commands = ["python3 setup.py build_ext --inplace"]
                output = "built"
                python_executable = sys.executable

                def to_receipt(self):
                    return {
                        "attempted": self.attempted,
                        "succeeded": self.succeeded,
                        "reason": self.reason,
                        "commands": self.commands,
                        "python_executable": self.python_executable,
                    }

            return Result()

    pipeline._make_env_denoiser = lambda repo_dir: FakeDenoiser()
    class FakeRunner:
        python_executable = "python3"
        run_repro = staticmethod(fake_run_repro)
        is_environment_failure = staticmethod(lambda evidence: "source checkout" in evidence)

    fake_runner = FakeRunner()
    pipeline._make_reproduction_runner = lambda repo_dir: fake_runner

    res_ctx = pipeline.run(ctx)
    receipt = json.loads(Path(res_ctx.receipt_path).read_text(encoding="utf-8"))

    assert res_ctx.solve_eligible is True
    assert calls == {"repro": 2, "denoise": 1}
    assert fake_runner.python_executable == sys.executable
    assert receipt["telemetries"]["env_denoise"]["succeeded"] is True
    assert receipt["telemetries"]["env_denoise"]["commands"] == ["python3 setup.py build_ext --inplace"]


def test_pipeline_hidden_verifier_required_fails_closed(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    def mock_generate(system, prompt):
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

    pipeline = HealPipeline(ollama_generate_fn=mock_generate, hidden_verifier=True)
    ctx = HealContext(
        instance_id="mock_hidden_required",
        repo_dir=tmp_path,
        problem_statement="Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.runner_completed is True
    assert res_ctx.solve_eligible is False
    assert res_ctx.final_patch == ""
    assert "hidden verifier" in res_ctx.evaluation_report.lower()


def test_pipeline_records_tsp_model_decisions_for_astropy(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")
    calls = []

    def mock_generate(system, prompt, model=None):
        calls.append(model)
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
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

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_astropy_tsp",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is True
    assert calls[:2] == ["qwen2.5-coder:7b", "qwen2.5-coder:14b"]
    assert [item["phase"] for item in res_ctx.model_decisions[:2]] == ["planning", "patch"]
    assert [item["timeout_seconds"] for item in res_ctx.model_decisions[:2]] == [600, 1200]


def test_pipeline_passes_phase_timeouts_to_model_calls(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")
    calls = []

    def mock_generate(system, prompt, model=None, timeout=None):
        calls.append((model, timeout))
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
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

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_phase_timeouts",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is True
    assert calls[:2] == [("qwen2.5-coder:7b", 600), ("qwen2.5-coder:14b", 1200)]


def test_pipeline_empty_patch_response_records_model_empty_response(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    def mock_generate(system, prompt, model=None, timeout=None):
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
        return ""

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_empty_model_response",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is False
    assert res_ctx.failure_reason == "MODEL_EMPTY_RESPONSE"


def test_pipeline_retry_exhaustion_records_latest_patch_error(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    def mock_generate(system, prompt, model=None, timeout=None):
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
        return "This is an explanation without a patch block."

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_retry_exhaustion_reason",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is False
    assert res_ctx.failure_reason.startswith("NO_BLOCKS_FOUND:")


def test_pipeline_timeout_patch_response_records_model_timeout(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    def mock_generate(system, prompt, model=None, timeout=None):
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
        raise TimeoutError("local model timed out")

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_model_timeout",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is False
    assert res_ctx.failure_reason == "MODEL_TIMEOUT"
    assert res_ctx.model_decisions[-1]["status"] == "MODEL_TIMEOUT"


def test_pipeline_provider_exception_records_model_provider_error(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    def mock_generate(system, prompt, model=None, timeout=None):
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
        raise RuntimeError("connection refused")

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_model_provider_error",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is False
    assert res_ctx.failure_reason == "MODEL_PROVIDER_ERROR"
    assert res_ctx.model_decisions[-1]["status"] == "MODEL_PROVIDER_ERROR"


def test_pipeline_apology_patch_response_records_model_refusal(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    def mock_generate(system, prompt, model=None, timeout=None):
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
        return "I apologize, but I cannot provide a patch for this issue."

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_model_refusal",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=2,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is False
    assert res_ctx.failure_reason == "MODEL_REFUSAL"
    assert res_ctx.model_decisions[-1]["status"] == "MODEL_REFUSAL"


def test_pipeline_planning_timeout_fails_closed_with_model_timeout(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    def mock_generate(system, prompt, model=None, timeout=None):
        if "JSON Output" in prompt:
            raise TimeoutError("planning timed out")
        return ""

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_planning_timeout",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.runner_completed is True
    assert res_ctx.solve_eligible is False
    assert res_ctx.failure_reason == "MODEL_TIMEOUT"
    assert res_ctx.model_decisions[-1]["phase"] == "planning"
    assert res_ctx.model_decisions[-1]["status"] == "MODEL_TIMEOUT"


def test_pipeline_reproduction_generation_timeout_fails_closed_with_model_timeout(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    def mock_generate(system, prompt, model=None, timeout=None):
        raise TimeoutError("reproduction timed out")

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_reproduction_timeout",
        repo_dir=tmp_path,
        problem_statement="No local reproducer available",
        max_tries=1,
    )
    ctx.localized_files = [("hello.py", file_path.read_text(encoding="utf-8"))]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.runner_completed is True
    assert res_ctx.solve_eligible is False
    assert res_ctx.failure_reason == "MODEL_TIMEOUT"
    assert res_ctx.model_decisions[-1]["phase"] == "reproduction"
    assert res_ctx.model_decisions[-1]["status"] == "MODEL_TIMEOUT"


def test_pipeline_localize_query_includes_plan_symbols_and_evidence(tmp_path):
    pipeline = HealPipeline(ollama_generate_fn=lambda system, prompt: "")
    ctx = HealContext(
        instance_id="mock_symbol_localize",
        repo_dir=tmp_path,
        problem_statement="Astropy TimeSeries column deletion bug",
        repro_evidence="ValueError when remove_column touches required columns",
        plan={"search_symbols": ["TimeSeries", "remove_column", "_required_columns"]},
    )
    captured = {}

    def fake_rank_files(issue_description, repo_dir, max_files=3, search_symbols=None):
        captured["rank_query"] = issue_description
        captured["search_symbols"] = search_symbols
        return [(1.0, {"path": "x.py", "content": "def x():\n    pass\n", "file_path": tmp_path / "x.py"})]

    pipeline.localizer.rank_files = fake_rank_files

    def fake_extract_relevant_code(ranked, query=""):
        captured["refine_query"] = query
        return [("x.py", query)]

    pipeline.localizer.extract_relevant_code = fake_extract_relevant_code

    pipeline._localize(ctx)

    assert "TimeSeries" in captured["rank_query"]
    assert "remove_column" in captured["rank_query"]
    assert captured["search_symbols"] == ["TimeSeries", "remove_column", "_required_columns"]
    # 修正：現在 rank_query 會包含 Evidence
    assert "ValueError" in captured["rank_query"]
    assert "ValueError" in captured["refine_query"]
    assert ctx.localized_files[0][1] == captured["refine_query"]


def test_pipeline_routes_reproduction_generation_to_7b(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")
    calls = []

    def mock_generate(system, prompt, model=None):
        calls.append(model)
        if "reproduce" in prompt.lower():
            return "raise AssertionError('bug reproduced')\n"
        return ""

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_repro_model_route",
        repo_dir=tmp_path,
        problem_statement="No local file, generate a reproduce script",
        max_tries=1,
    )
    ctx.localized_files = [("hello.py", file_path.read_text(encoding="utf-8"))]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.runner_completed is True
    assert res_ctx.reproduced is True
    assert calls[0] == "qwen2.5-coder:7b"
    assert res_ctx.model_decisions[0]["phase"] == "reproduction"


def test_pipeline_uses_env_resolved_python_for_reproduction(tmp_path):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")

    class FakeRunner:
        def __init__(self):
            self.python_executable = "python3"
            self.seen_python = []

        def run_repro(self, script):
            self.seen_python.append(self.python_executable)
            return False, "bug not reproduced"

        @staticmethod
        def is_environment_failure(evidence):
            return False

    fake_runner = FakeRunner()
    pipeline = HealPipeline(ollama_generate_fn=lambda system, prompt: "")
    pipeline._make_reproduction_runner = lambda repo_dir: fake_runner
    ctx = HealContext(
        instance_id="mock_env_resolved_python",
        repo_dir=tmp_path,
        problem_statement="No physical reproduction",
        max_tries=1,
        repro_script="print('not reproduced')\n",
        python_executable="/opt/python3.9",
    )
    ctx.localized_files = [("hello.py", file_path.read_text(encoding="utf-8"))]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is False
    assert fake_runner.seen_python == ["/opt/python3.9"]


def test_pipeline_uses_env_resolved_python_for_visible_verification(tmp_path, monkeypatch):
    file_path = tmp_path / "hello.py"
    file_path.write_text("def hello():\n    return False\n", encoding="utf-8")
    visible_cmds = []

    def mock_generate(system, prompt, model=None, timeout=None):
        if "JSON Output" in prompt:
            return '{"search_symbols": ["hello"], "repair_strategy": "rewrite hello", "violated_invariants": []}'
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

    def fake_run_visible_tests(self, test_cmds):
        visible_cmds.extend(test_cmds)
        return [TestResult(test_id=" ".join(test_cmds[0]), passed=True, output="ok")]

    monkeypatch.setattr(
        "nexus.services.local_heal.evaluation_gate.EvaluationGate.run_visible_tests",
        fake_run_visible_tests,
    )

    pipeline = HealPipeline(ollama_generate_fn=mock_generate)
    ctx = HealContext(
        instance_id="mock_env_python_verify",
        repo_dir=tmp_path,
        problem_statement="astropy bug: Change hello to return True",
        max_tries=1,
        repro_script="from pathlib import Path\nassert 'return True' in Path('hello.py').read_text()\n",
        repro_evidence="AssertionError: return True is missing",
        python_executable="/opt/python3.9",
    )
    ctx.localized_files = [("hello.py", "def hello():\n    return False\n")]

    res_ctx = pipeline.run(ctx)

    assert res_ctx.solve_eligible is True
    assert visible_cmds == [["/opt/python3.9", "reproduce_bug.py"]]
