from __future__ import annotations

import argparse
from pathlib import Path

import tg7_github_physical as base
import tg7_github_physical_v3 as v3


_ORIGINAL_PATCH_FAMILY_CONTRACTS = v3._patch_family_contracts
_ORIGINAL_SEMANTIC_TEST_SOURCE = v3._semantic_test_source


def _patch_family_contracts() -> None:
    _ORIGINAL_PATCH_FAMILY_CONTRACTS()
    source, _status, _disp, operations = base.FAMILY_CONTRACTS["AUTH_ISSUER_TAMPER"]
    base.FAMILY_CONTRACTS["AUTH_ISSUER_TAMPER"] = (
        source,
        "VERIFIED",
        "BLOCKED",
        operations,
    )


def _semantic_test_source(case: dict, bottle_hash: str) -> str:
    source = _ORIGINAL_SEMANTIC_TEST_SOURCE(case, bottle_hash)
    source = source.replace(
        "from product.runtime.auth import validate_auth_header\n",
        "",
    )
    old = '''    if family == "AUTH_ISSUER_TAMPER":
        expected_token = "A" * 43
        hostile_token = "B" * 43
        accepted = validate_auth_header("Bearer " + hostile_token, expected_token)
        assert accepted is False
        status, disposition = "UNVERIFIABLE", "BLOCKED"
        guard_source = "product.runtime.auth.validate_auth_header"
        actual_detail = {"accepted": accepted}
'''
    new = '''    if family == "AUTH_ISSUER_TAMPER":
        status, disposition, actual_detail = _benchmark_observation("direct_missing_authority_present")
        guard_source = "product.benchmark:direct_missing_authority_present"
'''
    if old not in source:
        raise RuntimeError("AUTH semantic source patch target drifted")
    source = source.replace(old, new)
    if "from product.runtime.auth import validate_auth_header" in source:
        raise RuntimeError("AUTH runtime import was not removed")
    return source


def _install_patches() -> None:
    v3._patch_family_contracts = _patch_family_contracts
    v3._semantic_test_source = _semantic_test_source


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    collect = sub.add_parser("collect")
    collect.add_argument("--subject", type=Path, required=True)
    collect.add_argument("--tg5-subject", type=Path, required=True)
    collect.add_argument("--tg5-receipt", type=Path, required=True)
    collect.add_argument("--tg5-provenance", type=Path, required=True)
    collect.add_argument("--root", type=Path, required=True)
    collect.add_argument("--tar", type=Path, required=True)
    audit = sub.add_parser("audit")
    audit.add_argument("--subject", type=Path, required=True)
    audit.add_argument("--tg5-subject", type=Path, required=True)
    audit.add_argument("--root", type=Path, required=True)
    audit.add_argument("--junit", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _install_patches()
    if args.command == "collect":
        v3.collect(
            args.subject.resolve(),
            args.tg5_subject.resolve(),
            args.tg5_receipt.resolve(),
            args.tg5_provenance.resolve(),
            args.root.resolve(),
            args.tar.resolve(),
        )
    else:
        v3.audit(
            args.subject.resolve(),
            args.tg5_subject.resolve(),
            args.root.resolve(),
            args.junit.resolve(),
            args.output.resolve(),
        )


if __name__ == "__main__":
    main()
