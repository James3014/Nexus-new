from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

import scripts.ops.trusted_deletion_anchor as trusted_anchor
import scripts.ops.trusted_merge_lane_gate as lane_gate
from scripts.ops.trusted_deletion_anchor import (
    SCHEMA_VERSION,
    _json,
    build_manifest,
    verify_evidence,
)

ROOT = Path(__file__).parents[2]
WORKFLOW = ROOT / ".github/workflows/trusted-deletion-anchor.yml"


def _package_contract_pyproject(*, packages: str, suffix: str = "") -> bytes:
    return (
        """[project]
name = "fixture"
version = "1"
dependencies = ["trusted==1"]
optional-dependencies = { test = ["pytest==9"] }

[tool.poetry]
name = "fixture"
version = "1"
packages = [
"""
        + packages
        + """
]

[tool.poetry.dependencies]
python = "^3.10"

[tool.poetry.extras]
test = ["pytest"]

[tool.poetry.scripts]
fixture = "fixture:main"

[tool.example]
enabled = true
count = 100

[build-system]
requires = ["poetry-core>=1"]
build-backend = "poetry.core.masonry.api"

[dependency-groups]
dev = ["pytest==9"]
"""
        + suffix
    ).encode()


def test_trusted_external_runtime_package_pair_is_exact() -> None:
    assert trusted_anchor.TRUSTED_EXTERNAL_RUNTIME_PACKAGES == (
        (
            "nexus-learning",
            "nexus_learning",
            "https://github.com/James3014/nexus-learning.git",
            "a48bd876b758069f4dd15c24d0d32f1f2486d319",
        ),
        (
            "nexus-runtime",
            "nexus_runtime",
            "https://github.com/James3014/nexus-runtime.git",
            "e73d152f17d5d06b78da258b62354cca11d6a352",
        ),
    )


@pytest.mark.parametrize(
    "packages",
    [
        '{include = "product"}, {include = "nexus"}, {include = "scripts"}',
        '{include = "nexus"}, {include = "product"}, {include = "scripts"}',
        '{include = "nexus"}, {include = "scripts"}, {include = "product"}',
    ],
)
def test_trusted_package_contract_allows_exact_product_package_only_delta(packages: str) -> None:
    # Historical test id kept (#1929/#821): the product-only delta used to be a
    # built-in fallback; after #2114 retired product from the wheel it is rejected.
    trusted = _package_contract_pyproject(packages='{include = "nexus"}, {include = "scripts"}')
    head = _package_contract_pyproject(packages=packages)

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            trusted,
            head,
            b"version = 1\n",
            b"version = 1\n",
            pull_request_number=1,
            head_product_init_is_regular=True,
        )


@pytest.mark.parametrize("pull_request_number", [1, 2114, 2127])
def test_issue1929_pr821_product_package_readd_requires_exact_transition(
    pull_request_number: int,
) -> None:
    """#1929 Owner decision / #821 retirement: re-adding product is not a free delta."""
    trusted = _package_contract_pyproject(packages='{include = "nexus"}, {include = "scripts"}')
    head = _package_contract_pyproject(
        packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
    )

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            trusted,
            head,
            b"version = 1\n",
            b"version = 1\n",
            pull_request_number=pull_request_number,
            head_product_init_is_regular=True,
        )

    # An unchanged contract still passes, with or without a regular product/__init__.py.
    for product_init_is_regular in (True, False):
        trusted_anchor._validate_trusted_dependency_contract(
            trusted,
            trusted,
            b"version = 1\n",
            b"version = 1\n",
            pull_request_number=pull_request_number,
            head_product_init_is_regular=product_init_is_regular,
        )


def test_trusted_dependency_snapshot_transition_is_four_hash_bound(monkeypatch) -> None:
    trusted_pyproject = b"trusted pyproject\n"
    trusted_lock = b"trusted lock\n"
    head_pyproject = b"open swe pyproject\n"
    head_lock = b"open swe lock\n"
    transition = (
        trusted_anchor._sha(trusted_pyproject),
        trusted_anchor._sha(trusted_lock),
        trusted_anchor._sha(head_pyproject),
        trusted_anchor._sha(head_lock),
    )
    monkeypatch.setattr(trusted_anchor, "TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION", (669, transition))

    trusted_anchor._validate_trusted_dependency_contract(
        trusted_pyproject,
        head_pyproject,
        trusted_lock,
        head_lock,
        pull_request_number=669,
        head_product_init_is_regular=True,
    )

    for index, value in enumerate((trusted_pyproject, trusted_lock, head_pyproject, head_lock)):
        values = [trusted_pyproject, trusted_lock, head_pyproject, head_lock]
        values[index] = value + b"tampered"
        with pytest.raises(
            ValueError,
            match="PR dependency contract drifts from trusted default",
        ):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=669,
                head_product_init_is_regular=True,
            )


@pytest.mark.parametrize("pull_request_number", [1, 668, 670])
def test_trusted_dependency_snapshot_transition_rejects_other_prs(
    monkeypatch, pull_request_number: int
) -> None:
    trusted_pyproject = b"trusted pyproject\n"
    trusted_lock = b"trusted lock\n"
    head_pyproject = b"open swe pyproject\n"
    head_lock = b"open swe lock\n"
    transition = tuple(
        trusted_anchor._sha(value)
        for value in (trusted_pyproject, trusted_lock, head_pyproject, head_lock)
    )
    monkeypatch.setattr(trusted_anchor, "TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION", (669, transition))

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            trusted_pyproject,
            head_pyproject,
            trusted_lock,
            head_lock,
            pull_request_number=pull_request_number,
            head_product_init_is_regular=True,
        )


def test_trusted_dependency_snapshot_transition_preserves_product_file_guard(monkeypatch) -> None:
    values = (
        b"trusted pyproject\n",
        b"trusted lock\n",
        b"open swe pyproject\n",
        b"open swe lock\n",
    )
    transition = tuple(trusted_anchor._sha(value) for value in values)
    monkeypatch.setattr(trusted_anchor, "TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION", (669, transition))

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=669,
            head_product_init_is_regular=False,
        )


def test_open_swe_dependency_snapshot_transition_is_retired_but_preserved_as_history() -> None:
    assert trusted_anchor.RETIRED_TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION == (
        669,
        (
            "c7d84dd5cbc4e533db65445ebb5691296f732d49f2fb39c6028745b18ca1d412",
            "3e753af334885a2f434a94d40fc8860abd151516950e7f1e3647971f2e0dfc51",
            "e52fc5fe9e76fca42299370641169e5ec3d6a59a765774deb1a77f38cd8eb246",
            "cb5ecbb7fcce287f9bcdbb17f65a3b931f13613b6fd1608b428e1c19c5f6965a",
        ),
    )

    _, hashes = trusted_anchor.RETIRED_TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION
    trusted_pyproject = b"trusted pyproject\n"
    trusted_lock = b"trusted lock\n"
    head_pyproject = b"open swe pyproject\n"
    head_lock = b"open swe lock\n"
    assert (
        tuple(
            trusted_anchor._sha(value)
            for value in (trusted_pyproject, trusted_lock, head_pyproject, head_lock)
        )
        != hashes
    )

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            trusted_pyproject,
            head_pyproject,
            trusted_lock,
            head_lock,
            pull_request_number=669,
            head_product_init_is_regular=True,
        )


# Historical #683 exact-base node: retain the exact reverse-transition hashes as
# evidence while proving that no active one-use transition remains authoritative.
def test_open_swe_dependency_snapshot_transition_hashes_are_exact() -> None:
    retired_pr, retired_hashes = trusted_anchor.RETIRED_TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION
    assert retired_pr == 669
    assert (*retired_hashes[2:], *retired_hashes[:2]) == (
        "e52fc5fe9e76fca42299370641169e5ec3d6a59a765774deb1a77f38cd8eb246",
        "cb5ecbb7fcce287f9bcdbb17f65a3b931f13613b6fd1608b428e1c19c5f6965a",
        "c7d84dd5cbc4e533db65445ebb5691296f732d49f2fb39c6028745b18ca1d412",
        "3e753af334885a2f434a94d40fc8860abd151516950e7f1e3647971f2e0dfc51",
    )


def test_core_v1_tg6_dependency_snapshot_transition_hashes_are_exact() -> None:
    # Keep the historical test node stable while advancing the active one-use binding.
    assert trusted_anchor.RETIRED_CORE_V1_TG6_DEPENDENCY_SNAPSHOT_TRANSITION == (
        811,
        (
            "95dc46753fa8d630ad5abcc00f0fc9bfd62e6767a8d943b027a56cddddb74bae",
            "1ca1b7f706c9202ab6cd8df8d86f0051a6769d6fe525c954bdb326971fb65111",
            "261ea0f2a2ffe179615d48acfa02ef89ed617e7970635ce39d70d8bede276b05",
            "5933bdf1497f6d0e852fc26730dd4eec7985d72512e0ff061fc2ab7f59842961",
        ),
    )


def test_core_namespace_retirement_transition_hashes_are_exact() -> None:
    assert trusted_anchor.TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION == (
        833,
        (
            "261ea0f2a2ffe179615d48acfa02ef89ed617e7970635ce39d70d8bede276b05",
            "5933bdf1497f6d0e852fc26730dd4eec7985d72512e0ff061fc2ab7f59842961",
            "382f05ca47059a15465515ab704d2d54b8a2a95ae83318b3f98617cd982029c3",
            "5933bdf1497f6d0e852fc26730dd4eec7985d72512e0ff061fc2ab7f59842961",
        ),
    )


def test_pr910_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR910_DEPENDENCY_SNAPSHOT_TRANSITION == (
        910,
        (
            "382f05ca47059a15465515ab704d2d54b8a2a95ae83318b3f98617cd982029c3",
            "5933bdf1497f6d0e852fc26730dd4eec7985d72512e0ff061fc2ab7f59842961",
            "f4f3c2c390804e048d42aa30c447a64af1d079bf2881a93252a38a6674cfcf9f",
            "26e853cd712aaf96b188f4dc9f1e2e8feea3a0d8989fc321a84b28e8b6776b45",
        ),
    )
    assert trusted_anchor.TRUSTED_DEPENDENCY_SNAPSHOT_TRANSITION[0] == 833


def test_pr1013_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1013_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1013,
        (
            "2c2c1a9d9e2f12736fb3a33efbace9a7b264ca737c00e27ed37696dc5f560c34",
            "ec48fa0ea3dc4403c84d26dcf73a0f18b88292270c4dc519986b06a92835ce35",
            "40012ce8452131f446fce0feb8f508f050a8b0dc875837eac1b623007e7388b8",
            "33543bf4216e10131b08c30951d65bed92ab98bb39e0e9fdde417bdf68a189c0",
        ),
    )


def test_pr1013_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1013_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1013,
        head_product_init_is_regular=True,
    )

    values[3] += b"tampered"
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=1013,
            head_product_init_is_regular=True,
        )


def test_pr1288_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1288_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1288,
        (
            "40012ce8452131f446fce0feb8f508f050a8b0dc875837eac1b623007e7388b8",
            "33543bf4216e10131b08c30951d65bed92ab98bb39e0e9fdde417bdf68a189c0",
            "2fce493ab2843794c1d44665fa68e8292c321fb937e04918795b39b124a99c4e",
            "1defe6b2b7251fd060fb3613bbb9875ec38b4c6ea4dbd8febc36dcb10d1724f1",
        ),
    )


def test_pr1288_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1288_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1288,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1288,
                head_product_init_is_regular=True,
            )

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=1289,
            head_product_init_is_regular=True,
        )


def test_pr1375_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1375_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1375,
        (
            "40012ce8452131f446fce0feb8f508f050a8b0dc875837eac1b623007e7388b8",
            "33543bf4216e10131b08c30951d65bed92ab98bb39e0e9fdde417bdf68a189c0",
            "2fce493ab2843794c1d44665fa68e8292c321fb937e04918795b39b124a99c4e",
            "1defe6b2b7251fd060fb3613bbb9875ec38b4c6ea4dbd8febc36dcb10d1724f1",
        ),
    )


def test_pr1375_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1375_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1375,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1375,
                head_product_init_is_regular=True,
            )

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=1376,
            head_product_init_is_regular=True,
        )


def test_pr1380_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1380_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1380,
        (
            "2fce493ab2843794c1d44665fa68e8292c321fb937e04918795b39b124a99c4e",
            "1defe6b2b7251fd060fb3613bbb9875ec38b4c6ea4dbd8febc36dcb10d1724f1",
            "0ff95ecbe90a66299ff40bc411ddd1045d978d43726729b454e5c1acf8d4a160",
            "6068e086cbdf1e08723520a339269033346ff5a7553d87008cc8e9f1f22260b4",
        ),
    )


def test_pr1380_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1380_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1380,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1380,
                head_product_init_is_regular=True,
            )

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=1381,
            head_product_init_is_regular=True,
        )


def test_pr1507_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1507_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1507,
        (
            "0ff95ecbe90a66299ff40bc411ddd1045d978d43726729b454e5c1acf8d4a160",
            "6068e086cbdf1e08723520a339269033346ff5a7553d87008cc8e9f1f22260b4",
            "10eb27a29cfb60d8cc45e223a68a1221f7f285b04d2b9ab58f1ed2096b11a829",
            "db1bd37456a5d302c0f508ab5ca193750f9d715985f2dcf5e67743a70e9d2667",
        ),
    )


def test_pr1507_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1507_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1507,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1507,
                head_product_init_is_regular=True,
            )

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=1508,
            head_product_init_is_regular=True,
        )


def test_pr1661_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1661_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1661,
        (
            "10eb27a29cfb60d8cc45e223a68a1221f7f285b04d2b9ab58f1ed2096b11a829",
            "db1bd37456a5d302c0f508ab5ca193750f9d715985f2dcf5e67743a70e9d2667",
            "ac96e101471ef46cea2e81af1859b68070fbf89af43ca7c004ecf58c19a7b0e4",
            "dfe0167a759b83769fec605e88bb3186ba3eba36f4b243dffdcded71db4bdc4c",
        ),
    )


def test_pr1661_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1661_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1661,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1661,
                head_product_init_is_regular=True,
            )

    for other_pr in (1660, 1662):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def _pr910_snapshot_fixture(monkeypatch):
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR910_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )
    return values, hashes


def test_pr910_dependency_snapshot_transition_allows_exact_values(monkeypatch) -> None:
    values, _ = _pr910_snapshot_fixture(monkeypatch)
    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=910,
        head_product_init_is_regular=True,
    )


@pytest.mark.parametrize("tampered_index", range(4))
def test_pr910_dependency_snapshot_transition_rejects_each_hash_tamper(
    monkeypatch, tampered_index: int
) -> None:
    values, _ = _pr910_snapshot_fixture(monkeypatch)
    values[tampered_index] += b"tampered"
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=910,
            head_product_init_is_regular=True,
        )


@pytest.mark.parametrize("pull_request_number", [833, 909, 911])
def test_pr910_dependency_snapshot_transition_rejects_other_prs(
    monkeypatch, pull_request_number: int
) -> None:
    values, _ = _pr910_snapshot_fixture(monkeypatch)
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=pull_request_number,
            head_product_init_is_regular=True,
        )


def test_pr910_dependency_snapshot_transition_preserves_product_file_guard(monkeypatch) -> None:
    values, _ = _pr910_snapshot_fixture(monkeypatch)
    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            values[0],
            values[2],
            values[1],
            values[3],
            pull_request_number=910,
            head_product_init_is_regular=False,
        )


@pytest.mark.parametrize(
    ("name", "head", "head_lock", "product_init_is_regular"),
    [
        (
            "dependency drift",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
            ).replace(b"trusted==1", b"hostile==2"),
            b"version = 1\n",
            True,
        ),
        (
            "dependency groups drift",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
            ).replace(b'dev = ["pytest==9"]', b'dev = ["hostile"]'),
            b"version = 1\n",
            True,
        ),
        (
            "build system drift",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
            ).replace(b'requires = ["poetry-core>=1"]', b'requires = ["hostile"]'),
            b"version = 1\n",
            True,
        ),
        (
            "scripts and extras drift",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
            ).replace(b'test = ["pytest"]', b'test = ["hostile"]'),
            b"version = 1\n",
            True,
        ),
        (
            "lock drift",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
            ),
            b"version = 2\n",
            True,
        ),
        (
            "existing package removed",
            _package_contract_pyproject(packages='{include = "nexus"}, {include = "product"}'),
            b"version = 1\n",
            True,
        ),
        (
            "existing package reordered",
            _package_contract_pyproject(
                packages='{include = "scripts"}, {include = "nexus"}, {include = "product"}'
            ),
            b"version = 1\n",
            True,
        ),
        (
            "duplicate product package",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}, {include = "product"}'
            ),
            b"version = 1\n",
            True,
        ),
        (
            "product package extra key",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product", from = "src"}'
            ),
            b"version = 1\n",
            True,
        ),
        (
            "other package added",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "other"}'
            ),
            b"version = 1\n",
            True,
        ),
        (
            "malformed TOML",
            b"[tool.poetry\n",
            b"version = 1\n",
            True,
        ),
        (
            "missing product init",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
            ),
            b"version = 1\n",
            False,
        ),
        (
            "arbitrary metadata drift",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}',
                suffix="\n[tool.hostile]\nvalue = true\n",
            ),
            b"version = 1\n",
            True,
        ),
        (
            "boolean to integer type drift",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
            ).replace(b"enabled = true", b"enabled = 1"),
            b"version = 1\n",
            True,
        ),
        (
            "integer to float type drift",
            _package_contract_pyproject(
                packages='{include = "nexus"}, {include = "scripts"}, {include = "product"}'
            ).replace(b"count = 100", b"count = 100.0"),
            b"version = 1\n",
            True,
        ),
    ],
)
def test_trusted_package_contract_rejects_every_non_allowlisted_delta(
    name: str, head: bytes, head_lock: bytes, product_init_is_regular: bool
) -> None:
    del name
    trusted = _package_contract_pyproject(packages='{include = "nexus"}, {include = "scripts"}')

    with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
        trusted_anchor._validate_trusted_dependency_contract(
            trusted,
            head,
            b"version = 1\n",
            head_lock,
            pull_request_number=1,
            head_product_init_is_regular=product_init_is_regular,
        )


def _workflow() -> dict[str, object]:
    return yaml.safe_load(WORKFLOW.read_text())


def _named_step(job_name: str, step_name: str) -> dict[str, object]:
    workflow = _workflow()
    return next(
        step
        for step in workflow["jobs"][job_name]["steps"]  # type: ignore[index]
        if step.get("name") == step_name
    )


def _event() -> dict[str, object]:
    return {
        "event_name": "pull_request_target",
        "workflow_ref": "James3014/Nexus-new/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main",
        "workflow_sha": "a" * 40,
        "run_id": 1240,
        "repository": {"full_name": "James3014/Nexus-new", "default_branch": "main"},
        "pull_request": {
            "number": 125,
            "base": {"sha": "b" * 40, "ref": "main", "repo": {"full_name": "James3014/Nexus-new"}},
            "head": {"sha": "c" * 40, "repo": {"full_name": "fork/Nexus-new"}},
        },
    }


