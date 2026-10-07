#!/usr/bin/env python3
from __future__ import annotations

import importlib.metadata as metadata
import json
import re
import sys

ALLOWED = {"nexus-learning", "nexus-runtime"}
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in ALLOWED:
        raise SystemExit("NEXUS_CORE_DEPENDENCY_ID_INVALID")
    name = sys.argv[1]
    dist = metadata.distribution(name)
    raw = dist.read_text("direct_url.json")
    if raw is None:
        raise SystemExit(f"NEXUS_CORE_DEPENDENCY_DIRECT_URL_MISSING:{name}")
    payload = json.loads(raw)
    commit = (payload.get("vcs_info") or {}).get("commit_id")
    if not isinstance(commit, str) or HEX40.fullmatch(commit) is None:
        raise SystemExit(f"NEXUS_CORE_DEPENDENCY_COMMIT_INVALID:{name}")
    print(f"git-commit:{commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
