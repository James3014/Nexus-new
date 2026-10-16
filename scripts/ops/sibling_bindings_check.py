#!/usr/bin/env python3
"""Bindings check for the sibling repos of Nexus-new (#2385).

Nexus-new runs ``scripts/ops/pr_preflight.py --only bindings``, which loads the
trusted lane gate from the target repo's own base commit. The sibling repos do
not carry that gate, so this script runs the same two validations with the
gate module from Nexus-new main (passed as ``--gate``, never from the PR):

* ``validate_issue_closure_intent``: a GitHub closing keyword (``Closes #N``)
  must be declared in a ``NEXUS_ISSUE_INTENT_V1`` block, so a merge never closes
  an Issue (e.g. a V12 sample) by accident;
* ``validate_final_merge_intent_binding``: the PR body, its intent block and the
  commit messages of the PR (merge-base..head) must agree.

Unlike Nexus-new, the ``NEXUS_CORE_ISSUE`` marker is not required here (not
every sibling repo runs the Core gate). Prints ``PASS  bindings: ...`` or
``FAIL  bindings [CODE]: ...`` and exits 0 only on PASS. Any error fails closed.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType


def _load_gate(path: Path) -> ModuleType:
    spec = importlib.util.spec_from_file_location("_sibling_trusted_gate", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load gate {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def _pr(repo_slug: str, number: int) -> dict:
    out = subprocess.run(
        ["gh", "api", f"repos/{repo_slug}/pulls/{number}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    return json.loads(out)


def run(args: argparse.Namespace) -> tuple[bool, str]:
    gate = _load_gate(Path(args.gate))
    pr = _pr(args.repo, args.pr)
    head = args.head
    if pr["head"]["sha"] != head:
        return (
            False,
            f"FAIL  bindings [HEAD_MOVED]: PR head is {pr['head']['sha'][:12]}, expected {head[:12]}",
        )
    body = pr.get("body") or ""
    base = _git(Path(args.repo_dir), "merge-base", args.base_ref, head)
    messages = gate._candidate_commit_messages(Path(args.repo_dir), base_sha=base, head_sha=head)
    try:
        intent = gate.validate_issue_closure_intent(body)
        gate.validate_final_merge_intent_binding(
            pr_body=body,
            pr_number=args.pr,
            head_sha=head,
            base_sha=base,
            expected_pr_number=args.pr,
            expected_head_sha=head,
            expected_base_sha=base,
            merge_method="squash",
            commit_title=pr.get("title"),
            commit_message=messages,
        )
    except Exception as exc:  # noqa: BLE001 - every gate error is a FAIL
        code = str(exc).split(":", 1)[0] or type(exc).__name__
        return False, f"FAIL  bindings [{code}]: {str(exc)[:300]}"
    return True, f"PASS  bindings: intents={intent['intents']}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").splitlines()[0] if __doc__ else None
    )
    parser.add_argument("--repo", required=True, help="owner/name of the PR's repository")
    parser.add_argument(
        "--repo-dir", required=True, help="checkout of that repo holding the PR head objects"
    )
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--head", required=True)
    parser.add_argument("--base-ref", required=True, help="e.g. origin/main")
    parser.add_argument(
        "--gate", required=True, help="path to trusted_merge_lane_gate.py from Nexus-new main"
    )
    args = parser.parse_args(argv)
    try:
        ok, line = run(args)
    except Exception as exc:  # noqa: BLE001 - fail closed
        ok, line = False, f"FAIL  bindings [{type(exc).__name__}]: {str(exc)[:300]}"
    print(line)
    return 0 if ok else 1


if __name__ == "__main__":
    os.environ.setdefault("GH_PROMPT_DISABLED", "1")
    sys.exit(main())
