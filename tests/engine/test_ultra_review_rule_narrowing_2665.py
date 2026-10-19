"""#2665: four ultra_review static rules narrowed so benign patterns stop blocking.

P1 test_harness_modified: pyproject.toml / setup.cfg / tox.ini only when their pytest or
   coverage configuration changes between the base ref and the head (parse error = flag).
P2 secret_literal: one whole quoted literal, never across two literals; marker words skipped.
P3 ruff S105-S107: reported at low severity (like bandit B105-B107), so they do not block.
P4 bandit B506 / ruff S506: dropped when yaml.load uses BaseLoader, SafeLoader or CSafeLoader.

Every case goes through the real service (``run`` or the diff scanner), and each
should-flag case is kept next to its should-not-flag twin.
"""

import subprocess

import pytest

from nexus.engine.ultra_review_service import UltraReviewService

_PYPROJECT_BASE = """\
[project]
name = "demo"
version = "0.1.0"
dependencies = ["nexus-runtime @ git+https://example.invalid/runtime@aaaaaaaa"]

[tool.pytest.ini_options]
addopts = "-q"
testpaths = ["tests"]
"""


def _git(path, *args):
    subprocess.run(["git", *args], cwd=path, check=True, capture_output=True)


def _init_repo(path, extra=None):
    _git(path, "init")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test User")
    (path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n", encoding="utf-8"
    )
    for rel, text in (extra or {}).items():
        target = path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    _git(path, "add", ".")
    _git(path, "commit", "-m", "init")


def _review(path, monkeypatch):
    # Static lanes only: the ghost lane is not what these rules are about.
    monkeypatch.setenv("NEXUS_ULTRA_SKIP_GHOST_REGRESSION", "1")
    return UltraReviewService(path).run(
        dry_run=True, report_path="reports/ultra.json", sandbox_root="reports/sandboxes"
    )


def _rules(payload):
    return {f["rule_id"] for f in payload["findings"]}


def _blocking_security(payload):
    return [
        f
        for f in payload["findings"]
        if f.get("lane") == "security_sentry"
        and f.get("state") == "VERIFIED_FINDING"
        and str(f.get("severity")).lower() in {"medium", "high", "critical"}
    ]


# ---------------------------------------------------------------- P1 test harness


def test_2665_pyproject_dependency_pin_change_is_not_harness(tmp_path, monkeypatch):
    # The #2122 / #1908 shape: only the nexus-runtime pin moved; [tool.pytest] is unchanged.
    _init_repo(tmp_path, {"pyproject.toml": _PYPROJECT_BASE})
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_BASE.replace("@aaaaaaaa", "@bbbbbbbb"), encoding="utf-8"
    )

    payload = _review(tmp_path, monkeypatch)

    assert "test_harness_modified" not in _rules(payload)
    assert payload["logic_breaker"]["passed"] is True


def test_2665_pyproject_pytest_addopts_change_is_harness(tmp_path, monkeypatch):
    _init_repo(tmp_path, {"pyproject.toml": _PYPROJECT_BASE})
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_BASE.replace(
            'addopts = "-q"', 'addopts = "-q -p no:cacheprovider --deselect tests"'
        ),
        encoding="utf-8",
    )

    payload = _review(tmp_path, monkeypatch)

    harness = [f for f in payload["findings"] if f["rule_id"] == "test_harness_modified"]
    assert harness and harness[0]["file"] == "pyproject.toml"
    assert payload["logic_breaker"]["passed"] is False


def test_2665_pyproject_new_pytest_table_and_plugin_entry_point_are_harness(tmp_path, monkeypatch):
    _init_repo(tmp_path, {"pyproject.toml": _PYPROJECT_BASE})
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_BASE + '\n[project.entry-points.pytest11]\nshadow = "app"\n', encoding="utf-8"
    )

    assert "test_harness_modified" in _rules(_review(tmp_path, monkeypatch))