def _manifest() -> dict[str, object]:
    runtime_identity = {
        "schema_version": trusted_anchor.RUNTIME_SCHEMA_VERSION,
        "runtime_probe": trusted_anchor._runtime_probe(),
        "builder": {"uv_version": trusted_anchor.UV_VERSION},
        "pyproject_sha256": hashlib.sha256(b"").hexdigest(),
        "uv_lock_sha256": hashlib.sha256(b"").hexdigest(),
        "requirements_sha256": hashlib.sha256(b"").hexdigest(),
        "pytest_plugins": trusted_anchor.PYTEST_PLUGINS,
        "dependency_groups": list(trusted_anchor.TRUSTED_RUNTIME_DEPENDENCY_GROUPS),
        "external_packages": [
            {**contract, "direct_url_sha256": "d" * 64}
            for contract in trusted_anchor._trusted_external_package_contract()
        ],
    }
    runtime_metadata = _json(runtime_identity) + b"\n"
    return build_manifest(
        _event(),
        raw_diff=b":100644 100644 abcdef1 abcdef2 M\tfile.py\0",
        test_inventory=["tests/ops/test_pr_impact_gate.py"],
        source_archive=b"trusted archive",
        git_bundle=b"git bundle",
        runtime_metadata=runtime_metadata,
        runtime_identity=runtime_identity,
        merge_base_sha="b" * 40,
    )


def _evidence(manifest: dict[str, object]) -> dict[str, object]:
    golden_report = {
        "schema": "nexus.golden_behavior_eval.v1",
        "source_revision": manifest["head_sha"],
        "source_tree": manifest["head_tree"],
        "root_binding_mode": "explicit_sha_bound",
        "trusted_evaluator_sha256": manifest["golden_evaluator_sha256"],
        "evaluator_identity": manifest["golden_evaluator_sha256"],
        "corpus_identity": manifest["golden_corpus_sha256"],
        "test_corpus_identity": manifest["golden_test_corpus_sha256"],
        "topology_identity": manifest["golden_topology_sha256"],
        "workspace_dirty": False,
        "validation_errors": [],
        "collection_exit_code": 0,
        "pytest_exit_code": 0,
        "case_count": 1,
        "selected_case_count": 1,
        "case_evidence": [
            {
                "case_id": "GB-TEST",
                "status": "covered",
                "witnesses": [
                    {
                        "collection_status": "collected",
                        "execution_status": "passed",
                    }
                ],
            }
        ],
    }
    evidence = {
        "schema_version": SCHEMA_VERSION,
        "status": "COMPLETE",
        "workflow_identity": manifest["workflow_identity"],
        "run_id": manifest["run_id"],
        "base_sha": manifest["base_sha"],
        "head_sha": manifest["head_sha"],
        "merge_base_sha": manifest["merge_base_sha"],
        "base_tree": manifest["base_tree"],
        "head_tree": manifest["head_tree"],
        "test_tree": manifest["test_tree"],
        "bundle_sha256": manifest["bundle_sha256"],
        "raw_diff_sha256": manifest["raw_diff_sha256"],
        "test_inventory_sha256": manifest["test_inventory_sha256"],
        "node_ids": manifest["node_ids"],
        "source_archive_sha256": manifest["source_archive_sha256"],
        "git_bundle_sha256": manifest["git_bundle_sha256"],
        "golden_evaluator_sha256": manifest["golden_evaluator_sha256"],
        "golden_corpus_sha256": manifest["golden_corpus_sha256"],
        "golden_test_corpus_sha256": manifest["golden_test_corpus_sha256"],
        "golden_topology_sha256": manifest["golden_topology_sha256"],
        "golden_report": golden_report,
        "golden_report_sha256": trusted_anchor._sha(trusted_anchor._json(golden_report)),
        "executor": {
            "exit_code": 0,
            "selected_tests": manifest["test_inventory"],
            "pytest_plugins": trusted_anchor.PYTEST_PLUGINS,
            "runtime_probe": manifest["runtime_identity"].get("runtime_probe"),
        },
    }
    for key in (
        "pyproject_sha256",
        "uv_lock_sha256",
        "requirements_sha256",
        "runtime_archive_sha256",
        "runtime_metadata_sha256",
        "runtime_identity",
    ):
        evidence[key] = manifest[key]
    return evidence


def _verify(manifest: dict[str, object], evidence: dict[str, object], **overrides: object) -> str:
    return verify_evidence(
        manifest,
        evidence,
        source_archive=overrides.get("source_archive", b"trusted archive"),
        raw_diff=overrides.get("raw_diff", b":100644 100644 abcdef1 abcdef2 M\tfile.py\0"),
        test_inventory=overrides.get("test_inventory", ["tests/ops/test_pr_impact_gate.py"]),
        git_bundle=overrides.get("git_bundle", b"git bundle"),
        requirements=overrides.get("requirements", b""),
        runtime_archive=overrides.get("runtime_archive", b""),
        runtime_metadata=overrides.get(
            "runtime_metadata", _json(manifest["runtime_identity"]) + b"\n"
        ),
        golden_evaluator=overrides.get("golden_evaluator", b""),
        recomputed_pyproject=overrides.get("pyproject", b""),
        recomputed_uv_lock=overrides.get("uv_lock", b""),
        recomputed_base_tree=overrides.get("base_tree", manifest["base_tree"]),
        recomputed_head_tree=overrides.get("head_tree", manifest["head_tree"]),
        recomputed_test_tree=overrides.get("test_tree", manifest["test_tree"]),
    )


def _run_git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _synthetic_runtime(
    root: Path,
    *,
    pyproject: bytes = b"",
    uv_lock: bytes = b"",
    probe: dict[str, str] | None = None,
    behavioral_pytest: bool = False,
) -> Path:
    runtime_dir = root / "runtime-artifact"
    runtime_dir.mkdir()
    requirements = b"synthetic locked runtime\n"
    test_driver = (
        (
            b"import json,os,sys\n"
            b"from pathlib import Path\n"
            b"args=sys.argv[1:]\n"
            b"if '--collect-only' in args:\n"
            b"  for token in args:\n"
            b"    if '::' in token:\n"
            b"      print(token)\n"
            b"  raise SystemExit\n"
            b"junit=None\n"
            b"for token in args:\n"
            b"  if token.startswith('--junitxml='):\n"
            b"    junit=token.split('=',1)[1]\n"
            b"if junit:\n"
            b"  import xml.etree.ElementTree as ET\n"
            b"  suite=ET.Element('testsuite',{'tests':str(sum(1 for t in args if '::' in t))})\n"
            b"  for token in args:\n"
            b"    if '::' not in token:\n"
            b"      continue\n"
            b"    path,*parts=token.split('::')\n"
            b"    module=path.removesuffix('.py').replace('/','.')\n"
            b"    if len(parts)>1:\n"
            b"      module=module+'.'+'.'.join(parts[:-1])\n"
            b"    name=parts[-1]\n"
            b"    ET.SubElement(suite,'testcase',{'classname':module,'name':name,'time':'0.0'})\n"
            b"  ET.ElementTree(suite).write(junit,encoding='utf-8',xml_declaration=True)\n"
            b"  raise SystemExit\n"
            b"raise SystemExit\n"
        )
        if behavioral_pytest
        else (
            b"import json,sys\n"
            b"import os\n"
            b"from pathlib import Path\n"
            b"Path('.selected-tests.json').write_text(json.dumps(sys.argv[1:]))\n"
            b"Path('.executor-env.json').write_text(json.dumps(sorted(os.environ)))\n"
        )
    )
    files = {
        "site-packages/pytest/__init__.py": b"",
        "site-packages/pytest/__main__.py": test_driver,
        "site-packages/pytest-9.dist-info/METADATA": (
            b"Metadata-Version: 2.1\nName: pytest\nVersion: 9.0.0\n"
        ),
        "site-packages/pytest_asyncio.py": b"",
        "site-packages/pytest_timeout.py": b"",
    }
    external_metadata = []
    for (
        distribution,
        package,
        repository,
        commit,
    ) in trusted_anchor.TRUSTED_EXTERNAL_RUNTIME_PACKAGES:
        external_direct_url = _json({
            "url": repository,
            "vcs_info": {
                "vcs": "git",
                "commit_id": commit,
                "requested_revision": commit,
            },
        })
        files[f"site-packages/{package}/__init__.py"] = b""
        files[f"site-packages/{package}-0.1.0.dist-info/METADATA"] = (
            f"Metadata-Version: 2.1\nName: {distribution}\nVersion: 0.1.0\n".encode()
        )
        files[f"site-packages/{package}-0.1.0.dist-info/direct_url.json"] = external_direct_url
        external_metadata.append({
            "distribution": distribution,
            "package": package,
            "repository": repository,
            "commit": commit,
            "direct_url_sha256": trusted_anchor._sha(external_direct_url),
        })
    stream = BytesIO()
    with tarfile.open(fileobj=stream, mode="w") as archive:
        for name, data in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(data)
            member.mode = 0o644
            archive.addfile(member, BytesIO(data))
    metadata = {
        "schema_version": trusted_anchor.RUNTIME_SCHEMA_VERSION,
        "runtime_probe": probe or trusted_anchor._runtime_probe(),
        "builder": {"uv_version": trusted_anchor.UV_VERSION},
        "pyproject_sha256": hashlib.sha256(pyproject).hexdigest(),
        "uv_lock_sha256": hashlib.sha256(uv_lock).hexdigest(),
        "requirements_sha256": hashlib.sha256(requirements).hexdigest(),
        "pytest_plugins": trusted_anchor.PYTEST_PLUGINS,
        "dependency_groups": list(trusted_anchor.TRUSTED_RUNTIME_DEPENDENCY_GROUPS),
        "external_packages": external_metadata,
    }
    (runtime_dir / "runtime.tar").write_bytes(stream.getvalue())
    (runtime_dir / "runtime-metadata.json").write_bytes(_json(metadata) + b"\n")
    (runtime_dir / "requirements.txt").write_bytes(requirements)
    return runtime_dir


