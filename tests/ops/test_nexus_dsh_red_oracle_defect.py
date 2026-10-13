"""#1665: the red receipt binds the failing assertion location and green-gate reports
a different/later assertion failure as RED_ORACLE_DEFECT, failing closed on ambiguity."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ops" / "nexus-dsh-workflow"
guard = SourceFileLoader("nexus_dsh_workflow_oracle_test", str(SCRIPT)).load_module()

TEST_PATH = "tests/test_red.py"
NODE = f"{TEST_PATH}::test_value_is_two"
# First assertion fails for the intended reason at RED; the second one is a wrong
# oracle that RED never executes (value() + 1 can never be 4 once value() == 2).
LATER_WRONG = """from app import value


def test_value_is_two():
    assert value() == 2, "VALUE_NOT_TWO"
    assert value() + 1 == 4, "WRONG_ORACLE"
"""
SOUND = """from app import value


def test_value_is_two():
    assert value() == 2, "VALUE_NOT_TWO"
    assert value() + 1 == 3, "SECOND"
"""
# Each parameter fails at a different line at RED, so no single location binds.
AMBIGUOUS = """import pytest

from app import value


@pytest.mark.parametrize("n", [1, 2])
def test_value_is_two(n):
    if n == 1:
        assert value() == 2, "VALUE_NOT_TWO"
    else:
        assert value() * 2 == 4, "VALUE_NOT_TWO"
    assert value() == 99
