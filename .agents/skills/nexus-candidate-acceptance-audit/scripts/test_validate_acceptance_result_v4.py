#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {filename}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


current = load("candidate_acceptance_v4_current", "validate_acceptance_result_v4.py")
legacy = load(
    "candidate_acceptance_v4_legacy",
    "validate_acceptance_result_v4_legacy_20260915.py",
)


class CandidateAcceptanceV4OrderingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.paths = [
            "README.md",
            "docs/EXTRACTION_STATUS.md",
            "docs/current-source-ownership.json",
        ]

    def entry(self, path: str) -> dict[str, object]:
        return {
            "path": path,
            "change_type": "MODIFY",
            "before_oid": "1" * 40,
            "after_oid": "2" * 40,
            "before_mode": "100644",
            "after_mode": "100755",
        }

    def manifest(self, ordered_paths: list[str]) -> dict[str, object]:
        return {
            "source_tree": "git-tree:" + "a" * 40,
            "target_tree": "git-tree:" + "b" * 40,
            "entries": [self.entry(path) for path in ordered_paths],
        }

    def test_current_order_matches_core_codepoint_order(self) -> None:
        self.assertEqual(
            current._canonical_manifest_path_order(self.paths.copy()),
            sorted(self.paths),
        )

    def test_historical_locale_order_remains_replayable_and_distinct(self) -> None:
        old = legacy._producer_locale_order(self.paths.copy())
        self.assertNotEqual(old, sorted(self.paths))
        self.assertEqual(
            old,
            [
                "docs/current-source-ownership.json",
                "docs/EXTRACTION_STATUS.md",
                "README.md",
            ],
        )

    def test_current_manifest_accepts_canonical_order(self) -> None:
        errors: list[str] = []
        self.assertTrue(
            current._validate_manifest(
                self.manifest(sorted(self.paths)),
                "a" * 40,
                "b" * 40,
                errors,
            )
        )
        self.assertEqual(errors, [])

    def test_current_manifest_rejects_legacy_locale_order(self) -> None:
        errors: list[str] = []
        self.assertFalse(
            current._validate_manifest(
                self.manifest(legacy._producer_locale_order(self.paths.copy())),
                "a" * 40,
                "b" * 40,
                errors,
            )
        )
        self.assertTrue(
            any(
                "canonical Unicode code-point lexical semantics" in error
                for error in errors
            )
        )

    def test_core_manifest_hash_uses_canonical_order(self) -> None:
        manifest = self.manifest(sorted(self.paths))
        rows = {row["path"]: row for row in manifest["entries"]}
        expected_value = [
            "nexus.core.git-change-manifest.v1-experimental",
            manifest["source_tree"],
            manifest["target_tree"],
            [
                [
                    rows[path]["path"],
                    rows[path]["change_type"],
                    rows[path]["before_oid"],
                    rows[path]["after_oid"],
                    rows[path]["before_mode"],
                    rows[path]["after_mode"],
                ]
                for path in sorted(self.paths)
            ],
        ]
        self.assertEqual(
            current.core_manifest_hash(manifest),
            current.core_value_hash(expected_value),
        )

    def test_missing_direct_evidence_fails_closed(self) -> None:
        errors, warnings = current.validate_physical(
            {"source": {}},
            SimpleNamespace(
                executor_evidence=None,
                verification_evidence=None,
                v3_validation_report=None,
            ),
        )
        self.assertEqual(warnings, [])
        self.assertEqual(
            errors,
            ["--executor-evidence is required for v4 physical binding"],
        )


if __name__ == "__main__":
    unittest.main()
