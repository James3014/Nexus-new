from __future__ import annotations

from pathlib import Path

TRUST_SCRIPT = Path("scripts/ops/trusted_deletion_anchor.py")
TEST_PATH = Path("tests/ops/test_trusted_deletion_anchor_dependency_transition.py")
OLD_RUNTIME = "d65e3ea7628a07bd73dee461750392bcdf85c3ac"
NEW_RUNTIME = "b48fbd7abe96041bffcea31fa31fa90e78582f02"

text = TRUST_SCRIPT.read_text(encoding="utf-8")
if text.count(OLD_RUNTIME) != 1:
    raise SystemExit("unexpected trusted Runtime identity count")
text = text.replace(OLD_RUNTIME, NEW_RUNTIME, 1)

pr910 = '''TRUSTED_PR910_DEPENDENCY_SNAPSHOT_TRANSITION: tuple[int, tuple[str, str, str, str]] = (
    910,
    (
        "382f05ca47059a15465515ab704d2d54b8a2a95ae83318b3f98617cd982029c3",
        "5933bdf1497f6d0e852fc26730dd4eec7985d72512e0ff061fc2ab7f59842961",
        "f4f3c2c390804e048d42aa30c447a64af1d079bf2881a93252a38a6674cfcf9f",
        "26e853cd712aaf96b188f4dc9f1e2e8feea3a0d8989fc321a84b28e8b6776b45",
    ),
)
'''
pr960 = '''# Exact one-use, four-way binding for Owner-approved PR #960 (Wave-2 Runtime
# exact-pin adoption after the canonical Runtime merge).
TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION: tuple[int, tuple[str, str, str, str]] = (
    960,
    (
        "f4f3c2c390804e048d42aa30c447a64af1d079bf2881a93252a38a6674cfcf9f",
        "26e853cd712aaf96b188f4dc9f1e2e8feea3a0d8989fc321a84b28e8b6776b45",
        "2c2c1a9d9e2f12736fb3a33efbace9a7b264ca737c00e27ed37696dc5f560c34",
        "ec48fa0ea3dc4403c84d26dcf73a0f18b88292270c4dc519986b06a92835ce35",
    ),
)
'''
if text.count(pr910) != 1:
    raise SystemExit("PR910 transition anchor not unique")
text = text.replace(pr910, pr910 + pr960, 1)

old_records = '''    authorized_transition_records = (
        TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION,
        TRUSTED_PR910_DEPENDENCY_SNAPSHOT_TRANSITION,
    )'''
new_records = '''    authorized_transition_records = (
        TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION,
        TRUSTED_PR910_DEPENDENCY_SNAPSHOT_TRANSITION,
        TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION,
    )'''
if text.count(old_records) != 1:
    raise SystemExit("authorized transition tuple not unique")
text = text.replace(old_records, new_records, 1)
TRUST_SCRIPT.write_text(text, encoding="utf-8")

TEST_PATH.write_text(
    '''from __future__ import annotations

import pytest

from scripts.ops import trusted_deletion_anchor as anchor


def _install_transition_hashes(monkeypatch: pytest.MonkeyPatch) -> None:
    values = iter(anchor.TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION[1])
    monkeypatch.setattr(anchor, "_sha", lambda _value: next(values))


def test_pr960_transition_is_exact_one_use_and_chained_from_pr910(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert anchor.TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION[0] == 960
    assert (
        anchor.TRUSTED_PR960_DEPENDENCY_SNAPSHOT_TRANSITION[1][:2]
        == anchor.TRUSTED_PR910_DEPENDENCY_SNAPSHOT_TRANSITION[1][2:]
    )
    _install_transition_hashes(monkeypatch)
    anchor._validate_trusted_dependency_contract(
        b"trusted-pyproject",
        b"head-pyproject",
        b"trusted-lock",
        b"head-lock",
        pull_request_number=960,
        head_product_init_is_regular=True,
    )


def test_pr960_transition_rejects_reuse_under_another_pr(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_transition_hashes(monkeypatch)
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        anchor._validate_trusted_dependency_contract(
            b"trusted-pyproject",
            b"head-pyproject",
            b"trusted-lock",
            b"head-lock",
            pull_request_number=961,
            head_product_init_is_regular=True,
        )


def test_trusted_runtime_identity_is_wave2_merge() -> None:
    runtime = next(
        record for record in anchor.TRUSTED_EXTERNAL_RUNTIME_PACKAGES if record[0] == "nexus-runtime"
    )
    assert runtime[3] == "b48fbd7abe96041bffcea31fa31fa90e78582f02"
''',
    encoding="utf-8",
)
