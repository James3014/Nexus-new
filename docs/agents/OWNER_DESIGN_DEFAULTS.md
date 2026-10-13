---
artifact_authority: advisory_guidance_only
owner: James Chen
status: active
purpose: Design defaults distilled from past Owner choices, consulted before asking the Owner to pick between design options.
---

# Owner Design Defaults

This file grants nothing and selects nothing. It is guidance only; an entry is
not authority. It does not authorize or select a lane, route, capability,
worker or model. It does not count as admission, review, acceptance, merge,
release or production evidence. Do not cite it as an Owner confirmation or
store it as an authorization or receipt. No code, script, workflow or tool may
read this file or its ids as a flag or boolean. AGENTS.md,
current_operating_mode.yaml, the active Task Card and the Issue contract always
take precedence over it.

## How to use

1. You face a design choice with two or more options, and a lane is already
   authorized for the work. Look up the Active entries first.
2. If an entry's scope matches and none of the universal ask triggers or the
   entry's `ask_anyway_if` lines apply, pick the default and continue (Active entries only).
3. Visibility rule: an agent that applies a default writes
   `Design default applied: DD-xx (reason)` in the PR body, so the Owner can
   override it at merge. A default applied silently is a defect.
4. If no entry matches, or entries conflict, ask the way you do today: give
   the options and a recommendation.

Universal ask triggers. Always ask if any of these apply; they are copied from
AGENTS.md and never relaxed here:
- contract widening
- weaker security, or removing, demoting or narrowing any check or gate
- a new irreversible external effect
- release or production claims
- lane, route or Workforce choice
- a change to a scientific or experiment contract
- a budget, quota or new account
- any change to this file

## Entries (Active)

- id: DD-01
  rule: Keep pinned identities (uv.lock/OCI digest, PROFILE_HASH, persisted receipt or hash formats) unchanged. Prefer a fix that avoids touching them (stdlib instead of a new dependency, leave the pinned format and document it).
  scope: nexus-core, Nexus-new code and test changes
  sources: nexus-core#174, #1730, nexus-core#168, nexus-core#169, #1693/PR #1723
  ask_anyway_if: the pinned value is itself the bug, an Issue requires the dependency or migration, or the change touches .nexus-core/config.toml

- id: DD-02
  rule: Do not delete code. Retire it in place: deprecation warning, lab-only marker, or a script stub that exits non-zero with a notice.
  scope: dead or unreachable modules and scripts
  sources: #1740/PR #1743, PR #1787, nexus-core#148
  ask_anyway_if: the retirement changes a capability inventory or a sealed claim, or the Issue explicitly requires deletion

