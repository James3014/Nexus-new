# Nexus-new #1705: physical consumer canary after Core #142 rollout

This disposable pull request tests the actual default-branch-owned Nexus Core
issue-gate and receipt-verify composite actions after Nexus-new PR #1709
installed immutable Core revision `77c7fb8fdc8c68a85c771280decd4a1e01b55085`.

The tested Nexus-new main is `d565535fb99eeb58f077a10277f7d4b327043af4`.
No production code, gate, trust policy, dependency, or Core pin is modified
by this fixture. The PR must **not** be merged.

Acceptance evidence: the two-job `Nexus Core issue completion` run must use
the merged Core revision, upload a signed receipt with an artifact name
including the actual PR-head SHA, workflow run ID and producing attempt,
carry the canonical producer `artifact-id` to the verifier, use by-ID
download, verify Sigstore GitHub workflow identity, and pass all nine
`nexus-certify receipt-check` expectations. After success, retain the
GitHub run and artifact IDs, close the fixture **without merging**, and
only then reconcile Nexus-new #1705 and nexus-core #142.