def _trusted_origin(
    root: Path, *, script_object: str = "blob", hostile_head: bool = False
) -> tuple[Path, str, str, Path]:
    source = root / "trusted-source"
    origin = root / "origin.git"
    marker = root / "head-code-executed"
    subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
    _run_git(source, "config", "user.email", "test@example.invalid")
    _run_git(source, "config", "user.name", "trusted-source-test")
    workflow_path = source / ".github/workflows/trusted-deletion-anchor.yml"
    workflow_path.parent.mkdir(parents=True)
    workflow_path.write_text("name: trusted source fixture\n", encoding="utf-8")
    script_path = source / "scripts/ops/trusted_deletion_anchor.py"
    script_path.parent.mkdir(parents=True)
    if script_object == "tree":
        script_path.mkdir()
        (script_path / "payload.py").write_text("raise SystemExit(99)\n", encoding="utf-8")
    else:
        script_path.write_bytes((ROOT / "scripts/ops/trusted_deletion_anchor.py").read_bytes())
        if script_object == "executable":
            script_path.chmod(0o755)
        elif script_object == "symlink":
            script_path.unlink()
            script_path.symlink_to("hostile-target.py")
    lane_gate_path = source / "scripts/ops/trusted_merge_lane_gate.py"
    lane_gate_path.write_bytes((ROOT / "scripts/ops/trusted_merge_lane_gate.py").read_bytes())
    golden_script_path = source / "scripts/ops/trusted_golden_verifier.py"
    golden_script_path.write_bytes((ROOT / "scripts/ops/trusted_golden_verifier.py").read_bytes())
    evaluator_path = source / trusted_anchor.GOLDEN_EVALUATOR_PATH
    evaluator_path.parent.mkdir(parents=True, exist_ok=True)
    evaluator_path.write_bytes((ROOT / trusted_anchor.GOLDEN_EVALUATOR_PATH).read_bytes())
    golden_dir = source / "tests/golden_behavior"
    golden_dir.mkdir(parents=True, exist_ok=True)
    for name in ("corpus.py", "test_corpus.py"):
        (golden_dir / name).write_bytes((ROOT / "tests/golden_behavior" / name).read_bytes())
    test_path = source / "tests/ops/test_pr_impact_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_fixture():\n    assert True\n", encoding="utf-8")
    (source / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (source / "uv.lock").write_text("version = 1\nrevision = 3\n")
    hostile_path = source / "scripts/ops/$(touch hostile-path-executed)"
    hostile_path.write_text("data only\n", encoding="utf-8")
    _run_git(source, "add", ".")
    _run_git(source, "commit", "-m", "trusted workflow source")
    workflow_sha = _run_git(source, "rev-parse", "HEAD")
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    _run_git(source, "remote", "add", "origin", str(origin))
    _run_git(source, "push", "origin", f"{workflow_sha}:refs/heads/main")
    head_sha = workflow_sha
    if hostile_head and script_object == "blob":
        script_path.write_text(
            f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n",
            encoding="utf-8",
        )
        _run_git(source, "commit", "-am", "hostile head code")
        head_sha = _run_git(source, "rev-parse", "HEAD")
        _run_git(source, "push", "origin", f"{head_sha}:refs/heads/hostile-head")
    return origin, workflow_sha, head_sha, marker


def _git_logging_path(root: Path) -> tuple[str, Path]:
    real_git = shutil.which("git")
    assert real_git
    bin_dir = root / "bin"
    bin_dir.mkdir()
    argv_log = root / "git-argv.bin"
    wrapper = bin_dir / "git"
    wrapper.write_text(
        '#!/bin/sh\nprintf "%s\\0" "$@" >> "$ARGV_LOG"\n'
        'if [ "${GIT_CONFIG_COUNT:-}" = 1 ]; then\n'
        '  test "${GIT_CONFIG_KEY_0:-}" = http.extraheader || exit 96\n'
        '  test "${GIT_CONFIG_VALUE_0:-}" = "Authorization: basic $EXPECTED_BASIC" || exit 97\n'
        '  printf "%s\\n" git-basic-ok >> "$AUTH_LOG"\n'
        "fi\n"
        'exec "$REAL_GIT" "$@"\n',
        encoding="utf-8",
    )
    wrapper.chmod(0o755)
    python_wrapper = bin_dir / "python"
    python_wrapper.write_text(
        "#!/bin/sh\n"
        'if [ "${GIT_CONFIG_COUNT:-}" = 1 ]; then\n'
        '  test "${GIT_CONFIG_KEY_0:-}" = http.extraheader || exit 98\n'
        '  test "${GIT_CONFIG_VALUE_0:-}" = "Authorization: basic $EXPECTED_BASIC" || exit 99\n'
        '  printf "%s\\n" python-basic-ok >> "$AUTH_LOG"\n'
        "fi\n"
        'exec "$REAL_PYTHON" "$@"\n',
        encoding="utf-8",
    )
    python_wrapper.chmod(0o755)
    return (
        f"{bin_dir}{os.pathsep}{Path(sys.executable).parent}{os.pathsep}{os.environ['PATH']}",
        argv_log,
    )


def _acquisition_environment(
    run_root: Path, workflow_sha: str, head_sha: str, *, token: str = "token-must-not-be-argv"
) -> dict[str, str]:
    event = _event()
    event["workflow_sha"] = workflow_sha
    event["pull_request"]["base"]["sha"] = workflow_sha  # type: ignore[index]
    event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
    # Legacy PR numbers are no longer exempt by number alone (#1749); carry a
    # genuine Owner-inline DIRECT binding so the lane gate step passes.
    event["pull_request"]["number"] = lane_gate.ENFORCEMENT_START_PR_NUMBER  # type: ignore[index]
    binding = {
        "schema": lane_gate.BINDING_SCHEMA,
        "execution_lane": "DIRECT_CANONICAL",
        "contract_kind": "OWNER_INLINE",
        "owner_id": "James3014",
        "issue_number": None,
        "task_id": None,
        "attempt_id": None,
        "task_card_path": None,
        "task_card_sha256": None,
        "owner_lane_rebind": None,
    }
    binding["binding_hash"] = lane_gate.canonical_hash(binding)
    event["pull_request"]["body"] = lane_gate.render_binding(binding)  # type: ignore[index]
    # OWNER_INLINE is honoured only for an Owner-authored PR.
    event["pull_request"]["user"] = {"login": "James3014", "type": "User"}  # type: ignore[index]
    path, argv_log = _git_logging_path(run_root)
    _synthetic_runtime(
        run_root,
        pyproject=b"[project]\nname='fixture'\nversion='0'\n",
        uv_lock=b"version = 1\nrevision = 3\n",
    )
    token_bytes = f"x-access-token:{token}".encode()
    encoded = base64.b64encode(token_bytes).decode()
    return {
        **os.environ,
        "ARGV_LOG": str(argv_log),
        "REAL_GIT": shutil.which("git") or "git",
        "REAL_PYTHON": sys.executable,
        "PATH": path,
        "RUNNER_TEMP": str(run_root),
        "EVENT_JSON": json.dumps(event),
        "EVENT_NAME": "pull_request_target",
        "WORKFLOW_REF": event["workflow_ref"],
        "WORKFLOW_SHA": workflow_sha,
        "RUN_ID": str(event["run_id"]),
        "REPOSITORY": event["repository"]["full_name"],
        "DEFAULT_BRANCH": event["repository"]["default_branch"],
        "TRUSTED_TOKEN": token,
        "EXPECTED_BASIC": encoded,
        "AUTH_LOG": str(run_root / "auth.log"),
    }


def _local_acquisition_run(job_name: str, origin: Path) -> str:
    step_name = (
        "Acquire and execute exact trusted controller source"
        if job_name == "trusted-controller"
        else "Acquire exact trusted verifier source"
    )
    run = _named_step(job_name, step_name)["run"]
    run = run.replace('"https://github.com/$REPOSITORY.git"', shlex.quote(str(origin)))
    return run.replace(
        'python "$trusted_script" runtime-builder --repo-root "$bare_repo" --workflow-sha "$WORKFLOW_SHA" --uv-executable "$(command -v uv)" --output-dir "$runtime_dir"',
        'cp -R "$RUNNER_TEMP/runtime-artifact" "$runtime_dir"',
    )


def _job_block(text: str, job_name: str, next_job_name: str) -> str:
    start = text.index(f"  {job_name}:\n")
    end = text.index(f"  {next_job_name}:\n", start)
    return text[start:end]


def test_valid_fixed_schema_evidence_is_accepted():
    manifest = _manifest()
    assert _verify(manifest, _evidence(manifest)) == "PASS"


@pytest.mark.parametrize(
    "witnesses",
    [
        ["not-a-mapping"],
        [{"collection_status": "collected", "execution_status": "skipped"}],
        [{"collection_status": "collected", "execution_status": "not_executed"}],
    ],
)
def test_malformed_or_nonexecuted_covered_witness_fails_closed(witnesses: list[object]):
    manifest = _manifest()
    evidence = _evidence(manifest)
    report = evidence["golden_report"]
    assert isinstance(report, dict)
    report["case_evidence"][0]["witnesses"] = witnesses
    evidence["golden_report_sha256"] = trusted_anchor._sha(trusted_anchor._json(report))
    assert _verify(manifest, evidence) == "IMPACT_UNKNOWN"


def test_finding_witness_cannot_claim_skipped_execution():
    manifest = _manifest()
    evidence = _evidence(manifest)
    report = evidence["golden_report"]
    assert isinstance(report, dict)
    report["case_evidence"][0]["status"] = "finding"
    report["case_evidence"][0]["witnesses"][0]["execution_status"] = "skipped"
    evidence["golden_report_sha256"] = trusted_anchor._sha(trusted_anchor._json(report))
    assert _verify(manifest, evidence) == "IMPACT_UNKNOWN"


def test_supplied_trees_cannot_override_immutable_commit_trees():
    manifest = _manifest()
    assert (
        _verify(manifest, _evidence(manifest), base_tree="e" * 40, head_tree="f" * 40)
        == "IMPACT_UNKNOWN"
    )


def test_controller_rejects_missing_exact_tree_before_deriving_artifacts(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(_event()), encoding="utf-8")
    derived_operations: list[str] = []

    def fake_git(repo: Path, *args: str, binary: bool = False) -> str:
        del repo, binary
        if args[:3] == ("fetch", "--no-tags", "--unshallow"):
            return ""
        if args == ("rev-parse", "--is-shallow-repository"):
            return "false"
        if args[0] == "cat-file" and args[-1].endswith("^{commit}"):
            return ""
        if args[0] == "rev-parse" and args[-1].endswith("^{tree}"):
            return "d" * 40
        if args[0] == "cat-file" and args[-1] == f"{'d' * 40}^{{tree}}":
            raise ValueError("missing exact tree")
        if args[0] in {"diff", "archive"}:
            derived_operations.append(args[0])
        raise AssertionError(f"unexpected git invocation: {args!r}")

    monkeypatch.setattr(trusted_anchor, "_git", fake_git)
    with pytest.raises(ValueError, match="missing exact tree"):
        trusted_anchor._controller(
            argparse.Namespace(
                event_json=str(event_path),
                repo_root=str(tmp_path / "repo.git"),
                output_dir=str(tmp_path / "bundle"),
            )
        )
    assert derived_operations == []


@pytest.mark.parametrize("status", ["SKIPPED", "NEUTRAL", "CANCELLED", "MISSING"])
def test_non_complete_status_fails_closed(status: str):
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence["status"] = status
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_tampered_artifact_and_head_drift_fail_closed():
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence["bundle_sha256"] = hashlib.sha256(b"replayed").hexdigest()
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"
    evidence = _evidence(manifest)
    evidence["head_sha"] = "d" * 40
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_malformed_or_token_bearing_evidence_fails_closed():
    manifest = _manifest()
    evidence = _evidence(manifest)
    evidence.pop("workflow_identity")
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"
    evidence = _evidence(manifest)
    evidence["token"] = "ghs_secret"
    assert verify_evidence(manifest, evidence) == "IMPACT_UNKNOWN"


def test_fork_identity_must_be_bound_to_the_event():
    event = _event()
    event["pull_request"]["head"]["sha"] = "not-a-sha"  # type: ignore[index]
    with pytest.raises(ValueError, match="exact SHA"):
        build_manifest(
            event, raw_diff=b"", test_inventory=[], source_archive=b"", merge_base_sha="b" * 40
        )


def test_workflow_substitution_fails_closed():
    event = _event()
    event["workflow_ref"] = (
        "fork/Nexus-new/.github/workflows/trusted-deletion-anchor.yml@refs/heads/main"
    )
    with pytest.raises(ValueError, match="workflow identity"):
        build_manifest(
            event,
            raw_diff=b"",
            test_inventory=["tests/ops/test_pr_impact_gate.py"],
            source_archive=b"",
            merge_base_sha="b" * 40,
        )


def test_recomputed_artifact_digest_rejects_replay():
    manifest = _manifest()
    assert (
        _verify(manifest, _evidence(manifest), source_archive=b"replayed archive")
        == "IMPACT_UNKNOWN"
    )


def test_non_git_isolated_python_reproduces_missing_pytest(tmp_path: Path):
    source = tmp_path / "extracted-source"
    source.mkdir()
    (source / "test_sample.py").write_text("def test_sample():\n    assert True\n")
    non_git_cwd = tmp_path / "non-git-cwd"
    non_git_cwd.mkdir()
    completed = subprocess.run(
        [sys.executable, "-I", "-S", "-m", "pytest", str(source / "test_sample.py")],
        cwd=non_git_cwd,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "No module named pytest" in completed.stderr


def test_extracted_source_without_bootstrap_reproduces_missing_git_head(tmp_path: Path):
    source = tmp_path / "extracted-source"
    source.mkdir()
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=source, capture_output=True, text=True
    )
    assert completed.returncode == 128
    assert "not a git repository" in completed.stderr


@pytest.mark.parametrize(
    ("override", "value"),
    [
        ("requirements", b"tampered requirements"),
        ("runtime_archive", b"tampered runtime"),
        ("runtime_metadata", b'{"tampered":true}'),
        ("pyproject", b"tampered project"),
        ("uv_lock", b"tampered lock"),
    ],
)
def test_runtime_or_dependency_contract_tamper_fails_closed(override: str, value: bytes):
    manifest = _manifest()
    assert _verify(manifest, _evidence(manifest), **{override: value}) == "IMPACT_UNKNOWN"


def test_verifier_does_not_substitute_its_runner_runtime_for_executor_identity(
    monkeypatch: pytest.MonkeyPatch,
):
    manifest = _manifest()
    evidence = _evidence(manifest)
    monkeypatch.setattr(trusted_anchor, "_runtime_probe", lambda: {"different": "verifier"})
    assert _verify(manifest, evidence) == "PASS"


def test_global_conftest_stub_installation_does_not_require_optional_ml_or_legacy_deps(
    tmp_path: Path,
):
    blocker = tmp_path / "sitecustomize.py"
    blocker.write_text(
        "import builtins\n"
        "_real_import = builtins.__import__\n"
        "def _blocked_import(name, globals=None, locals=None, fromlist=(), level=0):\n"
        "    if name.split('.', 1)[0] in {'numpy', 'pandas'}:\n"
        "        raise ModuleNotFoundError(f'blocked optional dependency: {name}')\n"
        "    return _real_import(name, globals, locals, fromlist, level)\n"
        "builtins.__import__ = _blocked_import\n",
        encoding="utf-8",
    )
    environment = os.environ.copy()
    environment["PYTHONPATH"] = os.pathsep.join((str(tmp_path), str(ROOT)))
    completed = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy; runpy.run_path('tests/conftest.py', run_name='__nexus_conftest_probe__')",
        ],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_runtime_builder_uses_frozen_hash_bound_binary_only_contract(tmp_path: Path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "runtime-builder-test")
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (repo / "uv.lock").write_text("version = 1\nrevision = 3\n")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "runtime contract")
    workflow_sha = _run_git(repo, "rev-parse", "HEAD")
    fake_uv = tmp_path / "uv"
    log = tmp_path / "uv.log"
    external_contracts = trusted_anchor._trusted_external_package_contract()
    fake_uv.write_text(
        f"#!{sys.executable}\n"
        "import json,os,sys\n"
        "from pathlib import Path\n"
        "args=sys.argv[1:]\n"
        f"external_specs={external_contracts!r}\n"
        f"with Path({str(log)!r}).open('a') as f: f.write(json.dumps(args)+'\\n')\n"
        "if args == ['--version']:\n print('uv 0.9.2'); raise SystemExit\n"
        "if args[0] == 'export':\n"
        " Path(args[args.index('--output-file')+1]).write_text('pytest==9 --hash=sha256:abc\\n'); raise SystemExit\n"
        "if args[:2] == ['pip','install']:\n"
        " target=Path(args[args.index('--target')+1])\n"
        " if '--requirements' in args:\n"
        "  (target/'pytest').mkdir(parents=True); (target/'pytest/__init__.py').write_text(''); (target/'pytest/__main__.py').write_text('')\n"
        "  (target/'pytest_asyncio.py').write_text(''); (target/'pytest_timeout.py').write_text(''); raise SystemExit\n"
        " spec=next(item for item in external_specs if item['distribution'] in args[-1]); distribution=spec['distribution']; package=spec['package']; repository=spec['repository']; commit=spec['commit']\n"
        " (target/package).mkdir(parents=True); (target/f'{package}/__init__.py').write_text('')\n"
        " info=target/f'{package}-0.1.0.dist-info'; info.mkdir()\n"
        " (info/'METADATA').write_text(f'Metadata-Version: 2.1\\nName: {distribution}\\nVersion: 0.1.0\\n')\n"
        " (info/'direct_url.json').write_text(json.dumps({'url': repository, 'vcs_info': {'vcs': 'git', 'commit_id': commit, 'requested_revision': commit}}, sort_keys=True, separators=(',',':')))\n"
        " raise SystemExit\n"
        "raise SystemExit(2)\n"
    )
    fake_uv.chmod(0o755)
    output = tmp_path / "built-runtime"
    trusted_anchor._build_runtime(
        argparse.Namespace(
            repo_root=str(repo),
            workflow_sha=workflow_sha,
            uv_executable=str(fake_uv),
            output_dir=str(output),
        )
    )
    calls = [json.loads(line) for line in log.read_text().splitlines()]
    export = next(call for call in calls if call and call[0] == "export")
    installs = [call for call in calls if call[:2] == ["pip", "install"]]
    install = next(call for call in installs if "--requirements" in call)
    external_installs = [call for call in installs if "--requirements" not in call]
    assert {
        "--frozen",
        "--no-default-groups",
        "--no-emit-project",
        "--no-emit-workspace",
        "--no-emit-local",
    } <= set(export)
    group_flags = [export[i + 1] for i, token in enumerate(export) if token == "--group"]
    assert group_flags == list(trusted_anchor.TRUSTED_RUNTIME_DEPENDENCY_GROUPS)
    extra_flags = [export[i + 1] for i, token in enumerate(export) if token == "--extra"]
    assert extra_flags == ["legacy"]
    excluded_packages = [
        export[i + 1] for i, token in enumerate(export) if token == "--no-emit-package"
    ]
    assert excluded_packages == [item["distribution"] for item in external_contracts]
    assert {"--require-hashes", "--only-binary", "--no-cache", "--no-python-downloads"} <= set(
        install
    )
    assert len(external_installs) == len(external_contracts)
    assert all(
        {"--no-cache", "--no-deps", "--no-python-downloads"} <= set(call)
        for call in external_installs
    )
    assert {call[-1] for call in external_installs} == {
        f"{item['distribution']} @ git+{item['repository']}@{item['commit']}"
        for item in external_contracts
    }
    assert all((output / name).is_file() for name in trusted_anchor.RUNTIME_FILENAMES)
    metadata = json.loads((output / "runtime-metadata.json").read_text(encoding="utf-8"))
    assert metadata["dependency_groups"] == list(trusted_anchor.TRUSTED_RUNTIME_DEPENDENCY_GROUPS)
    assert [
        {key: item[key] for key in contract}
        for item, contract in zip(metadata["external_packages"], external_contracts, strict=True)
    ] == external_contracts
    assert all(
        isinstance(item["direct_url_sha256"], str) and len(item["direct_url_sha256"]) == 64
        for item in metadata["external_packages"]
    )


def test_runtime_builder_failure_is_bounded_and_redacted(tmp_path: Path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "runtime-builder-test")
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (repo / "uv.lock").write_text("version = 1\nrevision = 3\n")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "runtime contract")
    workflow_sha = _run_git(repo, "rev-parse", "HEAD")
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "from pathlib import Path\n"
        "args=sys.argv[1:]\n"
        "if args and args[0] == 'export':\n"
        " Path(args[args.index('--output-file')+1]).write_text('pytest==9 --hash=sha256:abc\\n')\n"
        " raise SystemExit(0)\n"
        "if args[:2] == ['pip','install'] and '--requirements' in args:\n"
        " sys.stdout.write('Authorization: Bearer ghp_supersecret\\n')\n"
        " sys.stderr.write('https://x-access-token:github_pat_secret@example.invalid/repo ' + ('x' * 5000))\n"
        " raise SystemExit(23)\n"
        "raise SystemExit(2)\n"
    )
    fake_uv.chmod(0o755)

    with pytest.raises(RuntimeError) as exc_info:
        trusted_anchor._build_runtime(
            argparse.Namespace(
                repo_root=str(repo),
                workflow_sha=workflow_sha,
                uv_executable=str(fake_uv),
                output_dir=str(tmp_path / "built-runtime"),
            )
        )

    message = str(exc_info.value)
    assert "stage=locked-binary-install" in message
    assert "exit_code=23" in message
    assert "<truncated>" in message
    assert "<redacted>" in message
    assert "ghp_supersecret" not in message
    assert "github_pat_secret" not in message
    assert len(message) < trusted_anchor.SUBPROCESS_DIAGNOSTIC_LIMIT + 1000


@pytest.mark.parametrize(
    "tampered_groups",
    [
        None,  # missing key
        [],
        ["dev"],
        ["trusted-anchor"],
        ["trusted-anchor", "dev"],  # reordered
        ["dev", "trusted-anchor", "extra"],
        ["dev", "hostile"],
    ],
)
def test_runtime_metadata_dependency_groups_drift_fails_closed(
    tampered_groups: list[str] | None,
) -> None:
    manifest = _manifest()
    metadata = dict(manifest["runtime_identity"])  # type: ignore[arg-type]
    if tampered_groups is None:
        metadata.pop("dependency_groups", None)
    else:
        metadata["dependency_groups"] = tampered_groups
    tampered_metadata = _json(metadata) + b"\n"
    evidence = _evidence(manifest)
    assert _verify(manifest, evidence, runtime_metadata=tampered_metadata) == "IMPACT_UNKNOWN"
    manifest_tampered = dict(manifest)
    manifest_tampered["runtime_identity"] = metadata
    manifest_tampered["runtime_metadata_sha256"] = trusted_anchor._sha(tampered_metadata)
    evidence_tampered = _evidence(manifest_tampered)
    assert (
        _verify(manifest_tampered, evidence_tampered, runtime_metadata=tampered_metadata)
        == "IMPACT_UNKNOWN"
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("repository", "https://github.com/James3014/hostile.git"),
        ("commit", "f" * 40),
        ("distribution", "hostile-learning"),
        ("package", "hostile_learning"),
        ("direct_url_sha256", "f" * 64),
    ],
)
def test_runtime_metadata_external_package_identity_drift_fails_closed(
    field: str, replacement: str
) -> None:
    manifest = _manifest()
    metadata = dict(manifest["runtime_identity"])  # type: ignore[arg-type]
    packages = [dict(item) for item in metadata["external_packages"]]  # type: ignore[index]
    packages[0][field] = replacement
    metadata["external_packages"] = packages
    tampered_metadata = _json(metadata) + b"\n"
    manifest_tampered = dict(manifest)
    manifest_tampered["runtime_identity"] = metadata
    manifest_tampered["runtime_metadata_sha256"] = trusted_anchor._sha(tampered_metadata)
    evidence_tampered = _evidence(manifest_tampered)
    assert (
        _verify(manifest_tampered, evidence_tampered, runtime_metadata=tampered_metadata)
        == "IMPACT_UNKNOWN"
    )


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("repository", "https://github.com/James3014/hostile.git"),
        ("commit", "f" * 40),
        ("distribution", "hostile-runtime"),
        ("package", "hostile_runtime"),
        ("direct_url_sha256", "f" * 64),
    ],
)
def test_runtime_metadata_second_external_package_identity_drift_fails_closed(
    field: str, replacement: str
) -> None:
    manifest = _manifest()
    metadata = dict(manifest["runtime_identity"])  # type: ignore[arg-type]
    packages = [dict(item) for item in metadata["external_packages"]]  # type: ignore[index]
    packages[1][field] = replacement
    metadata["external_packages"] = packages
    tampered_metadata = _json(metadata) + b"\n"
    manifest_tampered = dict(manifest)
    manifest_tampered["runtime_identity"] = metadata
    manifest_tampered["runtime_metadata_sha256"] = trusted_anchor._sha(tampered_metadata)
    assert (
        _verify(manifest_tampered, _evidence(manifest_tampered), runtime_metadata=tampered_metadata)
        == "IMPACT_UNKNOWN"
    )


@pytest.mark.parametrize("mutation", ["missing-learning", "missing-runtime", "unknown-extra"])
def test_runtime_metadata_external_package_list_shape_fails_closed(mutation: str) -> None:
    manifest = _manifest()
    metadata = dict(manifest["runtime_identity"])  # type: ignore[arg-type]
    packages = [dict(item) for item in metadata["external_packages"]]  # type: ignore[index]
    if mutation == "missing-learning":
        packages.pop(0)
    elif mutation == "missing-runtime":
        packages.pop(1)
    else:
        packages.append({**packages[0], "distribution": "unknown-package"})
    metadata["external_packages"] = packages
    tampered_metadata = _json(metadata) + b"\n"
    manifest_tampered = dict(manifest)
    manifest_tampered["runtime_identity"] = metadata
    manifest_tampered["runtime_metadata_sha256"] = trusted_anchor._sha(tampered_metadata)
    assert (
        _verify(
            manifest_tampered,
            _evidence(manifest_tampered),
            runtime_metadata=tampered_metadata,
        )
        == "IMPACT_UNKNOWN"
    )


def test_external_runtime_package_provenance_rejects_wrong_commit(tmp_path: Path) -> None:
    site_packages = tmp_path / "site-packages"
    package = site_packages / "nexus_learning"
    dist_info = site_packages / "nexus_learning-0.1.0.dist-info"
    package.mkdir(parents=True)
    dist_info.mkdir()
    (package / "__init__.py").write_text("", encoding="utf-8")
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: nexus-learning\nVersion: 0.1.0\n", encoding="utf-8"
    )
    contract = trusted_anchor._trusted_external_package_contract()[0]
    (dist_info / "direct_url.json").write_bytes(
        _json({
            "url": contract["repository"],
            "vcs_info": {
                "vcs": "git",
                "commit_id": "f" * 40,
                "requested_revision": contract["commit"],
            },
        })
    )
    with pytest.raises(ValueError, match="provenance mismatch"):
        trusted_anchor._verify_external_runtime_packages(site_packages)


def _write_external_packages(site_packages: Path) -> None:
    for (
        distribution,
        package,
        repository,
        commit,
    ) in trusted_anchor.TRUSTED_EXTERNAL_RUNTIME_PACKAGES:
        package_dir = site_packages / package
        dist_info = site_packages / f"{package}-0.1.0.dist-info"
        package_dir.mkdir(parents=True)
        dist_info.mkdir()
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
        (dist_info / "METADATA").write_text(
            f"Metadata-Version: 2.1\nName: {distribution}\nVersion: 0.1.0\n",
            encoding="utf-8",
        )
        (dist_info / "direct_url.json").write_bytes(
            _json({
                "url": repository,
                "vcs_info": {
                    "vcs": "git",
                    "commit_id": commit,
                    "requested_revision": commit,
                },
            })
        )


@pytest.mark.parametrize(
    "missing_distribution",
    [item[0] for item in trusted_anchor.TRUSTED_EXTERNAL_RUNTIME_PACKAGES],
)
def test_external_runtime_package_provenance_rejects_missing_distribution(
    tmp_path: Path, missing_distribution: str
) -> None:
    site_packages = tmp_path / "site-packages"
    _write_external_packages(site_packages)
    contract = next(
        item
        for item in trusted_anchor.TRUSTED_EXTERNAL_RUNTIME_PACKAGES
        if item[0] == missing_distribution
    )
    import shutil

    shutil.rmtree(site_packages / contract[1])
    with pytest.raises(ValueError, match="install is incomplete"):
        trusted_anchor._verify_external_runtime_packages(site_packages)