def test_2665_pyproject_added_pytest_section_detected_against_base_ref(tmp_path, monkeypatch):
    # Base has no pytest config at all; the head adds [tool.pytest] (a new key under tool.pytest*).
    base = _PYPROJECT_BASE.split("[tool.pytest.ini_options]")[0]
    _init_repo(tmp_path, {"pyproject.toml": base})
    (tmp_path / "pyproject.toml").write_text(
        base + '\n[tool.pytest]\naddopts = ["-x"]\n', encoding="utf-8"
    )

    assert "test_harness_modified" in _rules(_review(tmp_path, monkeypatch))


def test_2665_pyproject_toml_parse_error_fails_closed(tmp_path, monkeypatch):
    _init_repo(tmp_path, {"pyproject.toml": _PYPROJECT_BASE})
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_BASE.replace("@aaaaaaaa", "@bbbbbbbb") + "\n[tool.pytest\nbroken = \n",
        encoding="utf-8",
    )

    assert "test_harness_modified" in _rules(_review(tmp_path, monkeypatch))


def test_2665_pyproject_base_parse_error_fails_closed(tmp_path, monkeypatch):
    _init_repo(tmp_path, {"pyproject.toml": "[project\nname = \n"})
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT_BASE, encoding="utf-8")

    assert "test_harness_modified" in _rules(_review(tmp_path, monkeypatch))


def test_2665_setup_cfg_non_pytest_section_is_not_harness(tmp_path, monkeypatch):
    base = (
        "[metadata]\nname = demo\n\n[tool:pytest]\naddopts = -q\n\n[coverage:run]\nbranch = true\n"
    )
    _init_repo(tmp_path, {"setup.cfg": base})
    (tmp_path / "setup.cfg").write_text(
        base.replace("name = demo", "name = demo2"), encoding="utf-8"
    )

    assert "test_harness_modified" not in _rules(_review(tmp_path, monkeypatch))


@pytest.mark.parametrize(
    "name, base, head",
    [
        ("setup.cfg", "[tool:pytest]\naddopts = -q\n", "[tool:pytest]\naddopts = -q -k nothing\n"),
        ("setup.cfg", "[coverage:run]\nbranch = true\n", "[coverage:run]\nbranch = false\n"),
        ("tox.ini", "[tox]\nenvlist = py\n", "[tox]\nenvlist = py\n\n[pytest]\naddopts = -x\n"),
        ("tox.ini", "[pytest]\naddopts = -q\n", "[pytest\naddopts = -q\n"),  # parse error
    ],
)
def test_2665_setup_cfg_and_tox_pytest_sections_are_harness(
    tmp_path, monkeypatch, name, base, head
):
    _init_repo(tmp_path, {name: base})
    (tmp_path / name).write_text(head, encoding="utf-8")

    assert "test_harness_modified" in _rules(_review(tmp_path, monkeypatch))


def test_2665_tox_ini_env_change_is_not_harness(tmp_path, monkeypatch):
    base = "[tox]\nenvlist = py311\n\n[pytest]\naddopts = -q\n"
    _init_repo(tmp_path, {"tox.ini": base})
    (tmp_path / "tox.ini").write_text(base.replace("py311", "py312"), encoding="utf-8")

    assert "test_harness_modified" not in _rules(_review(tmp_path, monkeypatch))


@pytest.mark.parametrize(
    "name", ["conftest.py", "pytest.ini", "sitecustomize.py", "usercustomize.py"]
)
def test_2665_always_flag_harness_files_stay_flagged(tmp_path, monkeypatch, name):
    _init_repo(tmp_path, {name: "# placeholder\n"})
    (tmp_path / name).write_text("# placeholder changed\n", encoding="utf-8")

    assert "test_harness_modified" in _rules(_review(tmp_path, monkeypatch))


def test_2665_harness_unusable_base_ref_fails_closed(tmp_path, monkeypatch):
    _init_repo(tmp_path, {"pyproject.toml": _PYPROJECT_BASE})
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT_BASE.replace("@aaaaaaaa", "@bbbbbbbb"), encoding="utf-8"
    )
    service = UltraReviewService(tmp_path)
    diff_text = service._capture_diff("HEAD")

    # No base ref, or one that looks like an option, means nothing can be compared: flag.
    for base_ref in ("", "--output=/tmp/x", "no-such-ref"):
        assert service._harness_changes(diff_text, execution_root=tmp_path, base_ref=base_ref) == [
            "pyproject.toml"
        ]
    assert service._harness_changes(diff_text, execution_root=tmp_path, base_ref="HEAD") == []


