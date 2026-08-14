# Issue #111 Option B — NightShift bounded candidate queue

- Baseline: `069596056fff852bad8c826725902d25361aa9c7`
- Authority: Owner-selected applicable OpenCode L1 path; bounded implementation only.
- Status: COMPLETE / TERMINAL_RECONCILIATION; `AUTO_CHAIN=false`.
- Frontier: `01-queue-contract.md`
- Forbidden: provider/model selection, second router/queue, approval, integration, release, #191/#143.
- Terminal marker: `NIGHTSHIFT_OPTION_B_QUEUE_CONSUMER_PROVEN`
- Claim ceiling: `NIGHTSHIFT_OPTION_B_QUEUE_CONSUMER_PROVEN_ONLY`
- Bound identities:
  - Implementation PR #220 (Option B), merged 2026-08-13.
  - PR base: `2c820eab67669ab63297bf76fcf1751aaa9496ba`
  - PR head: `da426a0d170a662048cc0a226e181153ddd00585` (branch `codex/issue-111-optionb`)
  - PR merge: `587aa4b1d6026dc85efe35930f2067fbd1ead3cc`
  - Exact scope: 8 files (+698/-117): `nexus/app/nightshift_runner_service.py`, `nexus/services/nightshift_queue_consumer.py`, `scripts/nightshift.py`, `tests/services/test_nightshift_queue_consumer.py`, `tests/ops/test_issue111_nightshift_impact_map.py`, `docs/testing/test_impact_map.md`, this campaign INDEX, `01-queue-contract.md`.
  - Head required checks: 6/6 SUCCESS (Pytest 396, Ruff 390, Pyright 390, Bandit 390, Policy Lane 80, Wiki 390).
  - Current main readback (`eb668fb76f0c30d8f025db42cdb8e320d556c037`): producer/consumer present; 7 focused consumer tests present.