@pytest.mark.parametrize(
    "tampered_field", ["repository", "commit_id", "requested_revision", "name"]
)
def test_external_runtime_package_provenance_rejects_metadata_tamper(
    tmp_path: Path, tampered_field: str
) -> None:
    site_packages = tmp_path / "site-packages"
    _write_external_packages(site_packages)
    contract = trusted_anchor._trusted_external_package_contract()[0]
    dist_info = site_packages / f"{contract['package']}-0.1.0.dist-info"
    metadata = json.loads((dist_info / "direct_url.json").read_text(encoding="utf-8"))
    if tampered_field == "name":
        (dist_info / "METADATA").write_text(
            "Metadata-Version: 2.1\nName: hostile\nVersion: 0.1.0\n", encoding="utf-8"
        )
    elif tampered_field == "repository":
        metadata["url"] = "https://github.com/James3014/hostile.git"
    else:
        metadata["vcs_info"][tampered_field] = "f" * 40
    (dist_info / "direct_url.json").write_bytes(_json(metadata))
    with pytest.raises(ValueError):
        trusted_anchor._verify_external_runtime_packages(site_packages)


def test_external_runtime_package_provenance_accepts_exact_pair(tmp_path: Path) -> None:
    site_packages = tmp_path / "site-packages"
    _write_external_packages(site_packages)
    assert len(trusted_anchor._verify_external_runtime_packages(site_packages)) == 2


def test_controller_executor_verifier_path_from_non_repository_cwd():
    with TemporaryDirectory(prefix="trusted-anchor-e2e-") as directory:
        root = Path(directory)
        origin = root / "origin.git"
        checkout = root / "checkout"
        controller_repo = root / "controller.git"
        subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
        subprocess.run(
            ["git", "clone", str(origin), str(checkout)], check=True, capture_output=True
        )
        _run_git(checkout, "config", "user.email", "test@example.invalid")
        _run_git(checkout, "config", "user.name", "trusted-anchor-test")
        test_path = checkout / "tests/ops/test_pr_impact_gate.py"
        test_path.parent.mkdir(parents=True)
        test_path.write_text("def test_anchor_path():\n    assert True\n", encoding="utf-8")
        (checkout / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
        (checkout / "uv.lock").write_text("version = 1\nrevision = 3\n")
        evaluator_path = checkout / trusted_anchor.GOLDEN_EVALUATOR_PATH
        evaluator_path.parent.mkdir(parents=True, exist_ok=True)
        evaluator_path.write_bytes((ROOT / trusted_anchor.GOLDEN_EVALUATOR_PATH).read_bytes())
        golden_dir = checkout / "tests/golden_behavior"
        golden_dir.mkdir(parents=True, exist_ok=True)
        for name in ("corpus.py", "test_corpus.py"):
            (golden_dir / name).write_bytes((ROOT / "tests/golden_behavior" / name).read_bytes())
        from tests.golden_behavior.corpus import CASES

        authority_paths: set[str] = set()
        witness_paths: set[str] = set()
        for case in CASES:
            for source in case.authority_sources:
                if not source.startswith("http"):
                    authority_paths.add(source.split("#", 1)[0].split(":", 1)[0])
            for nodeid in case.automated_tests:
                witness_paths.add(nodeid.split("::", 1)[0])
        for relative in sorted(authority_paths | witness_paths):
            source_file = ROOT / relative
            if not source_file.is_file():
                continue
            target = checkout / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source_file.read_bytes())
        _run_git(checkout, "add", ".")
        _run_git(checkout, "commit", "-m", "base")
        base_sha = _run_git(checkout, "rev-parse", "HEAD")
        test_path.write_text("def test_anchor_path():\n    assert 1 + 1 == 2\n", encoding="utf-8")
        _run_git(checkout, "commit", "-am", "head")
        head_sha = _run_git(checkout, "rev-parse", "HEAD")
        _run_git(checkout, "push", "origin", "HEAD:main")
        controller_completed = subprocess.run(
            ["git", "init", "--bare", str(controller_repo)], check=True, capture_output=True
        )
        _run_git(controller_repo, "remote", "add", "origin", str(origin))
        _run_git(controller_repo, "fetch", "--no-tags", "--depth=1", "origin", base_sha)
        event = _event()
        event["workflow_sha"] = base_sha
        event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
        event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
        event_path = root / "event.json"
        event_path.write_bytes(_json(event))
        bundle = root / "bundle"
        non_repository_cwd = root / "non-repository-cwd"
        non_repository_cwd.mkdir()
        runtime_dir = _synthetic_runtime(
            root,
            pyproject=(checkout / "pyproject.toml").read_bytes(),
            uv_lock=(checkout / "uv.lock").read_bytes(),
            behavioral_pytest=True,
        )
        verifier_script = ROOT / "scripts/ops/trusted_deletion_anchor.py"
        subprocess.run(
            [
                sys.executable,
                str(verifier_script),
                "controller",
                "--event-json",
                str(event_path),
                "--repo-root",
                str(controller_repo),
                "--output-dir",
                str(bundle),
                "--runtime-dir",
                str(runtime_dir),
            ],
            cwd=non_repository_cwd,
            capture_output=True,
            text=True,
        )
        assert controller_completed.returncode == 0, controller_completed.stderr
        manifest = json.loads((bundle / "manifest.json").read_text())
        anchor = json.loads((bundle / "external-anchor.json").read_text())
        assert (bundle / "git-objects.bundle").stat().st_size > 0
        assert (
            anchor["manifest_sha256"]
            == hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
        )
        clone = root / "bundle-clone.git"
        subprocess.run(["git", "init", "--bare", str(clone)], check=True, capture_output=True)
        for ref, revision in (
            ("refs/trusted-anchor/base", base_sha),
            ("refs/trusted-anchor/head", head_sha),
            ("refs/trusted-anchor/workflow", base_sha),
        ):
            _run_git(clone, "fetch", str(bundle / "git-objects.bundle"), f"{ref}:{ref}")
            assert _run_git(clone, "rev-parse", f"{ref}^{{commit}}") == revision
        executor_completed = subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "executor",
                "--bundle-dir",
                str(bundle),
            ],
            capture_output=True,
            text=True,
        )
        assert executor_completed.returncode == 0, executor_completed.stderr
        evidence_path = bundle / "raw-evidence.json"
        assert evidence_path.exists()
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["status"] == "COMPLETE"
        assert evidence["executor"]["exit_code"] == 0
        golden_report = evidence["golden_report"]
        assert golden_report["schema"] == "nexus.golden_behavior_eval.v1"
        assert golden_report["validation_errors"] == []
        assert golden_report["workspace_dirty"] is False
        assert _run_git(bundle / "source", "rev-parse", "HEAD") == head_sha
        assert _run_git(bundle / "source", "rev-parse", "HEAD^") == base_sha
        assert _run_git(bundle / "source", "rev-parse", "HEAD^{tree}") == manifest["head_tree"]
        assert _run_git(bundle / "source", "rev-parse", "HEAD:tests") == _run_git(
            checkout, "rev-parse", f"{head_sha}:tests"
        )
        assert (bundle / "source/tests/ops/test_pr_impact_gate.py").read_text() == (
            "def test_anchor_path():\n    assert 1 + 1 == 2\n"
        )
        expected = [
            "--expected-workflow-ref",
            event["workflow_ref"],
            "--expected-workflow-sha",
            event["workflow_sha"],
            "--expected-run-id",
            str(event["run_id"]),
            "--verify-evidence",
            str(bundle / "raw-evidence.json"),
            "--expected-manifest-sha256",
            anchor["manifest_sha256"],
            "--expected-external-anchor-sha256",
            hashlib.sha256((bundle / "external-anchor.json").read_bytes()).hexdigest(),
            "--expected-event-name",
            event["event_name"],
            "--expected-repository",
            event["repository"]["full_name"],
            "--expected-default-branch",
            event["repository"]["default_branch"],
            "--expected-pull-request-number",
            str(event["pull_request"]["number"]),
            "--expected-base-sha",
            base_sha,
            "--expected-head-sha",
            head_sha,
        ]
        verified = subprocess.run(
            [
                sys.executable,
                str(verifier_script),
                "verifier",
                "--bundle-dir",
                str(bundle),
                *expected,
            ],
            capture_output=True,
            text=True,
            cwd=non_repository_cwd,
        )
        assert verified.returncode == 0, verified.stderr
        assert '"status": "PASS"' in verified.stdout
        original_evidence = evidence_path.read_bytes()
        evidence_tamper = json.loads(original_evidence)
        evidence_tamper["head_tree"] = "0" * 40 if manifest["head_tree"] != "0" * 40 else "1" * 40
        evidence_path.write_bytes(_json(evidence_tamper) + b"\n")
        assert (
            subprocess.run(
                [
                    sys.executable,
                    str(verifier_script),
                    "verifier",
                    "--bundle-dir",
                    str(bundle),
                    *expected,
                ],
                capture_output=True,
                cwd=non_repository_cwd,
            ).returncode
            != 0
        )
        evidence_path.write_bytes(original_evidence)
        tampered = dict(manifest)
        tampered["head_sha"] = "d" * 40
        (bundle / "manifest.json").write_bytes(_json(tampered) + b"\n")
        assert (
            subprocess.run(
                [
                    sys.executable,
                    str(verifier_script),
                    "verifier",
                    "--bundle-dir",
                    str(bundle),
                    *expected,
                ],
                capture_output=True,
                cwd=non_repository_cwd,
            ).returncode
            != 0
        )