# ---------------------------------------------------------------- P2 secret_literal


def _scan_line(tmp_path, line):
    diff = (
        "diff --git a/mod.py b/mod.py\n--- a/mod.py\n+++ b/mod.py\n@@ -0,0 +1,1 @@\n+" + line + "\n"
    )
    found = UltraReviewService(tmp_path)._scan_security_observations(diff)
    return [f for f in found if f["rule_id"] == "secret_literal"]


@pytest.mark.parametrize(
    "line",
    [
        # The #2336 regression line: two literals joined by '+', no secret in either.
        '    ("client_secret_eq", "--client-secret=" + _B62_1873, "run {s} ok"),',
        # The #1700 marker word.
        'SECRET = "SECRET_OUT_OF_SCOPE_MARKER"',
        "token = 'NOT_A_REAL_TOKEN'",
        'api_key = "short"',
        'password = "has spaces in it"',
        "token = 'mixed\"quotes12'",
    ],
)
def test_2665_secret_literal_ignores_non_credentials(tmp_path, line):
    assert _scan_line(tmp_path, line) == []


@pytest.mark.parametrize(
    "line",
    [
        "api_key = " + '"sk-' + 'live-AbC123xyz987"',
        "token='ghp" + "_" + "16C7e42F292c6912E7710c838347Ae178B4a'",
        "API" + "_KEY = '123456789abcdef'",
        "db_password = " + '"Tr0ub4dor' + '&3xyz"',
        "client_secret = 'MARKER_ONE', backup_secret = " + "'q8Zr" + "2LmN9vX'",
    ],
)
def test_2665_secret_literal_still_flags_real_looking_secrets(tmp_path, line):
    assert len(_scan_line(tmp_path, line)) == 1


# ---------------------------------------------------------------- P3 ruff S105-S107


def test_2665_hardcoded_password_heuristics_report_low_and_do_not_block(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "def handler(value):\n    return value.strip()\n\n\n"
        'DEFAULT_PASSWORD = "chgme"\n\n\n'
        "def login(user, password='hunter2'):\n    return connect(user, password=\"guest\")\n\n\n"
        "def connect(user, password):\n    return (user, password)\n",
        encoding="utf-8",
    )

    payload = _review(tmp_path, monkeypatch)

    assert payload["security_sentry"]["scanned_python_files"] == ["app.py"]
    password_rules = {
        "ruff:S105",
        "ruff:S106",
        "ruff:S107",
        "bandit:B105",
        "bandit:B106",
        "bandit:B107",
    }
    reported = [f for f in payload["findings"] if f["rule_id"] in password_rules]
    assert reported, "the password heuristics must still be reported"
    assert {str(f["severity"]).lower() for f in reported} == {"low"}
    assert _blocking_security(payload) == []
    assert payload["security_sentry"]["passed"] is True


def test_2665_ruff_only_hardcoded_password_is_low(tmp_path, monkeypatch):
    # An annotated assignment is flagged by ruff S105 but not by bandit B105, so the ruff
    # finding is not folded into a bandit one and its own severity decides (the #535 shape).
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        'def handler(value):\n    return value.strip()\n\n\nclass Settings:\n    secret: str = "abc"\n',
        encoding="utf-8",
    )

    payload = _review(tmp_path, monkeypatch)

    s105 = [f for f in payload["findings"] if f["rule_id"] == "ruff:S105"]
    assert len(s105) == 1 and s105[0]["severity"] == "low"
    assert _blocking_security(payload) == []
    assert payload["security_sentry"]["passed"] is True


def test_2665_other_ruff_security_rules_still_block(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        "import pickle\n\n\ndef handler(value):\n    return pickle.loads(value)\n", encoding="utf-8"
    )

    payload = _review(tmp_path, monkeypatch)

    assert _blocking_security(payload)
    assert payload["security_sentry"]["passed"] is False


