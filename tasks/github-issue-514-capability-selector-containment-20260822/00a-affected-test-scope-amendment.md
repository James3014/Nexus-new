# TASK-514-001 Amendment A — affected legacy test semantics

- **Authority:** Issue #514 contract-delta comment `5381105345`
- **Applies to:** `TASK-514-001`
- **Reason:** RED evidence showed `tests/research/test_capability_selector.py` directly encodes the obsolete independent-selector behavior being removed by #514.
- **Scope delta:** add `tests/research/test_capability_selector.py` to the allowed test-edit set only.
- **Production scope delta:** none.
- **Requirement/acceptance delta:** none; this is same-contract affected-regression closure for REQ-001/REQ-002/REQ-003 and AC-004.
- **Maximum touched test files:** 5.
- **Claim ceiling:** unchanged: `LEGACY_CAPABILITY_SELECTOR_AUTHORITY_CONTAINED_AT_SOURCE`.
- **Auto-chain:** `false`.

The test update must remove expectations that `CapabilitySelector` independently chooses capabilities or fabricates successful `SkillSlot.used`; it must replace them with assertions that canonical selection authority is `CapabilityPlanner`, compatibility projection is bounded by the verified alias map, and non-executed skill slots remain truthful.