def _synthetic_git_bundle(root: Path) -> tuple[bytes, dict[str, object], str, str, str]:
    repo = root / "executor-git-source"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "executor-git-test")
    test_path = repo / "tests/ops/test_pr_impact_gate.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("def test_fixture():\n    assert True\n")
    (repo / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
    (repo / "uv.lock").write_text("version = 1\nrevision = 3\n")
    _run_git(repo, "add", ".")
    _run_git(repo, "commit", "-m", "base")
    base_sha = _run_git(repo, "rev-parse", "HEAD")
    test_path.write_text("def test_archive_bootstrap():\n    assert True\n")
    _run_git(repo, "commit", "-am", "head")
    head_sha = _run_git(repo, "rev-parse", "HEAD")
    for ref, revision in (
        (trusted_anchor.BASE_REF, base_sha),
        (trusted_anchor.HEAD_REF, head_sha),
        (trusted_anchor.WORKFLOW_REF, base_sha),
    ):
        _run_git(repo, "update-ref", ref, revision)
    path = root / "synthetic-git.bundle"
    subprocess.run(
        [
            "git",
            "bundle",
            "create",
            str(path),
            trusted_anchor.BASE_REF,
            trusted_anchor.HEAD_REF,
            trusted_anchor.WORKFLOW_REF,
        ],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    event = _event()
    event["workflow_sha"] = base_sha
    event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
    event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
    return (
        path.read_bytes(),
        event,
        _run_git(repo, "rev-parse", f"{base_sha}^{{tree}}"),
        _run_git(repo, "rev-parse", f"{head_sha}^{{tree}}"),
        _run_git(repo, "rev-parse", f"{head_sha}:tests"),
    )


def _executor_archive_bundle(
    root: Path, unsafe_member: tarfile.TarInfo, *, runtime_probe: dict[str, str] | None = None
) -> Path:
    bundle = root / "bundle"
    bundle.mkdir()
    test_name = "tests/ops/test_pr_impact_gate.py"
    test_data = b"def test_archive_bootstrap():\n    assert True\n"
    with tarfile.open(bundle / "source.tar", "w") as archive:
        test_member = tarfile.TarInfo(test_name)
        test_member.size = len(test_data)
        archive.addfile(test_member, fileobj=BytesIO(test_data))
        unsafe_data = BytesIO(b"x" * unsafe_member.size) if unsafe_member.isreg() else None
        archive.addfile(unsafe_member, fileobj=unsafe_data)
    runtime_dir = _synthetic_runtime(root, probe=runtime_probe)
    requirements = (runtime_dir / "requirements.txt").read_bytes()
    runtime_archive = (runtime_dir / "runtime.tar").read_bytes()
    runtime_metadata = (runtime_dir / "runtime-metadata.json").read_bytes()
    git_bundle, event, base_tree, head_tree, test_tree = _synthetic_git_bundle(root)
    manifest = build_manifest(
        event,
        raw_diff=b"",
        test_inventory=[test_name],
        source_archive=(bundle / "source.tar").read_bytes(),
        git_bundle=git_bundle,
        requirements=requirements,
        runtime_archive=runtime_archive,
        runtime_metadata=runtime_metadata,
        runtime_identity=json.loads(runtime_metadata),
        base_tree=base_tree,
        head_tree=head_tree,
        test_tree=test_tree,
        merge_base_sha=event["pull_request"]["base"]["sha"],  # type: ignore[index]
    )
    (bundle / "git-objects.bundle").write_bytes(git_bundle)
    for name in trusted_anchor.RUNTIME_FILENAMES:
        (bundle / name).write_bytes((runtime_dir / name).read_bytes())
    (bundle / "manifest.json").write_bytes(_json(manifest))
    evaluator = ROOT / trusted_anchor.GOLDEN_EVALUATOR_PATH
    (bundle / "run_golden_behavior_eval.py").write_bytes(evaluator.read_bytes())
    manifest["golden_evaluator_sha256"] = hashlib.sha256(evaluator.read_bytes()).hexdigest()
    # Rebuild the signed bundle identity after adding the trusted evaluator.
    unsigned = dict(manifest)
    unsigned.pop("bundle_sha256", None)
    manifest["bundle_sha256"] = trusted_anchor._sha(
        trusted_anchor._json(unsigned)
        + (bundle / "source.tar").read_bytes()
        + b""
        + trusted_anchor._json([test_name])
        + git_bundle
        + requirements
        + runtime_archive
        + (runtime_dir / "runtime-metadata.json").read_bytes()
        + evaluator.read_bytes()
    )
    (bundle / "manifest.json").write_bytes(_json(manifest))
    return bundle


def test_missing_runtime_artifact_cannot_emit_complete_evidence(tmp_path: Path):
    link = tarfile.TarInfo(".antigravitycli/irrelevant.json")
    link.type = tarfile.SYMTYPE
    link.linkname = "/tmp/ignored"
    bundle = _executor_archive_bundle(tmp_path, link)
    (bundle / "runtime.tar").unlink()
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (bundle / "raw-evidence.json").exists()


def test_executor_rejects_runtime_abi_mismatch(tmp_path: Path):
    probe = trusted_anchor._runtime_probe()
    probe["soabi"] = "incompatible-abi"
    link = tarfile.TarInfo(".antigravitycli/irrelevant.json")
    link.type = tarfile.SYMTYPE
    link.linkname = "/tmp/ignored"
    bundle = _executor_archive_bundle(tmp_path, link, runtime_probe=probe)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert "offline runtime identity mismatch" in completed.stderr
    assert not (bundle / "raw-evidence.json").exists()


@pytest.mark.parametrize(
    "tamper",
    [
        "git-digest",
        "malformed-bound-git",
        "substituted-base",
        "substituted-head",
        "substituted-workflow",
        "wrong-tree",
        "wrong-test-tree",
        "bound-source-test-drift",
        "source-digest",
    ],
)
def test_executor_git_context_tamper_fails_closed(tamper: str, tmp_path: Path):
    link = tarfile.TarInfo(".antigravitycli/irrelevant.json")
    link.type = tarfile.SYMTYPE
    link.linkname = "/tmp/ignored"
    bundle = _executor_archive_bundle(tmp_path, link)
    manifest_path = bundle / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if tamper == "git-digest":
        (bundle / "git-objects.bundle").write_bytes(
            (bundle / "git-objects.bundle").read_bytes() + b"tamper"
        )
    elif tamper == "malformed-bound-git":
        malformed = b"not a Git bundle"
        (bundle / "git-objects.bundle").write_bytes(malformed)
        manifest["git_bundle_sha256"] = hashlib.sha256(malformed).hexdigest()
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "substituted-head":
        manifest["head_sha"] = "f" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "substituted-base":
        manifest["base_sha"] = "f" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "substituted-workflow":
        manifest["workflow_identity"]["workflow_sha"] = "f" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "wrong-tree":
        manifest["head_tree"] = "0" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "wrong-test-tree":
        manifest["test_tree"] = "0" * 40
        manifest_path.write_bytes(_json(manifest))
    elif tamper == "bound-source-test-drift":
        original = tarfile.open(bundle / "source.tar")
        stream = BytesIO()
        with original, tarfile.open(fileobj=stream, mode="w") as rewritten:
            for member in original.getmembers():
                payload = original.extractfile(member) if member.isfile() else None
                if member.name == "tests/ops/test_pr_impact_gate.py":
                    data = b"def test_tampered():\n    assert True\n"
                    member.size = len(data)
                    payload = BytesIO(data)
                rewritten.addfile(member, payload)
        archive = stream.getvalue()
        (bundle / "source.tar").write_bytes(archive)
        manifest["source_archive_sha256"] = hashlib.sha256(archive).hexdigest()
        manifest_path.write_bytes(_json(manifest))
    else:
        (bundle / "source.tar").write_bytes((bundle / "source.tar").read_bytes() + b"tamper")
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (bundle / "raw-evidence.json").exists()


@pytest.mark.parametrize("target", ["/tmp/issue104-absolute-link", "../../issue104-outside-link"])
def test_executor_skips_only_external_links_and_runs_safe_tests(target: str, tmp_path: Path):
    link = tarfile.TarInfo(".antigravitycli/irrelevant.json")
    link.type = tarfile.SYMTYPE
    link.linkname = target
    bundle = _executor_archive_bundle(tmp_path, link)
    source = bundle / "source"
    non_git_cwd = tmp_path / "non-git-cwd"
    non_git_cwd.mkdir()
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=non_git_cwd,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert (source / "tests/ops/test_pr_impact_gate.py").is_file()
    assert not (source / ".antigravitycli").exists()
    assert "canonical Golden report is missing" in completed.stderr
    assert not (bundle / "raw-evidence.json").exists()


@pytest.mark.parametrize("member_type", ["outside-path", "device"])
def test_executor_keeps_other_unsafe_archive_forms_fail_closed(member_type: str, tmp_path: Path):
    member = tarfile.TarInfo("../outside.txt" if member_type == "outside-path" else "device")
    if member_type == "outside-path":
        member.size = len(b"must not extract")
    else:
        member.type = tarfile.CHRTYPE
        member.devmajor = 1
        member.devminor = 3
    bundle = _executor_archive_bundle(tmp_path, member)
    completed = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ops/trusted_deletion_anchor.py"),
            "executor",
            "--bundle-dir",
            str(bundle),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (bundle / "outside.txt").exists()
    assert not (bundle / "source" / "device").exists()


def test_controller_repairs_shallow_merge_head_for_full_history_bundle():
    with TemporaryDirectory(prefix="trusted-anchor-shallow-merge-") as directory:
        root = Path(directory)
        source = root / "source"
        origin = root / "origin.git"
        controller_repo = root / "controller.git"
        verifier_repo = root / "verifier.git"
        subprocess.run(["git", "init", str(source)], check=True, capture_output=True)
        _run_git(source, "config", "user.email", "test@example.invalid")
        _run_git(source, "config", "user.name", "trusted-anchor-shallow-test")
        test_path = source / "tests/ops/test_pr_impact_gate.py"
        test_path.parent.mkdir(parents=True)
        test_path.write_text("def test_anchor_path():\n    assert True\n", encoding="utf-8")
        (source / "pyproject.toml").write_text("[project]\nname='fixture'\nversion='0'\n")
        (source / "uv.lock").write_text("version = 1\nrevision = 3\n")
        evaluator_path = source / trusted_anchor.GOLDEN_EVALUATOR_PATH
        evaluator_path.parent.mkdir(parents=True, exist_ok=True)
        evaluator_path.write_bytes((ROOT / trusted_anchor.GOLDEN_EVALUATOR_PATH).read_bytes())
        golden_dir = source / "tests/golden_behavior"
        golden_dir.mkdir(parents=True, exist_ok=True)
        for name in ("corpus.py", "test_corpus.py"):
            (golden_dir / name).write_bytes((ROOT / "tests/golden_behavior" / name).read_bytes())
        _run_git(source, "add", ".")
        _run_git(source, "commit", "-m", "base")
        base_sha = _run_git(source, "rev-parse", "HEAD")
        subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
        _run_git(source, "remote", "add", "origin", str(origin))
        _run_git(source, "push", "origin", f"{base_sha}:refs/heads/main")

        _run_git(source, "switch", "-c", "feature")
        (source / "feature.txt").write_text("feature\n", encoding="utf-8")
        _run_git(source, "add", "feature.txt")
        _run_git(source, "commit", "-m", "feature")
        feature_sha = _run_git(source, "rev-parse", "HEAD")
        _run_git(source, "switch", "main")
        _run_git(source, "merge", "--no-ff", feature_sha, "-m", "merge head")
        head_sha = _run_git(source, "rev-parse", "HEAD")
        _run_git(source, "push", "origin", f"{head_sha}:refs/heads/merge-head")

        subprocess.run(
            ["git", "init", "--bare", str(controller_repo)], check=True, capture_output=True
        )
        _run_git(controller_repo, "remote", "add", "origin", str(origin))
        subprocess.run(
            [
                "git",
                "-C",
                str(controller_repo),
                "fetch",
                "--no-tags",
                "--depth=1",
                "origin",
                base_sha,
            ],
            check=True,
            capture_output=True,
        )
        assert _run_git(controller_repo, "rev-parse", "--is-shallow-repository") == "true"
        missing_merge_parent = subprocess.run(
            [
                "git",
                "-C",
                str(controller_repo),
                "cat-file",
                "-e",
                f"{feature_sha}^{{commit}}",
            ],
            capture_output=True,
        )
        assert missing_merge_parent.returncode != 0

        event = _event()
        event["workflow_sha"] = base_sha
        event["pull_request"]["base"]["sha"] = base_sha  # type: ignore[index]
        event["pull_request"]["head"]["sha"] = head_sha  # type: ignore[index]
        event_path = root / "event.json"
        event_path.write_bytes(_json(event))
        bundle = root / "bundle"
        runtime_dir = _synthetic_runtime(
            root,
            pyproject=(source / "pyproject.toml").read_bytes(),
            uv_lock=(source / "uv.lock").read_bytes(),
        )
        subprocess.run(
            [
                sys.executable,
                "scripts/ops/trusted_deletion_anchor.py",
                "controller",
                "--event-json",
                str(event_path),
                "--repo-root",
                str(controller_repo),
                "--output-dir",
                str(bundle),
                "--runtime-dir",
                str(runtime_dir),
            ],
            check=True,
        )
        assert _run_git(controller_repo, "rev-parse", "--is-shallow-repository") == "false"
        assert _run_git(controller_repo, "cat-file", "-e", f"{base_sha}^{{commit}}") == ""
        assert _run_git(controller_repo, "cat-file", "-e", f"{head_sha}^{{commit}}") == ""
        subprocess.run(
            ["git", "init", "--bare", str(verifier_repo)], check=True, capture_output=True
        )
        for ref, revision in (
            ("refs/trusted-anchor/base", base_sha),
            ("refs/trusted-anchor/head", head_sha),
            ("refs/trusted-anchor/workflow", base_sha),
        ):
            _run_git(verifier_repo, "fetch", str(bundle / "git-objects.bundle"), f"{ref}:{ref}")
            assert _run_git(verifier_repo, "rev-parse", f"{ref}^{{commit}}") == revision
            assert _run_git(verifier_repo, "rev-parse", f"{ref}^{{tree}}") == _run_git(
                controller_repo, "rev-parse", f"{revision}^{{tree}}"
            )
        head_with_parents = next(
            line
            for line in _run_git(
                verifier_repo, "rev-list", "--parents", "refs/trusted-anchor/head"
            ).splitlines()
            if line.startswith(head_sha)
        ).split()
        assert head_with_parents[0] == head_sha
        assert set(head_with_parents[1:]) == {base_sha, feature_sha}
        _run_git(verifier_repo, "merge-base", "--is-ancestor", base_sha, head_sha)


def test_workflow_is_three_job_isolated_anchor():
    workflow = _workflow()
    trigger = workflow.get("on", workflow.get(True))
    assert "pull_request_target" in trigger
    assert workflow["permissions"] == {}
    assert set(workflow["jobs"]) == {
        "trusted-controller",
        "unprivileged-executor",
        "trusted-verifier",
    }
    assert workflow["jobs"]["unprivileged-executor"]["permissions"] == {}
    assert workflow["jobs"]["trusted-controller"]["permissions"] == {"contents": "read"}
    assert workflow["jobs"]["trusted-verifier"]["permissions"] == {
        "contents": "read",
        "actions": "read",
    }
    assert {job["runs-on"] for job in workflow["jobs"].values()} == {"ubuntu-24.04"}
    runtime_builder = _named_step("trusted-controller", "Acquire fixed trusted runtime builder")
    assert runtime_builder["uses"] == "astral-sh/setup-uv@d0d8abe699bfb85fec6de9f7adb5ae17292296ff"
    assert runtime_builder["with"] == {"version": "0.9.2", "enable-cache": False}
    artifact_actions = (
        "actions/upload-artifact@",
        "actions/download-artifact@",
    )
    for job in workflow["jobs"].values():
        for step in job["steps"]:
            assert "actions/checkout@" not in step.get("uses", "")
            if step.get("uses", "").startswith(artifact_actions):
                pin = step["uses"].split("@", 1)[1].split()[0]
                assert re.fullmatch(r"[0-9a-f]{40}", pin)
    assert "--verify-evidence" in next(
        step["run"]
        for step in workflow["jobs"]["trusted-verifier"]["steps"]
        if step.get("name") == "Verify fixed schema and recomputed digests"
    )
    assert (
        "runtime-builder"
        in _named_step("trusted-controller", "Acquire and execute exact trusted controller source")[
            "run"
        ]
    )


def test_executor_workflow_has_no_runtime_provisioning_or_authority():
    workflow = _workflow()
    executor = workflow["jobs"]["unprivileged-executor"]
    assert executor["runs-on"] == "ubuntu-24.04"
    assert executor["permissions"] == {}
    text = json.dumps(executor).lower()
    for forbidden in (
        "setup-python",
        "setup-uv",
        "pip install",
        "uv sync",
        "actions/cache",
        "github.token",
        "secrets",
    ):
        assert forbidden not in text


def test_trusted_jobs_use_bare_exact_sha_and_allowlisted_regular_blob():
    text = WORKFLOW.read_text()
    assert "git init --bare" in text
    assert 'fetch --no-tags --depth=1 origin "$WORKFLOW_SHA"' in text
    assert 'rev-parse "$WORKFLOW_SHA^{commit}"' in text
    assert 'cat-file commit "$WORKFLOW_SHA"' in text
    assert 'ls-tree "$WORKFLOW_SHA"' in text
    assert "100644 blob" in text
    assert 'cat-file blob "$WORKFLOW_SHA:$script_path"' in text
    assert "trusted-source.receipt" in text
    assert "sha256=" in text
    assert '--repo-root "$bare_repo"' in text
    assert "actions/checkout" not in text
    assert "git checkout" not in text
    assert "git worktree" not in text
    assert "git submodule" not in text


def test_trusted_source_identity_and_token_isolation_are_fail_closed():
    workflow = _workflow()
    text = WORKFLOW.read_text().lower()
    assert "https://github.com/$repository.git" in text
    assert "git_config_key_0=http.extraheader" in text
    assert 'git_config_value_0="authorization: basic $basic_auth"' in text
    assert text.count("printf 'x-access-token:%s' \"$trusted_token\" | base64 | tr -d '\\n'") == 2
    assert 'test -n "$basic_auth"' in text
    assert "tr -cd '\\n'" in text
    assert "authorization: bearer" not in text
    assert "persist-credentials" not in text
    assert "credential.helper" not in text
    assert "github.token" in text
    assert "permissions: {}" in text
    assert not re.search(r"\bgit\b[^\n]*\s-c\s[^\n]*\$trusted_token", text)
    assert not re.search(r"\bgit\b[^\n]*(?:authorization|token)[^\n]*\$trusted_token", text)
    assert "env git" not in text
    assert "env python" not in text
    for job_name in ("trusted-controller", "trusted-verifier"):
        steps = workflow["jobs"][job_name]["steps"]
        cleanup = [step for step in steps if step.get("if") == "always()"]
        assert cleanup and steps[-1] is cleanup[-1]
        cleanup_lines = [line.strip() for line in cleanup[-1]["run"].splitlines()]
        remove_index = next(
            index for index, line in enumerate(cleanup_lines) if line.startswith("rm -rf")
        )
        prove_indexes = [
            index for index, line in enumerate(cleanup_lines) if line.startswith("test ! -e")
        ]
        assert prove_indexes and remove_index < min(prove_indexes)
        acquisition = _named_step(
            job_name,
            "Acquire and execute exact trusted controller source"
            if job_name == "trusted-controller"
            else "Acquire exact trusted verifier source",
        )["run"]
        assert "trap cleanup_on_exit EXIT" in acquisition
        assert "trap 'exit 130' INT" in acquisition
        assert "trap 'exit 143' TERM" in acquisition
    executor = str(workflow["jobs"]["unprivileged-executor"]).lower()
    assert "secrets" not in executor
    assert "cache" not in executor
    assert "token" not in executor


@pytest.mark.parametrize("job_name", ["trusted-controller", "trusted-verifier"])
def test_cleanup_shell_deletes_lock_and_credential_residue_before_proving_absence(
    job_name: str, tmp_path: Path
):
    prefix = "trusted-controller" if job_name == "trusted-controller" else "trusted-verifier"
    bare_repo = tmp_path / f"{prefix}.git"
    trusted_dir = tmp_path / f"{prefix}-source"
    bare_repo.mkdir()
    trusted_dir.mkdir()
    (bare_repo / "config.lock").write_text("stale lock\n")
    (bare_repo / "config").write_text("http.extraheader=Authorization: bearer secret\n")
    (trusted_dir / "token-file").write_text("ghs_secret\n")
    cleanup = _named_step(
        job_name,
        f"Cleanup trusted {'controller' if job_name == 'trusted-controller' else 'verifier'} source",
    )
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", cleanup["run"]],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not bare_repo.exists()
    assert not trusted_dir.exists()


def test_executor_cleanup_removes_only_extracted_material(tmp_path: Path):
    bundle = tmp_path / "trusted-anchor"
    (bundle / "source").mkdir(parents=True)
    (bundle / "runtime").mkdir()
    evidence = bundle / "raw-evidence.json"
    evidence.write_text('{"status":"COMPLETE"}\n')
    cleanup = _named_step("unprivileged-executor", "Cleanup unprivileged executor material")
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", cleanup["run"]],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path)},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not (bundle / "source").exists()
    assert not (bundle / "runtime").exists()
    assert evidence.is_file()


@pytest.mark.parametrize("job_name", ["trusted-controller", "trusted-verifier"])
def test_no_checkout_acquisition_shell_executes_only_exact_trusted_blob(
    job_name: str, tmp_path: Path
):
    origin, workflow_sha, head_sha, marker = _trusted_origin(tmp_path, hostile_head=True)
    run_root = tmp_path / f"run-{job_name}"
    run_root.mkdir()
    token = "token-must-not-be-argv"
    encoded = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", _local_acquisition_run(job_name, origin)],
        env=_acquisition_environment(run_root, workflow_sha, head_sha, token=token),
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert token not in completed.stdout
    assert token not in completed.stderr
    assert encoded not in completed.stdout
    assert encoded not in completed.stderr
    argv = (run_root / "git-argv.bin").read_bytes()
    assert token.encode() not in argv
    assert encoded.encode() not in argv
    auth_log = (run_root / "auth.log").read_text()
    assert token not in auth_log
    assert encoded not in auth_log
    assert "git-basic-ok" in auth_log.splitlines()
    if job_name == "trusted-controller":
        assert "python-basic-ok" in auth_log.splitlines()
    else:
        assert "python-basic-ok" not in auth_log.splitlines()
    assert not marker.exists()
    assert not (run_root / "hostile-path-executed").exists()
    prefix = "trusted-controller" if job_name == "trusted-controller" else "trusted-verifier"
    receipt = (run_root / f"{prefix}-source/trusted-source.receipt").read_text()
    assert f"commit={workflow_sha}" in receipt
    assert "path=scripts/ops/trusted_deletion_anchor.py" in receipt
    assert re.search(r"(?m)^blob=[0-9a-f]{40}$", receipt)
    assert re.search(r"(?m)^sha256=[0-9a-f]{64}$", receipt)
    assert token not in receipt
    assert encoded not in receipt
    config = (run_root / f"{prefix}.git/config").read_text()
    assert token not in config
    assert encoded not in config
    if job_name == "trusted-controller":
        assert (run_root / "trusted-anchor/manifest.json").is_file()


@pytest.mark.parametrize("script_object", ["executable", "symlink", "tree"])
def test_acquisition_shell_rejects_non_regular_or_wrong_mode_source(
    script_object: str, tmp_path: Path
):
    origin, workflow_sha, head_sha, _ = _trusted_origin(tmp_path, script_object=script_object)
    run_root = tmp_path / "run"
    run_root.mkdir()
    completed = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _local_acquisition_run("trusted-verifier", origin),
        ],
        env=_acquisition_environment(run_root, workflow_sha, head_sha),
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (run_root / "trusted-verifier.git").exists()
    assert not (run_root / "trusted-verifier-source").exists()


def test_acquisition_shell_rejects_wrong_workflow_sha_and_cleans_up(tmp_path: Path):
    origin, _, head_sha, _ = _trusted_origin(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir()
    wrong_sha = "f" * 40
    completed = subprocess.run(
        [
            "bash",
            "-euo",
            "pipefail",
            "-c",
            _local_acquisition_run("trusted-verifier", origin),
        ],
        env=_acquisition_environment(run_root, wrong_sha, head_sha),
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (run_root / "trusted-verifier.git").exists()
    assert not (run_root / "trusted-verifier-source").exists()


@pytest.mark.parametrize("interruption", ["false", "kill -TERM $$"])
def test_acquisition_trap_removes_config_lock_on_failure_or_signal(
    interruption: str, tmp_path: Path
):
    origin, workflow_sha, head_sha, _ = _trusted_origin(tmp_path)
    run_root = tmp_path / "run"
    run_root.mkdir()
    run = _local_acquisition_run("trusted-verifier", origin)
    remote_line = f'git -C "$bare_repo" remote add origin {shlex.quote(str(origin))}'
    run = run.replace(
        remote_line,
        f'{remote_line}\ntouch "$bare_repo/config.lock"\n{interruption}',
    )
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env=_acquisition_environment(run_root, workflow_sha, head_sha),
        capture_output=True,
        text=True,
    )
    assert completed.returncode != 0
    assert not (run_root / "trusted-verifier.git").exists()
    assert not (run_root / "trusted-verifier-source").exists()


def test_trusted_jobs_never_execute_head_code_or_materialize_a_worktree():
    workflow = yaml.safe_load(WORKFLOW.read_text())
    for job_name in ("trusted-controller", "trusted-verifier"):
        serialized = str(workflow["jobs"][job_name]).lower()
        assert "github.event.pull_request.head" in serialized or job_name == "trusted-controller"
        assert "checkout" not in serialized
        assert "worktree" not in serialized
        assert "submodule" not in serialized
        assert "source.tar" not in serialized or job_name == "trusted-controller"


def test_canonical_raw_diff_ignores_git_abbrev_config(tmp_path: Path):
    repo = tmp_path / "raw-diff-source"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "trusted-anchor-test")
    source = repo / "sample.txt"
    source.write_text("before\n", encoding="utf-8")
    _run_git(repo, "add", "sample.txt")
    _run_git(repo, "commit", "-m", "base")
    base_sha = _run_git(repo, "rev-parse", "HEAD")
    source.write_text("after\n", encoding="utf-8")
    _run_git(repo, "commit", "-am", "head")
    head_sha = _run_git(repo, "rev-parse", "HEAD")

    _run_git(repo, "config", "core.abbrev", "9")
    nine = trusted_anchor._canonical_raw_diff(repo, base_sha, head_sha)
    _run_git(repo, "config", "core.abbrev", "8")
    eight = trusted_anchor._canonical_raw_diff(repo, base_sha, head_sha)

    assert nine == eight
    metadata = nine.split(b"\0", 1)[0].split()
    assert len(metadata[2]) == 40
    assert len(metadata[3]) == 40


def test_ephemeral_bare_repo_disables_background_maintenance(tmp_path: Path) -> None:
    repo = tmp_path / "repo.git"
    trusted_anchor._init_ephemeral_bare_repo(repo)

    def config(key: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), "config", "--get", key],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    assert config("core.bare") == "true"
    assert config("gc.auto") == "0"
    assert config("gc.autoDetach") == "false"
    assert config("gc.writeCommitGraph") == "false"
    assert config("fetch.writeCommitGraph") == "false"
    assert config("maintenance.auto") == "false"


def test_pr1789_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1789_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1789,
        (
            "ca23695a4cfbca27f64bc163655256ae45cb0b12933cffe7c07c5aff91da440d",
            "2f5282586cbc972ad6990be39f5f7789efe1f7fcfa9b2b8eaa7508eccf03224f",
            "96331173f3ce5c1c91f7a20d011f1af2d4a927602ede40eacf91c343a0453b9a",
            "6df6eff22f2bb3dcddbd3c4fd16483a91aeac644ca1bc098ef0a7a153088e3e2",
        ),
    )


def test_pr1789_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1789_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1789,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1789,
                head_product_init_is_regular=True,
            )

    for other_pr in (1788, 1790):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_pr1796_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1796_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1796,
        (
            "96331173f3ce5c1c91f7a20d011f1af2d4a927602ede40eacf91c343a0453b9a",
            "6df6eff22f2bb3dcddbd3c4fd16483a91aeac644ca1bc098ef0a7a153088e3e2",
            "16b2ee33278ec5fdf156b47f1d8f30bd167509616c3c8d506d358aa9bad1239d",
            "0a50680697e7abbe0b26e6d3e6eef235d9c1e3244a5527b87ac47d57fe2f0015",
        ),
    )