# ---------------------------------------------------------------- P4 yaml.load


@pytest.mark.parametrize(
    "source",
    [
        "import yaml\n\n\ndef read(text):\n    return yaml.load(text, Loader=yaml.BaseLoader)\n",
        "import yaml\n\n\ndef read(text):\n    return yaml.load(text, Loader=yaml.SafeLoader)\n",
        "import yaml\n\n\ndef read(text):\n    return yaml.load(text, Loader=yaml.CSafeLoader)\n",
        "import yaml\nfrom yaml import SafeLoader\n\n\ndef read(text):\n"
        "    return yaml.load(\n        text,\n        Loader=SafeLoader,\n    )\n",
    ],
)
def test_2665_yaml_load_with_safe_loader_is_not_flagged(tmp_path, monkeypatch, source):
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text(source, encoding="utf-8")

    payload = _review(tmp_path, monkeypatch)

    # Not vacuous: both tools really scanned the changed file.
    assert payload["security_sentry"]["scanned_python_files"] == ["app.py"]
    assert {"bandit", "ruff-security"} <= set(payload["security_sentry"]["executed_checks"])
    assert not {"bandit:B506", "ruff:S506"} & _rules(payload)
    assert payload["security_sentry"]["passed"] is True


@pytest.mark.parametrize(
    "source",
    [
        "import yaml\n\n\ndef read(text):\n    return yaml.load(text, Loader=yaml.Loader)\n",
        "import yaml\n\n\ndef read(text):\n    return yaml.load(text, Loader=yaml.FullLoader)\n",
        "import yaml\n\n\ndef read(text):\n    return yaml.load(text, Loader=yaml.UnsafeLoader)\n",
        "import yaml\n\n\ndef read(text):\n    return yaml.load(text)\n",
        # A safe-looking name that is really the unsafe loader.
        "import yaml\nfrom yaml import UnsafeLoader as SafeLoader\n\n\ndef read(text):\n"
        "    return yaml.load(text, Loader=SafeLoader)\n",
    ],
)
def test_2665_yaml_load_with_unsafe_or_missing_loader_is_flagged(tmp_path, monkeypatch, source):
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text(source, encoding="utf-8")

    payload = _review(tmp_path, monkeypatch)

    assert {"bandit:B506", "ruff:S506"} & _rules(payload)
    assert payload["security_sentry"]["passed"] is False


# ---------------------------------------------------------------- review follow-ups (#2686)

_STRICT_CFG = (
    "[metadata]\nname = demo\n\n[tool:pytest]\nfilterwarnings = error\nxfail_strict = true\n"
)


@pytest.mark.parametrize(
    "head",
    [
        # pytest's ini keys are case-sensitive: "Filterwarnings" is ignored, strictness is off.
        _STRICT_CFG.replace("filterwarnings", "Filterwarnings"),
        # [DEFAULT] is an ordinary section for pytest: moving keys there drops them.
        "[DEFAULT]\nfilterwarnings = error\nxfail_strict = true\n\n[metadata]\nname = demo\n\n"
        "[tool:pytest]\n",
    ],
)
def test_2665_ini_key_case_change_or_default_move_is_harness(tmp_path, monkeypatch, head):
    _init_repo(tmp_path, {"setup.cfg": _STRICT_CFG})
    (tmp_path / "setup.cfg").write_text(head, encoding="utf-8")

    assert "test_harness_modified" in _rules(_review(tmp_path, monkeypatch))


@pytest.mark.parametrize(
    "head",
    [
        # Case change outside the pytest sections.
        _STRICT_CFG.replace("name = demo", "Name = demo"),
        # A [DEFAULT] section pytest never reads; [tool:pytest] itself is unchanged.
        "[DEFAULT]\nfilterwarnings = ignore\n\n" + _STRICT_CFG,
    ],
)
def test_2665_ini_case_or_default_outside_pytest_is_not_harness(tmp_path, monkeypatch, head):
    _init_repo(tmp_path, {"setup.cfg": _STRICT_CFG})
    (tmp_path / "setup.cfg").write_text(head, encoding="utf-8")

    assert "test_harness_modified" not in _rules(_review(tmp_path, monkeypatch))


