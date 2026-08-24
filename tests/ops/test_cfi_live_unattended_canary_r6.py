"""Live unattended CFI evidence canary (r4).

This PR exists only to produce one material terminal CI failure on the exact
current main lineage so the nexus-opencli-reviewer daemon can naturally
detect it, fingerprint it, diagnose it semantically and publish its
PRE_REVIEW advisory. The PR will be closed without merging once the full
CFI chain is verified; the assertion below is intentionally false.
"""


def test_cfi_live_unattended_canary_r4():
    assert False, "intentional CFI live canary failure for reviewer evidence chain"