def test_pr1796_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1796_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1796,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1796,
                head_product_init_is_regular=True,
            )

    for other_pr in (1795, 1797):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_pr1804_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1804_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1804,
        (
            "16b2ee33278ec5fdf156b47f1d8f30bd167509616c3c8d506d358aa9bad1239d",
            "0a50680697e7abbe0b26e6d3e6eef235d9c1e3244a5527b87ac47d57fe2f0015",
            "91745c8beac9a1363e18b3dd13e743590c754a98d27dc2f0bff97874a94f0257",
            "e605aa1109b70d6c99c124e30997f0acf45b72300624a155b4499cc8e2632f52",
        ),
    )


def test_pr1804_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1804_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1804,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1804,
                head_product_init_is_regular=True,
            )

    for other_pr in (1803, 1805):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_pr1857_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1857_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1857,
        (
            "91745c8beac9a1363e18b3dd13e743590c754a98d27dc2f0bff97874a94f0257",
            "e605aa1109b70d6c99c124e30997f0acf45b72300624a155b4499cc8e2632f52",
            "57e07fd5272cb64774464bec61e3d8b475898782bcfd048d6930b873336afd75",
            "7808d62f2eaf6ab80a4b56c74563c5053ebe2764d64591f46a5c30b7c4a96068",
        ),
    )


def test_pr1857_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1857_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1857,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1857,
                head_product_init_is_regular=True,
            )

    for other_pr in (1856, 1858):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_pr1908_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR1908_DEPENDENCY_SNAPSHOT_TRANSITION == (
        1908,
        (
            "57e07fd5272cb64774464bec61e3d8b475898782bcfd048d6930b873336afd75",
            "7808d62f2eaf6ab80a4b56c74563c5053ebe2764d64591f46a5c30b7c4a96068",
            "275eceb0af8e4d07a7373359bd0811c8147a403f9fa4d49739f20dd1d974c762",
            "09f17508d34972268d4c7cff6877c447cf8586eff8684bbbbc6170255ca368d4",
        ),
    )


def test_pr1908_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR1908_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=1908,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=1908,
                head_product_init_is_regular=True,
            )

    for other_pr in (1907, 1909):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


# --- #1974 (#1895 rows 2-3): verifier surfaces the controller failure reason ---


def _controller_failure_dir(tmp_path: Path, files: dict[str, object]) -> Path:
    failure_dir = tmp_path / "trusted-anchor-failure"
    failure_dir.mkdir()
    for name, payload in files.items():
        data = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        (failure_dir / name).write_bytes(data)
    return failure_dir


def _controller_args(tmp_path: Path, failure_reason: Path | None) -> argparse.Namespace:
    return argparse.Namespace(
        event_json=str(tmp_path / "missing-event.json"),
        repo_root=str(tmp_path),
        output_dir=str(tmp_path / "out"),
        runtime_dir=str(tmp_path / "runtime"),
        failure_reason_json=None if failure_reason is None else str(failure_reason),
    )


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (
            ValueError("PR dependency contract drifts from trusted default"),
            "DEPENDENCY_CONTRACT_DRIFT",
        ),
        (ValueError("controller repository remains shallow"), "CONTROLLER_ERROR"),
        (subprocess.CalledProcessError(128, ["git", "fetch"]), "CONTROLLER_ERROR"),
    ],
)
def test_controller_failure_records_reason_and_still_fails(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, error: Exception, code: str
):
    def _boom(_args: argparse.Namespace) -> None:
        raise error

    monkeypatch.setattr(trusted_anchor, "_controller", _boom)
    reason_path = tmp_path / "trusted-anchor-failure" / "controller-failure.json"
    with pytest.raises(type(error)):
        trusted_anchor._controller_recording_failure(_controller_args(tmp_path, reason_path))
    record = json.loads(reason_path.read_text(encoding="utf-8"))
    assert record["schema"] == trusted_anchor.CONTROLLER_FAILURE_SCHEMA
    assert record["reason_code"] == code
    assert "\n" not in record["detail"]
    assert len(record["detail"]) <= trusted_anchor.CONTROLLER_FAILURE_DETAIL_LIMIT


def test_controller_success_writes_no_failure_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setattr(trusted_anchor, "_controller", lambda _args: None)
    reason_path = tmp_path / "trusted-anchor-failure" / "controller-failure.json"
    trusted_anchor._controller_recording_failure(_controller_args(tmp_path, reason_path))
    assert not reason_path.exists()


def test_controller_cli_accepts_failure_reason_path():
    assert (
        "--failure-reason-json"
        in _named_step("trusted-controller", "Acquire and execute exact trusted controller source")[
            "run"
        ]
    )


@pytest.mark.parametrize(
    ("lane_reason", "code"),
    [
        ("EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED", "MERGE_LANE_BINDING_MISSING"),
        ("PR_BODY_REQUIRED", "MERGE_LANE_BINDING_MISSING"),
        ("OWNER_INLINE_MUST_BE_DIRECT", "MERGE_LANE_BINDING_BLOCKED"),
    ],
)
def test_lane_gate_block_is_surfaced_with_trusted_remedy(
    tmp_path: Path, lane_reason: str, code: str
):
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "merge-lane-gate.json": {
                "schema": "nexus.trusted_merge_lane_gate_result.v1",
                "status": "BLOCK",
                "reason": lane_reason,
                "remedy": "forged remedy must never be shown",
            }
        },
    )
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["status"] == "BLOCK"
    assert result["reason_code"] == code
    assert result["remedy"] == trusted_anchor.CONTROLLER_FAILURE_REMEDIES[code]
    assert result["detail"] == lane_reason


def test_dependency_drift_reason_is_surfaced(tmp_path: Path):
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": "DEPENDENCY_CONTRACT_DRIFT",
                "detail": "ValueError: PR dependency contract drifts from trusted default",
            }
        },
    )
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["reason_code"] == "DEPENDENCY_CONTRACT_DRIFT"
    assert "merge origin/main" in result["remedy"]


@pytest.mark.parametrize(
    "files",
    [
        {},
        {"controller-failure.json": b"not json"},
        {"controller-failure.json": {"schema": "other", "reason_code": "CONTROLLER_ERROR"}},
        {
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": "PASS",
                "detail": "x",
            }
        },
        {
            "merge-lane-gate.json": {
                "status": "PASS",
                "reason": "EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED",
            }
        },
        {"merge-lane-gate.json": {"status": "BLOCK", "reason": "lower case\n::error::forged"}},
        {
            "merge-lane-gate.json": b"{"
            + b" " * (trusted_anchor.CONTROLLER_FAILURE_FILE_LIMIT + 1)
            + b"}"
        },
    ],
)
def test_untrusted_or_unrecognized_reason_falls_back_to_unavailable(
    tmp_path: Path, files: dict[str, object]
):
    failure_dir = _controller_failure_dir(tmp_path, files)
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["status"] == "BLOCK"
    assert result["reason_code"] == "CONTROLLER_REASON_UNAVAILABLE"


def test_missing_failure_dir_falls_back_to_unavailable(tmp_path: Path):
    result = trusted_anchor.resolve_controller_failure(
        tmp_path / "absent", controller_result="cancelled"
    )
    assert result["reason_code"] == "CONTROLLER_REASON_UNAVAILABLE"
    assert "cancelled" in result["detail"]


def test_symlinked_reason_file_is_not_followed(tmp_path: Path):
    target = tmp_path / "elsewhere.json"
    target.write_text(
        json.dumps({"status": "BLOCK", "reason": "EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED"})
    )
    failure_dir = _controller_failure_dir(tmp_path, {})
    (failure_dir / "merge-lane-gate.json").symlink_to(target)
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["reason_code"] == "CONTROLLER_REASON_UNAVAILABLE"


def test_hostile_detail_is_single_bounded_printable_line(tmp_path: Path):
    hostile = "line1\n::add-mask::x\r\n::set-output name=a::b\x1b[31m‮" + "A" * 10_000
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": "CONTROLLER_ERROR",
                "detail": hostile,
            }
        },
    )
    detail = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")[
        "detail"
    ]
    assert len(detail) <= trusted_anchor.CONTROLLER_FAILURE_DETAIL_LIMIT
    assert re.fullmatch(r"[\x20-\x7e]*", detail)


@pytest.mark.parametrize("controller_result", ["failure", "success", "cancelled", "skipped"])
def test_explain_controller_failure_always_fails_closed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], controller_result: str
):
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "merge-lane-gate.json": {"status": "PASS", "reason": "::error::forged"},
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": "CONTROLLER_ERROR",
                "detail": "\n::warning::forged\n",
            },
        },
    )
    args = argparse.Namespace(failure_dir=str(failure_dir), controller_result=controller_result)
    with pytest.raises(SystemExit) as exit_info:
        trusted_anchor._explain_controller_failure(args)
    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    command_lines = [line for line in out.splitlines() if line.lstrip().startswith("::")]
    assert command_lines == [
        "::error title=Trusted controller failed::CONTROLLER_ERROR: "
        + trusted_anchor.CONTROLLER_FAILURE_REMEDIES["CONTROLLER_ERROR"]
    ]
    assert "forged" in out  # shown, but only as inert, prefixed data


def test_controller_job_uploads_failure_reason_only_on_failure():
    upload = _named_step("trusted-controller", "Upload controller failure reason")
    assert upload["if"] == "failure()"
    assert upload["uses"].startswith("actions/upload-artifact@")
    assert upload["with"]["name"] == "trusted-anchor-controller-failure-${{ github.run_id }}"
    assert upload["with"]["path"] == "${{ runner.temp }}/trusted-anchor-failure/"
    collect = _named_step("trusted-controller", "Collect controller failure reason")
    assert collect["if"] == "failure()"
    steps = [step.get("name") for step in _workflow()["jobs"]["trusted-controller"]["steps"]]
    assert steps.index("Collect controller failure reason") < steps.index(
        "Upload controller failure reason"
    )


def test_collect_controller_failure_step_copies_lane_block_and_skips_symlink(tmp_path: Path):
    """#2258: the step no longer copies a merge-lane result (the gate step is gone).

    A stray ``merge-lane-gate.json`` in the anchor dir, real or symlinked, must
    not reach the failure artifact, and the failure dir is still never empty.
    """
    run = _named_step("trusted-controller", "Collect controller failure reason")["run"]
    assert "merge-lane-gate.json" not in run
    anchor_dir = tmp_path / "trusted-anchor"
    anchor_dir.mkdir()
    (anchor_dir / "merge-lane-gate.json").write_text('{"status":"BLOCK"}\n')
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path), "GITHUB_RUN_ID": "7"},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    failure_dir = tmp_path / "trusted-anchor-failure"
    assert not (failure_dir / "merge-lane-gate.json").exists()
    assert list(failure_dir.iterdir())  # never empty, so the upload cannot vanish
    second = tmp_path / "second"
    (second / "trusted-anchor").mkdir(parents=True)
    (second / "trusted-anchor" / "merge-lane-gate.json").symlink_to(tmp_path / "x")
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env={**os.environ, "RUNNER_TEMP": str(second), "GITHUB_RUN_ID": "7"},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert not (second / "trusted-anchor-failure" / "merge-lane-gate.json").exists()


def test_verifier_reports_controller_reason_before_bundle_download_and_fails_closed():
    steps = _workflow()["jobs"]["trusted-verifier"]["steps"]
    names = [step.get("name") for step in steps]
    download = _named_step("trusted-verifier", "Download controller failure reason")
    report = _named_step("trusted-verifier", "Report controller failure reason (fail closed)")
    gate = "needs.trusted-controller.result != 'success'"
    assert download["if"] == gate
    assert download["continue-on-error"] is True
    assert download["uses"].startswith("actions/download-artifact@")
    assert download["with"]["name"] == "trusted-anchor-controller-failure-${{ github.run_id }}"
    assert report["if"] == gate
    assert "continue-on-error" not in report
    assert "explain-controller-failure" in report["run"]
    assert '"$RUNNER_TEMP/trusted-verifier-source/trusted_deletion_anchor.py"' in report["run"]
    assert (
        names.index("Acquire exact trusted verifier source")
        < names.index("Download controller failure reason")
        < names.index("Report controller failure reason (fail closed)")
        < names.index("Download controller bundle")
    )
    # Steps after the report keep the implicit success() guard, so a controller
    # failure can never reach the PASS path.
    later = steps[names.index("Download controller bundle") :]
    for step in later[:-1]:
        assert "if" not in step, step.get("name")
    assert later[-1]["name"] == "Cleanup trusted verifier source"
    assert later[-1]["if"] == "always()"


def test_oversized_but_otherwise_valid_lane_block_is_rejected(tmp_path: Path):
    payload = json.dumps({
        "status": "BLOCK",
        "reason": "EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED",
        "padding": "x" * trusted_anchor.CONTROLLER_FAILURE_FILE_LIMIT,
    }).encode()
    failure_dir = _controller_failure_dir(tmp_path, {"merge-lane-gate.json": payload})
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["reason_code"] == "CONTROLLER_REASON_UNAVAILABLE"
    # Control: the same content under the limit is accepted.
    (tmp_path / "small").mkdir()
    small = _controller_failure_dir(
        tmp_path / "small",
        {"merge-lane-gate.json": {"status": "BLOCK", "reason": "PR_BODY_REQUIRED"}},
    )
    assert (
        trusted_anchor.resolve_controller_failure(small, controller_result="failure")["reason_code"]
        == "MERGE_LANE_BINDING_MISSING"
    )


@pytest.mark.parametrize(
    "forged_code",
    [
        "MERGE_LANE_BINDING_MISSING",
        "MERGE_LANE_BINDING_BLOCKED",
        "CONTROLLER_REASON_UNAVAILABLE",
    ],
)
def test_controller_record_cannot_claim_non_recordable_code(tmp_path: Path, forged_code: str):
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": forged_code,
                "detail": "forged",
            }
        },
    )
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["reason_code"] == "CONTROLLER_REASON_UNAVAILABLE"
    assert "forged" not in result["detail"]


def test_token_like_strings_are_redacted_from_detail(tmp_path: Path):
    ghs = "ghs" + "_" + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"
    ghp = "ghp" + "_" + "Z9y8X7w6V5u4T3s2R1q0P9o8N7m6L5k4J3i2"
    pat = "github" + "_pat_" + "11ABCDEFG0123456789_abcdefghijklmnop"
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": "CONTROLLER_ERROR",
                "detail": f"auth {ghs} then {ghp} and {pat} end",
            }
        },
    )
    detail = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")[
        "detail"
    ]
    for secret in (ghs, ghp, pat):
        assert secret not in detail
    assert detail == "auth [REDACTED] then [REDACTED] and [REDACTED] end"
    record = trusted_anchor._controller_failure_record(ValueError(f"leak {ghs}"))
    assert ghs not in record["detail"]
    assert "[REDACTED]" in record["detail"]


def test_deeply_nested_reason_json_falls_back_to_unavailable(tmp_path: Path):
    failure_dir = _controller_failure_dir(
        tmp_path, {"controller-failure.json": b"[" * 30_000 + b"]" * 30_000}
    )
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["reason_code"] == "CONTROLLER_REASON_UNAVAILABLE"


def test_explain_step_runs_isolated_default_branch_source():
    run = _named_step("trusted-verifier", "Report controller failure reason (fail closed)")["run"]
    commands = [line.strip() for line in run.splitlines() if "explain-controller-failure" in line]
    assert commands == [
        'python -I "$RUNNER_TEMP/trusted-verifier-source/trusted_deletion_anchor.py" '
        "explain-controller-failure "
        '--failure-dir "$RUNNER_TEMP/trusted-anchor-failure" '
        '--controller-result "$CONTROLLER_RESULT"'
    ]
    assert "trusted-anchor-failure/" not in run.split("explain-controller-failure")[0]


def test_collect_step_skips_symlink_to_existing_file(tmp_path: Path):
    run = _named_step("trusted-controller", "Collect controller failure reason")["run"]
    real = tmp_path / "real-lane.json"
    real.write_text('{"status":"BLOCK","reason":"PR_BODY_REQUIRED"}\n')
    (tmp_path / "trusted-anchor").mkdir()
    (tmp_path / "trusted-anchor" / "merge-lane-gate.json").symlink_to(real)
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path), "GITHUB_RUN_ID": "7"},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    failure_dir = tmp_path / "trusted-anchor-failure"
    assert not (failure_dir / "merge-lane-gate.json").exists()
    assert (failure_dir / "controller-failed.marker").read_text() == "run_id=7\n"


def test_pr2016_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR2016_DEPENDENCY_SNAPSHOT_TRANSITION == (
        2016,
        (
            "634340008a5adc2a608dc19c6fc34fee38b1773b2de78661327412c609e3820f",
            "09f17508d34972268d4c7cff6877c447cf8586eff8684bbbbc6170255ca368d4",
            "fa6c8ebbfac872fc59715a035158ab05c3141fcd2df5363f35ac623d57decef1",
            "c00226cb36776992cb706c0b3d8727de67b3cdc28e1b9b92f95c89aac1c6d808",
        ),
    )


def test_pr2016_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR2016_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=2016,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=2016,
                head_product_init_is_regular=True,
            )

    for other_pr in (2015, 2017):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


# --- controller bash steps record a bootstrap reason (failure before Python runs) ---

_BOOTSTRAP_STEP = "Acquire and execute exact trusted controller source"


def _run_bootstrap_step(tmp_path: Path, **env: str) -> subprocess.CompletedProcess[str]:
    run = _named_step("trusted-controller", _BOOTSTRAP_STEP)["run"]
    return subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path), **env},
        capture_output=True,
        text=True,
    )


def _bootstrap_env(**overrides: str) -> dict[str, str]:
    return {
        "EVENT_JSON": "{}",
        "EVENT_NAME": "pull_request",  # not pull_request_target: first fail-closed test trips
        "WORKFLOW_REF": "x",
        "WORKFLOW_SHA": "0" * 40,
        "RUN_ID": "1",
        "REPOSITORY": "James3014/Nexus-new",
        "DEFAULT_BRANCH": "main",
        "TRUSTED_TOKEN": "ghs_" + "A" * 36,
        **overrides,
    }


def test_bootstrap_bash_failure_records_allowlisted_reason_and_still_fails(tmp_path: Path):
    completed = _run_bootstrap_step(tmp_path, **_bootstrap_env())
    assert completed.returncode != 0
    reason_path = tmp_path / "trusted-anchor-failure" / "controller-failure.json"
    record = json.loads(reason_path.read_text(encoding="utf-8"))
    assert record["schema"] == trusted_anchor.CONTROLLER_FAILURE_SCHEMA
    assert record["reason_code"] == "CONTROLLER_BOOTSTRAP_FAILED"
    assert _BOOTSTRAP_STEP in record["detail"]
    assert "ghs_" not in reason_path.read_text(encoding="utf-8")
    assert "ghs_" not in completed.stderr
    result = trusted_anchor.resolve_controller_failure(
        reason_path.parent, controller_result="failure"
    )
    assert result["status"] == "BLOCK"
    assert result["reason_code"] == "CONTROLLER_BOOTSTRAP_FAILED"
    assert (
        result["remedy"]
        == trusted_anchor.CONTROLLER_FAILURE_REMEDIES["CONTROLLER_BOOTSTRAP_FAILED"]
    )
    assert _BOOTSTRAP_STEP in result["detail"]