- id: DD-03
  rule: Report what was measured. Use UNVERIFIED, NOT_MEASURED or NOT_RUN instead of PASS. A failure exits non-zero. Synthetic or simulated evidence is flagged and kept out of metrics.
  scope: CLIs, status reports, verifiers, benchmarks
  sources: PR #1827, PR #1840, #1733 decision #4, nexus-core#156 (b), #1763/PR #1767
  ask_anyway_if: a required CI gate or an external contract consumes the old value (as in #1763, where the PASS label was kept)

- id: DD-04
  rule: Keep the always-loaded AGENTS.md 12,000-byte guard fixed. Make room by moving text verbatim into on-demand docs. On-demand docs get growth caps (current size plus about 10%), enforced on every PR through Golden.
  scope: agent instruction and context budgets
  sources: PR #1864 (B), PR #1883 (C), PR #1859
  ask_anyway_if: raising the AGENTS.md cap, a cap increase above about 10%, or removing a rule rather than moving it

- id: DD-05
  rule: When an instruction or overlay file is broken, restore the Owner's original text verbatim from the canonical source. Do not write new wording or point at a mixed or derived copy.
  scope: bootstrap and overlay text files
  sources: PR #1855 (A), PR #1859 ("restored original wording"); Owner confirmed in chat 2026-10-14
  ask_anyway_if: the original cannot be obtained byte-for-byte, or the restored text would change what is authorized

- id: DD-06
  rule: For a hardening finding with no independent exploit, where the fix would need a new trust mechanism or a format migration, document the trust assumption and add a pinning test. Do not build the mechanism.
  scope: nexus-core and Nexus-new audit findings
  sources: nexus-core#163 (c), nexus-core#169 (a), nexus-core#168 (A); Owner confirmed in chat 2026-10-14
  ask_anyway_if: the finding is exploitable, or the remedy removes or relaxes an existing check

- id: DD-07
  rule: Any change to an execution or experiment identity (dispatcher hash, model, runtime pin) gets a new label or generation. Never relabel, reuse or substitute in place.
  scope: experiment generations, canaries, worker identities
  sources: #1216 comment 6094518130 (option b), PR #1744 D1, #29 decision 1, PR #1857
  ask_anyway_if: always ask which identity to use; this entry only says how to record a change

- id: DD-08
  rule: A protocol loss excludes only the affected item. Reset a whole generation only for identity drift or a systematic defect over a threshold agreed in advance.
  scope: research cohorts and replication runs
  sources: PR #1744 D2, #1216 comment 6136359049, #1655 Amendment 1
  ask_anyway_if: the threshold was not agreed in advance, or the reset discards sealed results

- id: DD-09
  rule: Fix pre-registered parameters and classification rules before scoring. Do not tune them after seeing results; report their effect instead.
  scope: experiments
  sources: #1655 Amendment 1 ("Rule from now on"), #1196 comments 6068109283 and 6124280776
  ask_anyway_if: an amendment is needed after output exists

- id: DD-10
  rule: When natural data is slow to accumulate, use a frozen external benchmark with a lower claim ceiling. Do not wait for N natural tasks.
  scope: research evidence gathering
  sources: #1196 comment 6119832474, #1196 comment 6124280776 ("do not revert to waiting")
  ask_anyway_if: the change alters the claim, the cohort, the budget or the run contract

- id: DD-11
  rule: For a model revision within an established lineage, do the minimum delta requalification. Do not restart calibration from scratch.
  scope: Workforce capability evidence planning (not admission)
  sources: #569 comment 5902919200 ("Do not restart calibration"); Owner confirmed in chat 2026-10-14
  ask_anyway_if: there is evidence of a material change, or admission itself would change

- id: DD-12
  rule: Ship a new drift or health control as read-only detection and alerting first. Run new and old checks side by side. Leave the remedy (rebind, reload, ruleset switch) to its owning path.
  scope: ops checks, CI gates, Gateway drift
  sources: #1900 (Owner decision), #1898, #1754, #49
  ask_anyway_if: always ask before switching, demoting or narrowing an enforcing gate

- id: DD-13
  rule: Every fail-closed error message prints the exact remedy, for example the rebase target or the expected marker line.
  scope: gates, validators, CLIs
  sources: nexus-core#243, #1900, #1898
  ask_anyway_if: never (diagnostics only)

- id: DD-14
  rule: Ship the part that is neutral to authority. Leave the part that depends on authority open, linked to its owning Issue. Do not implement ahead of an undecided authority source.
  scope: Issues that mix authority-neutral and authority-dependent work
  sources: nexus-core#233, #1761/PR #1888 with #1886, #1898
  ask_anyway_if: always ask about the deferred part

- id: DD-15
  rule: When an optional input is unavailable on a path that is not a security path, degrade visibly (a warning plus a typed reason such as constraints_source=unavailable). Do not hard-fail or return a silent empty value.
  scope: memory, learning and advisory wiring
  sources: #1733 decision #1 ("先不擋"), PR #1799, PR #1813, #1763 item 3; Owner confirmed in chat 2026-10-14
  ask_anyway_if: the path is a security, admission or verification gate (those stay fail-closed)

- id: DD-16
  rule: When two surfaces disagree, align the docs or the secondary surface to the higher-authority file or to the behaviour already in use.
  scope: docs vs code, CLI vs Action, overlay vs AGENTS.md
  sources: nexus-core#156 (b), PR #1787 (Belief edge direction), #1761 (overlay aligned to AGENTS.md)
  ask_anyway_if: the behaviour in use is the bug, or aligning would widen a contract

## Pending Owner confirmation — not active

No pending entries. Agents must not apply anything added here. An entry moves
to Active only through an Owner-confirmed PR.