"""


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    (path / "tests").mkdir(parents=True)
    (path / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    (path / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (path / "tests" / "conftest.py").write_text(
        "import sys\nfrom pathlib import Path\nsys.path.insert(0, str(Path(__file__).parents[1]))\n",
        encoding="utf-8",
    )
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "t@example.invalid")
    _git(path, "config", "user.name", "t")
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", "base")
    return path


def _run(repo: Path, tmp_path: Path, gate: str, contract: dict, *extra: str) -> tuple[int, dict]:
    contract_path = tmp_path / f"{gate}-contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    cmd = [
        sys.executable,
        str(SCRIPT),
        gate,
        "--repo-root",
        str(repo),
        "--base-revision",
        _git(repo, "rev-parse", "HEAD"),
        "--contract",
        str(contract_path),
        "--python",
        sys.executable,
        "--timeout",
        "120",
        *extra,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    return proc.returncode, json.loads(proc.stdout)


def _red(repo: Path, tmp_path: Path, test_text: str) -> dict:
    (repo / TEST_PATH).write_text(test_text, encoding="utf-8")
    _git(repo, "add", TEST_PATH)
    code, receipt = _run(
        repo,
        tmp_path,
        "red-gate",
        {
            "schema": "nexus.dsh_red_contract.v1",
            "repository": "James3014/Nexus-new",
            "issue_number": 1665,
            "invariant": "value() must be two",
            "test_nodes": [NODE],
            "expected_failure": {"kind": "assertion", "message_regex": "VALUE_NOT_TWO"},
            "forbidden_oracle_literals": [],
            "test_path_globs": ["tests/**"],
        },
    )
    assert code == 0 and receipt["decision"] == "RED_READY", receipt
    return receipt


def _save(tmp_path: Path, receipt: dict) -> Path:
    path = tmp_path / "red-receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    return path


def _rehash(receipt: dict) -> dict:
    body = {k: v for k, v in receipt.items() if k != "receipt_hash"}
    return {**body, "receipt_hash": guard._sha256_bytes(guard._canonical_json(body).encode())}


def _green(repo: Path, tmp_path: Path, app: str, red_receipt: Path | None) -> tuple[int, dict]:
    (repo / "app.py").write_text(app, encoding="utf-8")
    extra = ("--red-receipt", str(red_receipt)) if red_receipt else ()
    return _run(
        repo,
        tmp_path,
        "green-gate",
        {
            "schema": "nexus.dsh_green_contract.v1",
            "repository": "James3014/Nexus-new",
            "issue_number": 1665,
            "target_test_nodes": [NODE],
            "regression_pytest_targets": [],
            "allowed_change_globs": ["app.py", "tests/**"],
            "lint": {"ruff_check_paths_from_changes": False, "ruff_format_preview": False},
        },
        *extra,
    )


FIXED = "def value():\n    return 2\n"
STILL_WRONG = "def value():\n    return 3\n"


def test_red_receipt_binds_failing_assertion_location(repo: Path, tmp_path: Path) -> None:
    receipt = _red(repo, tmp_path, LATER_WRONG)
    sha = "sha256:" + hashlib.sha256(LATER_WRONG.encode()).hexdigest()
    assert receipt["node_results"][0]["assertion_location"] == {
        "status": "BOUND",
        "path": TEST_PATH,
        "line": 5,
        "exception": "AssertionError",
        "path_sha256": sha,
    }


def test_later_wrong_assertion_at_green_is_red_oracle_defect(repo: Path, tmp_path: Path) -> None:
    red = _red(repo, tmp_path, LATER_WRONG)
    code, receipt = _green(repo, tmp_path, FIXED, _save(tmp_path, red))
    assert code != 0
    assert receipt["decision"] == "REVISE_GREEN"
    assert receipt["green_semantics"] is None
    assert receipt["reason_codes"] == ["RED_ORACLE_DEFECT"]
    node = receipt["node_results"][0]
    assert node["oracle_classification"] == "RED_ORACLE_DEFECT"
    assert (node["red_assertion_location"]["path"], node["red_assertion_location"]["line"]) == (
        TEST_PATH,
        5,
    )
    assert (node["assertion_location"]["path"], node["assertion_location"]["line"]) == (
        TEST_PATH,
        6,
    )
    assert receipt["red_oracle"]["status"] == "BOUND"
    assert receipt["red_oracle"]["red_receipt_hash"] == red["receipt_hash"]


def test_same_assertion_failing_at_green_is_implementation_failure(
    repo: Path, tmp_path: Path
) -> None:
    red = _red(repo, tmp_path, LATER_WRONG)
    _code, receipt = _green(repo, tmp_path, STILL_WRONG, _save(tmp_path, red))
    assert receipt["reason_codes"] == ["TARGET_TESTS_NOT_PASSING"]
    node = receipt["node_results"][0]
    assert node["oracle_classification"] == "IMPLEMENTATION_FAILURE"
    assert node["assertion_location"]["line"] == node["red_assertion_location"]["line"] == 5


def test_ordinary_failure_in_production_code_is_implementation_failure(
    repo: Path, tmp_path: Path
) -> None:
    red = _red(repo, tmp_path, SOUND)
    broken = "def value():\n    assert False, 'impl'\n    return 2\n"
    _code, receipt = _green(repo, tmp_path, broken, _save(tmp_path, red))
    assert receipt["reason_codes"] == ["TARGET_TESTS_NOT_PASSING"]
    node = receipt["node_results"][0]
    assert node["assertion_location"]["path"] == "app.py"
    assert node["oracle_classification"] == "IMPLEMENTATION_FAILURE"


def test_red_receipt_without_location_fails_closed(repo: Path, tmp_path: Path) -> None:
    red = _red(repo, tmp_path, LATER_WRONG)
    legacy = dict(red)
    legacy["node_results"] = [
        {k: v for k, v in n.items() if k != "assertion_location"} for n in red["node_results"]
    ]
    _code, receipt = _green(repo, tmp_path, FIXED, _save(tmp_path, _rehash(legacy)))
    assert receipt["reason_codes"] == ["TARGET_TESTS_NOT_PASSING"]
    node = receipt["node_results"][0]
    assert node["oracle_classification"] == "UNCLASSIFIED"
    assert node["oracle_detail"] == "RED_LOCATION_UNAVAILABLE"


def test_ambiguous_red_location_fails_closed(repo: Path, tmp_path: Path) -> None:
    red = _red(repo, tmp_path, AMBIGUOUS)
    assert red["node_results"][0]["assertion_location"]["status"] == "AMBIGUOUS"
    _code, receipt = _green(repo, tmp_path, FIXED, _save(tmp_path, red))
    assert receipt["reason_codes"] == ["TARGET_TESTS_NOT_PASSING"]
    node = receipt["node_results"][0]
    assert node["oracle_classification"] == "UNCLASSIFIED"
    assert node["oracle_detail"] == "RED_LOCATION_AMBIGUOUS"


def test_test_file_edited_after_red_fails_closed(repo: Path, tmp_path: Path) -> None:
    red = _red(repo, tmp_path, LATER_WRONG)
    (repo / TEST_PATH).write_text("\n" + LATER_WRONG, encoding="utf-8")
    _code, receipt = _green(repo, tmp_path, FIXED, _save(tmp_path, red))
    assert receipt["reason_codes"] == ["TARGET_TESTS_NOT_PASSING"]
    assert receipt["node_results"][0]["oracle_detail"] == "RED_LOCATION_FILE_CHANGED"


@pytest.mark.parametrize("mutation", ["tamper", "not_ready", "other_issue"])
def test_unbound_red_receipt_fails_closed(repo: Path, tmp_path: Path, mutation: str) -> None:
    red = _red(repo, tmp_path, SOUND)
    if mutation == "tamper":
        bad = {**red, "issue_number": 1}
    elif mutation == "not_ready":
        bad = _rehash({**red, "decision": "REVISE_RED"})
    else:
        bad = _rehash({**red, "issue_number": 1})
    code, receipt = _green(repo, tmp_path, FIXED, _save(tmp_path, bad))
    assert code != 0
    assert receipt["decision"] == "REVISE_GREEN"
    assert receipt["reason_codes"] == ["RED_RECEIPT_INVALID"]
    assert receipt["red_oracle"]["status"] == "INVALID"


def test_green_ready_with_red_receipt(repo: Path, tmp_path: Path) -> None:
    red = _red(repo, tmp_path, SOUND)
    code, receipt = _green(repo, tmp_path, FIXED, _save(tmp_path, red))
    assert code == 0, receipt
    assert receipt["decision"] == "GREEN_READY"
    assert receipt["node_results"][0]["outcome"] == "passed"
    assert "oracle_classification" not in receipt["node_results"][0]


def test_green_without_red_receipt_is_unchanged(repo: Path, tmp_path: Path) -> None:
    _red(repo, tmp_path, LATER_WRONG)
    _code, receipt = _green(repo, tmp_path, FIXED, None)
    assert receipt["reason_codes"] == ["TARGET_TESTS_NOT_PASSING"]
    assert "red_oracle" not in receipt
    assert set(receipt["node_results"][0]) == {"nodeid", "outcome", "message"}


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("def t():\n>   assert x\nE   assert 0\n\ntests/t.py:7: AssertionError", ("BOUND", 7)),
        ("no location here", ("UNAVAILABLE", None)),
        (
            "tests/t.py:3: KeyError\n\nDuring handling of the above exception, another"
            " exception occurred:\n\ntests/t.py:5: AssertionError",
            ("AMBIGUOUS", None),
        ),
        ("tests/t.py:9: \n_ _ _\n\ntests/h.py:2: AssertionError", ("BOUND", 2)),
    ],
)
def test_crash_location_parsing(text: str, expected: tuple[str, int | None]) -> None:
    location = guard._crash_location(text)
    assert (location["status"], location.get("line")) == expected