def test_bootstrap_failure_never_overwrites_python_controller_record(tmp_path: Path):
    reason_path = tmp_path / "trusted-anchor-failure" / "controller-failure.json"
    reason_path.parent.mkdir()
    original = json.dumps({
        "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
        "reason_code": "DEPENDENCY_CONTRACT_DRIFT",
        "detail": "drift",
    })
    reason_path.write_text(original, encoding="utf-8")
    completed = _run_bootstrap_step(tmp_path, **_bootstrap_env())
    assert completed.returncode != 0
    assert reason_path.read_text(encoding="utf-8") == original


def test_bootstrap_trap_keeps_failed_command_text_unexpanded():
    run = _named_step("trusted-controller", _BOOTSTRAP_STEP)["run"]
    trap_lines = [line for line in run.splitlines() if "trap '" in line and "ERR" in line]
    assert len(trap_lines) == 1
    assert "$BASH_COMMAND" in trap_lines[0]
    assert trap_lines[0].strip().startswith("trap '")  # single-quoted: expands only on error
    assert "set -x" not in run


def test_bootstrap_failure_does_not_print_token_from_failed_command(tmp_path: Path):
    completed = _run_bootstrap_step(
        tmp_path, **_bootstrap_env(EVENT_NAME="pull_request_target", REPOSITORY="evil/x")
    )
    assert completed.returncode != 0
    assert "ghs_" not in completed.stderr
    assert "ghs_" not in completed.stdout


def test_collect_step_falls_back_to_bootstrap_reason_when_nothing_recorded(tmp_path: Path):
    run = _named_step("trusted-controller", "Collect controller failure reason")["run"]
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env={
            **os.environ,
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_RUN_ID": "7",
            "RUNTIME_BUILDER_OUTCOME": "failure",
            "TRUSTED_SOURCE_OUTCOME": "skipped",
            "EXTERNAL_ANCHOR_OUTCOME": "skipped",
        },
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    failure_dir = tmp_path / "trusted-anchor-failure"
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["reason_code"] == "CONTROLLER_BOOTSTRAP_FAILED"
    assert "runtime-builder=failure" in result["detail"]


def test_collect_step_keeps_existing_reason_record(tmp_path: Path):
    run = _named_step("trusted-controller", "Collect controller failure reason")["run"]
    failure_dir = tmp_path / "trusted-anchor-failure"
    failure_dir.mkdir()
    existing = '{"schema":"x","reason_code":"CONTROLLER_ERROR","detail":"d"}\n'
    (failure_dir / "controller-failure.json").write_text(existing)
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path), "GITHUB_RUN_ID": "7"},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert (failure_dir / "controller-failure.json").read_text() == existing


def test_lane_gate_block_outranks_bootstrap_record(tmp_path: Path):
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": "CONTROLLER_BOOTSTRAP_FAILED",
                "detail": "step=x",
            },
            "merge-lane-gate.json": {
                "status": "BLOCK",
                "reason": "EXACTLY_ONE_MERGE_LANE_BINDING_REQUIRED",
            },
        },
    )
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["reason_code"] == "MERGE_LANE_BINDING_MISSING"


def test_bootstrap_record_detail_is_sanitized_display_data(tmp_path: Path):
    ghs = "ghs_" + "B" * 36
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": "CONTROLLER_BOOTSTRAP_FAILED",
                "detail": f"step=a\nline {ghs} " + "z" * 1000,
            }
        },
    )
    detail = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")[
        "detail"
    ]
    assert ghs not in detail and "\n" not in detail
    assert len(detail) <= trusted_anchor.CONTROLLER_FAILURE_DETAIL_LIMIT


def test_failure_upload_runs_on_failure_regardless_of_failing_step():
    controller = _workflow()["jobs"]["trusted-controller"]["steps"]
    names = [step.get("name") for step in controller]
    collect = _named_step("trusted-controller", "Collect controller failure reason")
    upload = _named_step("trusted-controller", "Upload controller failure reason")
    assert collect["if"] == "failure()" and upload["if"] == "failure()"
    assert names.index("Acquire fixed trusted runtime builder") < names.index(collect["name"])


def test_bootstrap_failure_preserves_distinct_exit_status(tmp_path: Path):
    run = _named_step("trusted-controller", _BOOTSTRAP_STEP)["run"]
    marker = 'test "$EVENT_NAME" = pull_request_target'
    assert marker in run
    run = run.replace(marker, "exit 7", 1)
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", run],
        env={**os.environ, "RUNNER_TEMP": str(tmp_path), **_bootstrap_env()},
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 7, completed.stderr
    record = json.loads(
        (tmp_path / "trusted-anchor-failure" / "controller-failure.json").read_text(
            encoding="utf-8"
        )
    )
    assert "exit=7" in record["detail"]


# ------------------------------------------------------------------------------
# Merge-base rule (Owner-approved option (b), 2026-10-13).  The executor no
# longer requires the base tip as an ancestor of the head.  It requires exactly
# one merge-base, bound in the manifest, and the controller and verifier fail
# closed when main moved over the gate-oracle surface or over the PR's own paths.

_MB_PYPROJECT = b"[project]\nname='fixture'\nversion='0'\n"
_MB_UV_LOCK = b"version = 1\nrevision = 3\n"


def _mb_commit(repo: Path, message: str, files: dict[str, bytes | None]) -> str:
    for relative, data in files.items():
        target = repo / relative
        if data is None:
            target.unlink()
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-q", "--no-verify", "-m", message)
    return _run_git(repo, "rev-parse", "HEAD")


def _mb_root_files() -> dict[str, bytes | None]:
    return {
        "pyproject.toml": _MB_PYPROJECT,
        "uv.lock": _MB_UV_LOCK,
        "tests/ops/test_pr_impact_gate.py": b"def test_gate():\n    assert True\n",
        "tests/golden_behavior/corpus.py": (
            b'CASES = ("tests/contracts/test_witness.py::test_witness",)\n'
        ),
        "tests/contracts/test_witness.py": b"def test_witness():\n    assert True\n",
        "tests/golden_behavior/test_corpus.py": b"def test_corpus():\n    assert True\n",
        trusted_anchor.GOLDEN_EVALUATOR_PATH: b"# trusted evaluator placeholder\n",
        "docs/shared.md": b"shared\n",
    }


def _mb_history(root: Path, scenario: str) -> dict[str, object]:
    """Build an origin with a PR head and a main tip for one history shape."""

    source = root / "mb-source"
    subprocess.run(["git", "init", "-q", "-b", "main", str(source)], check=True)
    _run_git(source, "config", "user.email", "test@example.invalid")
    _run_git(source, "config", "user.name", "merge-base-test")
    fork = _mb_commit(source, "fork point", _mb_root_files())
    main_files: dict[str, bytes | None] = {"docs/main-added.md": b"main added\n"}
    pr_files: dict[str, bytes | None] = {"docs/pr.md": b"pr work\n"}
    if scenario == "main_golden":
        main_files["tests/golden_behavior/corpus.py"] = (
            b'CASES = ("tests/contracts/test_witness.py::test_witness",)\n# main moved\n'
        )
    elif scenario.startswith("main_delete:"):
        main_files[scenario.removeprefix("main_delete:")] = None
    elif scenario.startswith("main_touch:"):
        main_files[scenario.removeprefix("main_touch:")] = b"# main moved\n"
    elif scenario == "main_selected_test":
        main_files["tests/ops/test_pr_impact_gate.py"] = b"def test_gate():\n    assert 1\n"
    elif scenario == "main_uv_lock":
        main_files["uv.lock"] = _MB_UV_LOCK + b"# main lock bump\n"
    elif scenario == "same_path":
        main_files["docs/shared.md"] = b"shared, main edit\n"
        pr_files["docs/shared.md"] = b"shared, pr edit\n"
    if scenario == "up_to_date":
        base = fork
        head = _mb_commit(source, "pr", pr_files)
    elif scenario == "criss_cross":
        x = _mb_commit(source, "x", {"docs/x.md": b"x\n"})
        _run_git(source, "checkout", "-q", "-b", "y", fork)
        y = _mb_commit(source, "y", {"docs/y.md": b"y\n"})
        _run_git(source, "checkout", "-q", "-b", "tip", x)
        _run_git(source, "merge", "-q", "--no-ff", "--no-verify", "-m", "tip", y)
        base = _run_git(source, "rev-parse", "HEAD")
        _run_git(source, "checkout", "-q", "-b", "head", y)
        _run_git(source, "merge", "-q", "--no-ff", "--no-verify", "-m", "head", x)
        head = _run_git(source, "rev-parse", "HEAD")
    elif scenario == "unrelated":
        base = _mb_commit(source, "main moved", main_files)
        _run_git(source, "checkout", "-q", "--orphan", "orphan")
        head = _mb_commit(source, "orphan", {})
    else:
        _run_git(source, "checkout", "-q", "-b", "feature")
        head = _mb_commit(source, "pr", pr_files)
        _run_git(source, "checkout", "-q", "main")
        base = _mb_commit(source, "main moved", main_files)
    origin = root / "mb-origin.git"
    subprocess.run(["git", "init", "-q", "--bare", str(origin)], check=True)
    _run_git(
        source, "push", "-q", str(origin), f"{base}:refs/heads/main", f"{head}:refs/pull/1/head"
    )
    controller_repo = root / "mb-controller.git"
    subprocess.run(["git", "init", "-q", "--bare", str(controller_repo)], check=True)
    _run_git(controller_repo, "remote", "add", "origin", str(origin))
    _run_git(controller_repo, "fetch", "-q", "--no-tags", "--depth=1", "origin", base)
    event = _event()
    event["workflow_sha"] = base
    event["pull_request"]["base"]["sha"] = base  # type: ignore[index]
    event["pull_request"]["head"]["sha"] = head  # type: ignore[index]
    event_path = root / "mb-event.json"
    event_path.write_bytes(_json(event))

    def _at_base(path: str) -> bytes:
        return subprocess.run(
            ["git", "-C", str(source), "show", f"{base}:{path}"], check=True, capture_output=True
        ).stdout

    runtime_dir = _synthetic_runtime(
        root, pyproject=_at_base("pyproject.toml"), uv_lock=_at_base("uv.lock")
    )
    return {
        "source": source,
        "controller_repo": controller_repo,
        "event": event,
        "event_path": event_path,
        "runtime_dir": runtime_dir,
        "bundle": root / "mb-bundle",
        "fork": fork,
        "base": base,
        "head": head,
    }


def _mb_run_controller(history: dict[str, object]) -> dict[str, object]:
    trusted_anchor._controller(
        argparse.Namespace(
            event_json=str(history["event_path"]),
            repo_root=str(history["controller_repo"]),
            output_dir=str(history["bundle"]),
            runtime_dir=str(history["runtime_dir"]),
        )
    )
    return json.loads((Path(history["bundle"]) / "manifest.json").read_text(encoding="utf-8"))


def _mb_raw_entries(raw: bytes) -> list[tuple[str, str]]:
    fields = raw.split(b"\0")
    entries = []
    for index in range(0, len(fields) - 1, 2):
        status = fields[index].split()[-1].decode()
        entries.append((status, fields[index + 1].decode()))
    return entries


def _mb_executor_git_context(bundle: Path, manifest: dict[str, object]) -> None:
    source = bundle / "source"
    if source.exists():
        shutil.rmtree(source)
    source.mkdir()
    with tarfile.open(bundle / "source.tar") as archive:
        archive.extractall(source, filter=trusted_anchor._executor_archive_filter)
    trusted_anchor._prepare_executor_git_context(bundle, source, manifest)


def _mb_verifier_args(history: dict[str, object]) -> argparse.Namespace:
    bundle = Path(history["bundle"])
    event = history["event"]
    assert isinstance(event, dict)
    return argparse.Namespace(
        bundle_dir=str(bundle),
        expected_workflow_ref=event["workflow_ref"],
        expected_workflow_sha=event["workflow_sha"],
        expected_run_id=event["run_id"],
        verify_evidence=str(bundle / "raw-evidence.json"),
        expected_manifest_sha256=trusted_anchor._sha((bundle / "manifest.json").read_bytes()),
        expected_external_anchor_sha256=trusted_anchor._sha(
            (bundle / "external-anchor.json").read_bytes()
        ),
        expected_event_name=event["event_name"],
        expected_repository=event["repository"]["full_name"],
        expected_default_branch=event["repository"]["default_branch"],
        expected_pull_request_number=event["pull_request"]["number"],
        expected_base_sha=event["pull_request"]["base"]["sha"],
        expected_head_sha=event["pull_request"]["head"]["sha"],
    )


def _mb_write_evidence(bundle: Path, manifest: dict[str, object]) -> None:
    (bundle / "raw-evidence.json").write_bytes(_json(_evidence(manifest)) + b"\n")


def _mb_rebind_manifest(bundle: Path, manifest: dict[str, object]) -> None:
    """Rewrite a manifest as a compromised controller would: every digest consistent."""

    unsigned = dict(manifest)
    unsigned.pop("bundle_sha256", None)
    manifest["bundle_sha256"] = trusted_anchor._sha(
        trusted_anchor._json(unsigned)
        + (bundle / "source.tar").read_bytes()
        + (bundle / "raw-diff.bin").read_bytes()
        + trusted_anchor._json(sorted(manifest["test_inventory"]))  # type: ignore[arg-type]
        + (bundle / "git-objects.bundle").read_bytes()
        + (bundle / "requirements.txt").read_bytes()
        + (bundle / "runtime.tar").read_bytes()
        + (bundle / "runtime-metadata.json").read_bytes()
        + (bundle / "run_golden_behavior_eval.py").read_bytes()
    )
    (bundle / "manifest.json").write_bytes(_json(manifest) + b"\n")
    anchor = json.loads((bundle / "external-anchor.json").read_text(encoding="utf-8"))
    anchor["manifest_sha256"] = trusted_anchor._sha((bundle / "manifest.json").read_bytes())
    anchor["merge_base_sha"] = manifest["merge_base_sha"]
    (bundle / "external-anchor.json").write_bytes(_json(anchor) + b"\n")


def test_schema_version_is_bumped_for_merge_base_binding():
    assert trusted_anchor.SCHEMA_VERSION == "trusted-deletion-anchor.v4"
    assert trusted_anchor.RUNTIME_SCHEMA_VERSION == "trusted-deletion-runtime.v2"
    assert "merge_base_sha" in trusted_anchor.REQUIRED_EVIDENCE_KEYS


def test_up_to_date_pr_behaviour_is_unchanged(tmp_path: Path):
    history = _mb_history(tmp_path, "up_to_date")
    manifest = _mb_run_controller(history)
    bundle = Path(history["bundle"])
    assert manifest["merge_base_sha"] == history["base"]
    expected_diff = subprocess.run(
        [
            "git",
            "-C",
            str(history["source"]),
            "diff",
            "--raw",
            "-z",
            "--no-renames",
            "--no-abbrev",
            str(history["base"]),
            str(history["head"]),
        ],
        check=True,
        capture_output=True,
    ).stdout
    assert (bundle / "raw-diff.bin").read_bytes() == expected_diff
    anchor = json.loads((bundle / "external-anchor.json").read_text(encoding="utf-8"))
    assert anchor["merge_base_sha"] == history["base"]
    _mb_executor_git_context(bundle, manifest)
    _mb_write_evidence(bundle, manifest)
    trusted_anchor._verifier(_mb_verifier_args(history))


def test_behind_but_disjoint_pr_passes_controller_executor_and_verifier(tmp_path: Path):
    history = _mb_history(tmp_path, "behind_disjoint")
    manifest = _mb_run_controller(history)
    bundle = Path(history["bundle"])
    assert manifest["base_sha"] == history["base"]
    assert manifest["merge_base_sha"] == history["fork"]
    _mb_executor_git_context(bundle, manifest)
    _mb_write_evidence(bundle, manifest)
    trusted_anchor._verifier(_mb_verifier_args(history))


def test_behind_pr_raw_diff_has_no_false_deletions_for_files_main_added(tmp_path: Path):
    history = _mb_history(tmp_path, "behind_disjoint")
    _mb_run_controller(history)
    entries = _mb_raw_entries((Path(history["bundle"]) / "raw-diff.bin").read_bytes())
    assert entries == [("A", "docs/pr.md")]
    assert all(status != "D" for status, _path in entries)


@pytest.mark.parametrize("scenario", ["criss_cross", "unrelated"])
def test_controller_requires_exactly_one_merge_base(tmp_path: Path, scenario: str):
    history = _mb_history(tmp_path, scenario)
    with pytest.raises(ValueError, match="MERGE_BASE_NOT_UNIQUE"):
        _mb_run_controller(history)
    assert not (Path(history["bundle"]) / "manifest.json").exists()


@pytest.mark.parametrize("scenario", ["criss_cross", "unrelated"])
def test_executor_rejects_non_unique_merge_base(tmp_path: Path, scenario: str):
    history = _mb_history(tmp_path, scenario)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(trusted_anchor, "_unique_merge_base", lambda *_args: history["base"])
        manifest = _mb_run_controller(history)
    with pytest.raises(ValueError, match="executor Git identity mismatch"):
        _mb_executor_git_context(Path(history["bundle"]), manifest)


def test_tampered_merge_base_sha_fails_executor_and_verifier(tmp_path: Path):
    history = _mb_history(tmp_path, "behind_disjoint")
    manifest = _mb_run_controller(history)
    bundle = Path(history["bundle"])
    manifest["merge_base_sha"] = history["base"]
    _mb_rebind_manifest(bundle, manifest)
    with pytest.raises(ValueError, match="executor Git identity mismatch"):
        _mb_executor_git_context(bundle, manifest)
    _mb_write_evidence(bundle, manifest)
    with pytest.raises(SystemExit):
        trusted_anchor._verifier(_mb_verifier_args(history))


def test_evidence_merge_base_sha_must_match_manifest():
    manifest = _manifest()
    evidence = _evidence(manifest)
    assert _verify(manifest, evidence) == "PASS"
    evidence["merge_base_sha"] = "f" * 40
    assert _verify(manifest, evidence) == "IMPACT_UNKNOWN"


@pytest.mark.parametrize("scenario", ["main_golden", "main_selected_test", "same_path"])
def test_main_moved_over_gate_surface_or_pr_paths_fails_closed(tmp_path: Path, scenario: str):
    history = _mb_history(tmp_path, scenario)
    with pytest.raises(ValueError, match="MAIN_MOVED_OVER_GATE_SURFACE: merge origin/main"):
        _mb_run_controller(history)
    record = trusted_anchor._controller_failure_record(
        ValueError("MAIN_MOVED_OVER_GATE_SURFACE: merge origin/main; x")
    )
    assert record["reason_code"] == "MAIN_MOVED_OVER_GATE_SURFACE"


@pytest.mark.parametrize("scenario", ["main_golden", "same_path"])
def test_verifier_recomputes_main_moved_check(
    tmp_path: Path, scenario: str, capsys: pytest.CaptureFixture[str]
):
    history = _mb_history(tmp_path, scenario)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(trusted_anchor, "_require_main_not_moved_over_gate", lambda *_a: None)
        manifest = _mb_run_controller(history)
    bundle = Path(history["bundle"])
    _mb_write_evidence(bundle, manifest)
    with pytest.raises(SystemExit):
        trusted_anchor._verifier(_mb_verifier_args(history))
    assert "MAIN_MOVED_OVER_GATE_SURFACE: merge origin/main" in capsys.readouterr().err


