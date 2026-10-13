"""Nightly quarantine entry: tests/ops/test_issue_821_core_namespace_retirement.py (#1929). See package docstring."""

from __future__ import annotations

ENTRY: dict[str, object] = {
    "file": "tests/ops/test_issue_821_core_namespace_retirement.py",
    "disposition": "quarantine-product-bug?",
    "issue": "#1929",
    "cause": 'fails in isolation: #1972 (741c3d187, Refs #1929) added {include = "product"} to [tool.poetry].packages to satisfy tests/product/test_robustness.py::test_poetry_packages_include_product_without_version_change, which contradicts the #821 namespace retirement asserted here (wheel must not ship product/); the two tests are mutually exclusive, owner packaging decision pending',
    "tests": ("test_legacy_wheel_releases_product_namespace_and_duplicate_certify_cli",),
}