@pytest.mark.parametrize("rel", ["tests/pytest.toml", "tests/.pytest.ini", ".pytest.toml"])
def test_2665_new_pytest9_config_file_is_harness(tmp_path, monkeypatch, rel):
    _init_repo(tmp_path)
    target = tmp_path / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    body = (
        '[pytest]\naddopts = ["--deselect", "tests/test_app.py::test_x"]\n'
        if rel.endswith(".toml")
        else "[pytest]\naddopts = --deselect tests/test_app.py::test_x\n"
    )
    target.write_text(body, encoding="utf-8")
    _git(tmp_path, "add", rel)

    payload = _review(tmp_path, monkeypatch)

    assert [f["file"] for f in payload["findings"] if f["rule_id"] == "test_harness_modified"] == [
        rel
    ]


def test_2665_head_identical_to_base_while_diff_changed_fails_closed(tmp_path):
    # The diff says pyproject.toml changed, but the mirror still holds the base bytes (the
    # patch did not land): nothing can be compared, so it is flagged.
    _init_repo(tmp_path, {"pyproject.toml": _PYPROJECT_BASE})
    head = _PYPROJECT_BASE.replace("@aaaaaaaa", "@bbbbbbbb")
    (tmp_path / "pyproject.toml").write_text(head, encoding="utf-8")
    service = UltraReviewService(tmp_path)
    diff_text = service._capture_diff("HEAD")

    stale = tmp_path / "stale_mirror"
    stale.mkdir()
    (stale / "pyproject.toml").write_text(_PYPROJECT_BASE, encoding="utf-8")
    applied = tmp_path / "applied_mirror"
    applied.mkdir()
    (applied / "pyproject.toml").write_text(head, encoding="utf-8")

    assert service._harness_changes(diff_text, execution_root=stale, base_ref="HEAD") == [
        "pyproject.toml"
    ]
    assert service._harness_changes(diff_text, execution_root=applied, base_ref="HEAD") == []


_YAML_HEAD = "import yaml\n\n\ndef read(text):\n"


@pytest.mark.parametrize(
    "source",
    [
        # Two calls on one line, one unsafe.
        _YAML_HEAD
        + "    return yaml.load(text, Loader=yaml.BaseLoader), yaml.load(text, Loader=yaml.Loader)\n",
        # The module's safe loader patched to the unsafe one.
        "import yaml\n\nyaml.BaseLoader = yaml.UnsafeLoader\n\n\ndef read(text):\n"
        "    return yaml.load(text, Loader=yaml.BaseLoader)\n",
        "import yaml\n\nsetattr(yaml, 'BaseLoader', yaml.UnsafeLoader)\n\n\ndef read(text):\n"
        "    return yaml.load(text, Loader=yaml.BaseLoader)\n",
        "import yaml\nfrom evil import *\n\n\ndef read(text):\n"
        "    return yaml.load(text, Loader=BaseLoader)\n",
        "import yaml\n\nglobals()['BaseLoader'] = yaml.UnsafeLoader\n\n\ndef read(text):\n"
        "    return yaml.load(text, Loader=BaseLoader)\n",
    ],
)
def test_2665_yaml_load_rebinding_or_mixed_calls_stay_flagged(tmp_path, monkeypatch, source):
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text(source, encoding="utf-8")

    payload = _review(tmp_path, monkeypatch)

    assert {"bandit:B506", "ruff:S506"} & _rules(payload)
    assert payload["security_sentry"]["passed"] is False


def test_2665_yaml_load_two_safe_calls_on_one_line_not_flagged(tmp_path, monkeypatch):
    _init_repo(tmp_path)
    (tmp_path / "app.py").write_text(
        _YAML_HEAD
        + "    return yaml.load(text, Loader=yaml.BaseLoader), yaml.load(text, Loader=yaml.SafeLoader)\n",
        encoding="utf-8",
    )

    payload = _review(tmp_path, monkeypatch)

    assert payload["security_sentry"]["scanned_python_files"] == ["app.py"]
    assert not {"bandit:B506", "ruff:S506"} & _rules(payload)