def test_main_changed_uv_lock_fails_with_dependency_drift(tmp_path: Path):
    history = _mb_history(tmp_path, "main_uv_lock")
    with pytest.raises(ValueError) as caught:
        _mb_run_controller(history)
    record = trusted_anchor._controller_failure_record(caught.value)
    assert record["reason_code"] == "DEPENDENCY_CONTRACT_DRIFT"
    assert (
        "merge origin/main"
        in trusted_anchor.CONTROLLER_FAILURE_REMEDIES["DEPENDENCY_CONTRACT_DRIFT"]
    )


@pytest.mark.parametrize(
    ("path", "gated"),
    [
        ("tests/ops/test_pr_impact_gate.py", True),
        ("tests/ops/test_select_tests.py", True),
        ("tests/golden_behavior/corpus.py", True),
        ("tests/golden_behavior/nested/data.json", True),
        ("scripts/ops/run_golden_behavior_eval.py", True),
        ("scripts/ops/pr_impact_gate.py", True),
        ("scripts/ops/select_tests.py", True),
        ("scripts/ops/trusted_deletion_anchor.py", True),
        ("scripts/ops/trusted_impact_gate.py", True),
        (".github/workflows/lint.yml", True),
        (".nexus-core/config.json", True),
        ("docs/testing/test_impact_map.md", True),
        (".nexus/test_impact_index.json", True),
        ("pyproject.toml", True),
        ("uv.lock", True),
        ("product/__init__.py", True),
        ("scripts/ops/nested/trusted_x.py", False),
        ("scripts/ops/untrusted_x.py", False),
        ("tests/ops/test_other.py", False),
        ("product/other.py", False),
        ("docs/main-added.md", False),
    ],
)
def test_gate_oracle_surface_membership(path: str, gated: bool):
    assert trusted_anchor._is_gate_oracle_surface(path) is gated
    assert bool(trusted_anchor._gate_surface_overlap([path], [])) is gated


def test_gate_surface_overlap_includes_pr_paths_and_empty_main_delta_passes():
    assert trusted_anchor._gate_surface_overlap([], ["uv.lock"]) == []
    assert trusted_anchor._gate_surface_overlap(["docs/a.md"], ["docs/b.md"]) == []
    assert trusted_anchor._gate_surface_overlap(["docs/a.md", "uv.lock"], ["docs/a.md"]) == [
        "docs/a.md",
        "uv.lock",
    ]


def test_main_moved_reason_is_allowlisted_with_trusted_remedy(tmp_path: Path):
    code = "MAIN_MOVED_OVER_GATE_SURFACE"
    assert "merge origin/main" in trusted_anchor.CONTROLLER_FAILURE_REMEDIES[code]
    failure_dir = _controller_failure_dir(
        tmp_path,
        {
            "controller-failure.json": {
                "schema": trusted_anchor.CONTROLLER_FAILURE_SCHEMA,
                "reason_code": code,
                "detail": "ValueError: MAIN_MOVED_OVER_GATE_SURFACE: merge origin/main; uv.lock",
            }
        },
    )
    result = trusted_anchor.resolve_controller_failure(failure_dir, controller_result="failure")
    assert result["reason_code"] == code
    assert result["remedy"] == trusted_anchor.CONTROLLER_FAILURE_REMEDIES[code]


@pytest.mark.parametrize(
    "path",
    [
        "tests/contracts/test_witness.py",
        "pytest.ini",
        "tests/conftest.py",
        "tests/ops/conftest.py",
        "tests/contracts/conftest.py",
        "tests/__init__.py",
        "scripts/__init__.py",
        "scripts/ops/__init__.py",
    ],
)
def test_main_moved_over_witness_pytest_ini_or_import_chain_fails_closed(tmp_path: Path, path: str):
    history = _mb_history(tmp_path, f"main_touch:{path}")
    with pytest.raises(ValueError, match="MAIN_MOVED_OVER_GATE_SURFACE: merge origin/main"):
        _mb_run_controller(history)


def test_verifier_recomputes_witness_surface(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    history = _mb_history(tmp_path, "main_touch:tests/contracts/test_witness.py")
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(trusted_anchor, "_require_main_not_moved_over_gate", lambda *_a: None)
        manifest = _mb_run_controller(history)
    _mb_write_evidence(Path(history["bundle"]), manifest)
    with pytest.raises(SystemExit):
        trusted_anchor._verifier(_mb_verifier_args(history))
    assert "tests/contracts/test_witness.py" in capsys.readouterr().err


def test_unrelated_main_test_change_stays_admitted(tmp_path: Path):
    history = _mb_history(tmp_path, "main_touch:tests/contracts/test_unrelated.py")
    manifest = _mb_run_controller(history)
    assert manifest["merge_base_sha"] == history["fork"]


def test_golden_witness_paths_are_read_statically_from_corpus_source():
    source = (
        b'X = ("tests/a/test_one.py::test_x", "tests/a/test_one.py::C::test_y")\n'
        b'Y = ("tests/b/test_two.py" "::test_z", "nexus/not_a_test.py", "docs/x.md")\n'
        b"import os; os.system('never executed')\n"
    )
    assert trusted_anchor._golden_witness_paths(source) == {
        "tests/a/test_one.py",
        "tests/b/test_two.py",
    }
    with pytest.raises(ValueError, match="GOLDEN_CORPUS_UNVERIFIABLE"):
        trusted_anchor._golden_witness_paths(b"def (")


def test_witness_named_only_at_base_tip_or_only_at_merge_base_is_surface():
    overlap = trusted_anchor._gate_surface_overlap
    assert overlap(["tests/x/test_w.py"], [], {"tests/x/test_w.py"}) == ["tests/x/test_w.py"]
    assert overlap(["tests/x/test_w.py"], [], set()) == []


def test_build_manifest_requires_merge_base_sha():
    with pytest.raises(TypeError):
        build_manifest(  # type: ignore[call-arg]
            _event(),
            raw_diff=b"",
            test_inventory=["tests/ops/test_pr_impact_gate.py"],
            source_archive=b"",
        )


def test_verifier_rejects_anchor_merge_base_that_differs_from_manifest(tmp_path: Path):
    """The external anchor names the merge-base it vouches for; it must equal the manifest."""

    history = _mb_history(tmp_path, "behind_disjoint")
    manifest = _mb_run_controller(history)
    bundle = Path(history["bundle"])
    _mb_write_evidence(bundle, manifest)
    trusted_anchor._verifier(_mb_verifier_args(history))
    anchor = json.loads((bundle / "external-anchor.json").read_text(encoding="utf-8"))
    anchor["merge_base_sha"] = history["base"]
    (bundle / "external-anchor.json").write_bytes(_json(anchor) + b"\n")
    with pytest.raises(SystemExit):
        trusted_anchor._verifier(_mb_verifier_args(history))


def test_unparseable_main_corpus_fails_closed(tmp_path: Path):
    history = _mb_history(tmp_path, "main_touch:tests/golden_behavior/corpus.py")
    source = Path(history["source"])
    (source / "tests/golden_behavior/corpus.py").write_text("def (\n")
    _run_git(source, "commit", "-q", "--no-verify", "-am", "broken corpus")
    with pytest.raises(ValueError, match="GOLDEN_CORPUS_UNVERIFIABLE"):
        trusted_anchor._main_moved_overlap(
            source,
            str(history["fork"]),
            _run_git(source, "rev-parse", "HEAD"),
            str(history["head"]),
        )


# --- follow-up A: Golden witness extraction must fail closed, never open ---

_GOOD_WITNESS = '"tests/contracts/test_witness.py::test_witness"'


@pytest.mark.parametrize(
    ("source", "why"),
    [
        (b"", "empty"),
        (b"CASES = ()\n", "zero witnesses"),
        (b'CASES = (f"tests/contracts/test_{1}.py::test_witness",)\n', "f-string"),
        (b'CASES = ("tests/contracts/" + "test_witness.py::test_witness",)\n', "concatenation"),
        (b'CASES = (b"tests/contracts/test_witness.py::test_witness",)\n', "bytes"),
        (b'X = "tests/contracts/test_witness.py ::bad"\n', "malformed path string"),
        (
            b"W = ()\n_c('GB-1', 't', 'c', 's', 'e', (), W)\n",
            "positional automated_tests is a name",
        ),
        (
            b"_c('GB-1', 't', 'c', 's', 'e', (), automated_tests=tuple(['x']))\n",
            "keyword automated_tests is a call",
        ),
        (
            b"_c('GB-1', 't', 'c', 's', 'e', (), (" + _GOOD_WITNESS.encode() + b", W))\n",
            "non-literal element",
        ),
    ],
)
def test_golden_witness_extraction_fails_closed(source: bytes, why: str):
    with pytest.raises(ValueError, match="GOLDEN_CORPUS_UNVERIFIABLE"):
        trusted_anchor._golden_witness_paths(source)


def test_golden_witness_extraction_accepts_literal_case_calls_and_helper_body():
    source = (
        b"def _c(case_id, t, c, s, e, a, automated_tests=()):\n"
        b"    return GoldenCase(case_id, t, c, s, e, a, automated_tests)\n"
        b"CASES = (\n"
        b"    _c('GB-1', 't', 'c', 's', 'e', (), (" + _GOOD_WITNESS.encode() + b",)),\n"
        b"    _c('GB-2', 't', 'c', 's', 'e', (), automated_tests=['tests/a/test_b.py::t']),\n"
        b"    _c('GB-3', 't', 'c', 's', 'e', ()),\n"
        b")\n"
    )
    assert trusted_anchor._golden_witness_paths(source) == {
        "tests/contracts/test_witness.py",
        "tests/a/test_b.py",
    }


def test_real_golden_corpus_extracts_witnesses():
    paths = trusted_anchor._golden_witness_paths(
        (ROOT / "tests/golden_behavior/corpus.py").read_bytes()
    )
    assert len(paths) >= 30
    assert "tests/ops/test_trusted_merge_lane_gate.py" in paths


def _corpus_repo(root: Path, main_corpus: bytes | None) -> tuple[Path, str, str, str]:
    repo = root / "corpus-repo"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "corpus-test")
    fork = _mb_commit(repo, "fork", _mb_root_files())
    _run_git(repo, "checkout", "-q", "-b", "feature")
    head = _mb_commit(repo, "pr", {"docs/pr.md": b"pr\n"})
    _run_git(repo, "checkout", "-q", "main")
    base = _mb_commit(
        repo,
        "main corpus",
        {"tests/golden_behavior/corpus.py": main_corpus, "docs/main.md": b"m\n"},
    )
    return repo, fork, base, head


@pytest.mark.parametrize(
    "main_corpus",
    [
        None,
        b"CASES = ()\n",
        b'CASES = (f"tests/contracts/test_{1}.py::test_witness",)\n',
        b'CASES = ("tests/contracts/" + "test_witness.py::test_witness",)\n',
    ],
    ids=["missing-at-base-tip", "zero-witnesses", "f-string", "concatenation"],
)
def test_main_moved_overlap_fails_closed_on_unverifiable_base_tip_corpus(
    tmp_path: Path, main_corpus: bytes | None
):
    repo, fork, base, head = _corpus_repo(tmp_path, main_corpus)
    with pytest.raises(ValueError, match="GOLDEN_CORPUS_UNVERIFIABLE"):
        trusted_anchor._main_moved_overlap(repo, fork, base, head)


def test_controller_records_unverifiable_corpus_reason(tmp_path: Path):
    history = _mb_history(tmp_path, "main_delete:tests/golden_behavior/corpus.py")
    with pytest.raises(ValueError, match="GOLDEN_CORPUS_UNVERIFIABLE") as caught:
        _mb_run_controller(history)
    record = trusted_anchor._controller_failure_record(caught.value)
    assert record["reason_code"] == "GOLDEN_CORPUS_UNVERIFIABLE"
    assert "GOLDEN_CORPUS_UNVERIFIABLE" in trusted_anchor.CONTROLLER_FAILURE_REMEDIES
    assert "GOLDEN_CORPUS_UNVERIFIABLE" in trusted_anchor._CONTROLLER_RECORDED_CODES


def test_corpus_absent_everywhere_contributes_no_witnesses(tmp_path: Path):
    repo = tmp_path / "no-corpus"
    subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
    _run_git(repo, "config", "user.email", "test@example.invalid")
    _run_git(repo, "config", "user.name", "corpus-test")
    fork = _mb_commit(repo, "fork", {"docs/a.md": b"a\n"})
    _run_git(repo, "checkout", "-q", "-b", "feature")
    head = _mb_commit(repo, "pr", {"docs/pr.md": b"pr\n"})
    _run_git(repo, "checkout", "-q", "main")
    base = _mb_commit(repo, "main", {"docs/main.md": b"m\n"})
    assert trusted_anchor._main_moved_overlap(repo, fork, base, head) == []


@pytest.mark.parametrize(
    ("path", "gated"),
    [
        # The quarantine package __init__ is loader code (exec_module, imported via
        # tests/conftest.py under NEXUS_NIGHTLY_QUARANTINE=1) and can xfail witnesses.
        ("tests/nightly_quarantine_items/__init__.py", True),
        ("tests/nightly_quarantine_items/tests_unit_test_orchestrator.py", False),
        ("scripts/ops/wiring_fixtures/codeintel/app/__init__.py", False),
    ],
)
def test_fixture_data_packages_are_not_import_chain_surface(path: str, gated: bool):
    assert trusted_anchor._is_gate_oracle_surface(path) is gated


def test_main_moved_over_quarantine_loader_fails_closed(tmp_path: Path):
    history = _mb_history(tmp_path, "main_touch:tests/nightly_quarantine_items/__init__.py")
    with pytest.raises(ValueError, match="MAIN_MOVED_OVER_GATE_SURFACE: merge origin/main"):
        _mb_run_controller(history)


@pytest.mark.parametrize(
    "source",
    [
        b"W = ()\n_c('GB-1', 't', 'c', 's', 'e', (), ('tests/a/test_b.py::t',) + W)\n",
        b"W = ()\n_c('GB-1', 't', 'c', 's', 'e', (), automated_tests=W + ('tests/a/test_b.py::t',))\n",
        b"_c('GB-1', 't', 'c', 's', 'e', (), list(('tests/a/test_b.py::t',)))\n",
        b"_c('GB-1', 't', 'c', 's', 'e', (), automated_tests=tuple(('tests/a/test_b.py::t',)))\n",
    ],
    ids=["positional-binop", "keyword-binop", "positional-call", "keyword-call"],
)
def test_automated_tests_binop_or_call_fails_closed(source: bytes):
    with pytest.raises(ValueError, match="automated_tests is not a literal"):
        trusted_anchor._golden_witness_paths(source)


def test_pr2071_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR2071_DEPENDENCY_SNAPSHOT_TRANSITION == (
        2071,
        (
            "fa6c8ebbfac872fc59715a035158ab05c3141fcd2df5363f35ac623d57decef1",
            "c00226cb36776992cb706c0b3d8727de67b3cdc28e1b9b92f95c89aac1c6d808",
            "55364183a2047573e0f32a423768596c7219ace8304f42a542613419b206949b",
            "12f4f793d1a0d5da8b337f879337fe8e4d2da0fe6876fd72339e416a8b9ebb20",
        ),
    )


def test_pr2071_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR2071_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=2071,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=2071,
                head_product_init_is_regular=True,
            )

    for other_pr in (2070, 2072):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_pr2108_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR2108_DEPENDENCY_SNAPSHOT_TRANSITION == (
        2108,
        (
            "55364183a2047573e0f32a423768596c7219ace8304f42a542613419b206949b",
            "12f4f793d1a0d5da8b337f879337fe8e4d2da0fe6876fd72339e416a8b9ebb20",
            "922c9abcdd9cd9b47b72cb8346253c065dc655f41573e4dc1dac0bd7a54c21fa",
            "cde189df08f2b389041432ad12b514b993b34421f5a6b4d2afb3f8214a980602",
        ),
    )


def test_pr2108_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR2108_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=2108,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=2108,
                head_product_init_is_regular=True,
            )

    for other_pr in (2107, 2109):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_pr2114_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR2114_DEPENDENCY_SNAPSHOT_TRANSITION == (
        2114,
        (
            "922c9abcdd9cd9b47b72cb8346253c065dc655f41573e4dc1dac0bd7a54c21fa",
            "cde189df08f2b389041432ad12b514b993b34421f5a6b4d2afb3f8214a980602",
            "ee385dc73e3f1a522bb8492fbc951ee7a4bbb437e3b4eb4222b0c90df816c649",
            "cde189df08f2b389041432ad12b514b993b34421f5a6b4d2afb3f8214a980602",
        ),
    )


def test_pr2114_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR2114_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=2114,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=2114,
                head_product_init_is_regular=True,
            )

    for other_pr in (2108, 2115):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_pr2122_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR2122_DEPENDENCY_SNAPSHOT_TRANSITION == (
        2122,
        (
            "ee385dc73e3f1a522bb8492fbc951ee7a4bbb437e3b4eb4222b0c90df816c649",
            "cde189df08f2b389041432ad12b514b993b34421f5a6b4d2afb3f8214a980602",
            "0f697d7eb658da44a9fa185d28af905f774d259171b32b34128d8e1424a4c1e4",
            "12f3261a4c5caf033b02e585cf972fe63e16dbc3221d04b0b26a14d41463c066",
        ),
    )


def test_pr2122_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR2122_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=2122,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=2122,
                head_product_init_is_regular=True,
            )

    for other_pr in (2121, 2123):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_lane_binding_missing_hint_names_the_agent_lane() -> None:
    hint = trusted_anchor.CONTROLLER_FAILURE_REMEDIES["MERGE_LANE_BINDING_MISSING"]
    assert "AGENT_INLINE" in hint
    assert "OWNER_INLINE" in hint
    assert "must not mint" not in hint


def test_pr2205_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR2205_DEPENDENCY_SNAPSHOT_TRANSITION == (
        2205,
        (
            "0f697d7eb658da44a9fa185d28af905f774d259171b32b34128d8e1424a4c1e4",
            "12f3261a4c5caf033b02e585cf972fe63e16dbc3221d04b0b26a14d41463c066",
            "90732f0ae715bb157fc028c5f6693588d63221abe94fbf2753e90574c863955f",
            "93d7a13d0b0e932d4a30612d6941d1940509e571cfeba2b33186a96bcdab1379",
        ),
    )


def test_pr2205_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR2205_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=2205,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=2205,
                head_product_init_is_regular=True,
            )

    for other_pr in (2204, 2206):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )


def test_pr2278_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.TRUSTED_PR2278_DEPENDENCY_SNAPSHOT_TRANSITION == (
        2278,
        (
            "90732f0ae715bb157fc028c5f6693588d63221abe94fbf2753e90574c863955f",
            "93d7a13d0b0e932d4a30612d6941d1940509e571cfeba2b33186a96bcdab1379",
            "61e302532d3f9c7c87601d0265629b827d3f40c9938c726fbce03c1d23d5e48e",
            "284a427af830b18981531fa02e2df191141081c2376bef6a349d479c393347b3",
        ),
    )


def test_pr2278_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\n", b"trusted lock\n", b"head pyproject\n", b"head lock\n"]
    hashes = trusted_anchor.TRUSTED_PR2278_DEPENDENCY_SNAPSHOT_TRANSITION[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number=2278,
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number=2278,
                head_product_init_is_regular=True,
            )

    for other_pr in (2277, 2279):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )
