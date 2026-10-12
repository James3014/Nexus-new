#!/usr/bin/env python3
"""Offline-only audit of GitHub main ruleset snapshot invariants.

This is a diagnostic checker, never a permission, issuer or merge authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CONTEXT = "Nexus Core issue completion"
TRUSTED_APP_ID = 15368


def evaluate(snapshot: object) -> list[str]:
    if not isinstance(snapshot, dict):
        return ["INVALID_SNAPSHOT"]
    failures = []
    if snapshot.get("enforcement") != "active":
        failures.append("RULESET_NOT_ACTIVE")
    if snapshot.get("bypass_actors") != []:
        failures.append("BYPASS_ACTORS_PRESENT")
    if snapshot.get("target") != "branch" or not isinstance(snapshot.get("conditions"), dict):
        failures.append("INVALID_BRANCH_TARGET")
    else:
        refs = snapshot["conditions"].get("ref_name")
        if not isinstance(refs, dict) or not ({ "~DEFAULT_BRANCH", "refs/heads/main" } & set(refs.get("include", []))) or "refs/heads/main" in refs.get("exclude", []):
            failures.append("DEFAULT_BRANCH_NOT_INCLUDED")
    rules = snapshot.get("rules")
    if not isinstance(rules, list):
        rules = []
    if not any(isinstance(rule, dict) and rule.get("type") == "pull_request" for rule in rules):
        failures.append("PULL_REQUEST_RULE_MISSING")
    checks = []
    for rule in rules:
        if isinstance(rule, dict) and rule.get("type") == "required_status_checks":
            params = rule.get("parameters")
            if isinstance(params, dict) and isinstance(params.get("required_status_checks"), list):
                checks.extend(params["required_status_checks"])
    core_checks = [check for check in checks if isinstance(check, dict) and check.get("context") == CONTEXT]
    if not core_checks:
        failures.append("CORE_CHECK_MISSING")
    elif any(check.get("integration_id") is None for check in core_checks):
        failures.append("CORE_CHECK_ISSUER_UNBOUND")
    elif len(core_checks) != 1 or type(core_checks[0].get("integration_id")) is not int or core_checks[0]["integration_id"] != TRUSTED_APP_ID:
        failures.append("CORE_CHECK_WRONG_ISSUER")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="+", help="Local JSON snapshots; never fetched or changed")
    args = parser.parse_args(argv)
    results = []
    for name in args.snapshots:
        try:
            content = json.loads(Path(name).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError):
            violations = ["SNAPSHOT_UNREADABLE"]
        else:
            violations = evaluate(content)
        results.append({"path": name, "status": "FAIL" if violations else "PASS", "reason_codes": violations})
    failed = any(row["status"] == "FAIL" for row in results)
    print(json.dumps({"status": "FAIL" if failed else "PASS", "snapshots": results}, sort_keys=True))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
