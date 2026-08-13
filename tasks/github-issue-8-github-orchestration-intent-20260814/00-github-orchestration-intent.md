# M4 GitHub orchestration intent

Objective: produce a deterministic `MERGE_INTENT` evidence object without
granting mutation authority. A valid standing-grant pre-merge action yields
`GRANT_MATCH`; a `GITHUB_MERGE` evaluation yields
`OWNER_MERGE_SLOT_REQUIRED` and remains non-authorizing.

No network, subprocess, GitHub API, lifecycle, governance, route, or workforce
side effects are permitted. Inputs are protocol/test doubles only.
