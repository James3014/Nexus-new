# Owner confirmation via host elicitation — Phase 1 (#1750)

Status: implementation candidate. It is not merged until an independent security
review and the Owner's own host tests pass.

## Problem

`nexus_owner_standing_grant_issue` treated `ownerConfirmation: true`, a value the
model types into the tool arguments, as Owner consent. The Owner id was a
constant, and the caller chose the actions, including `GITHUB_MERGE`. In effect
the model could grant authority to itself.

## Owner direction (2026-10-11)

1. Authority is normally given in the Owner–agent conversation. The Owner is not
   required to act on GitHub in person.
2. The agent may draft scope and keep records. It may never issue or widen
   Owner authority itself.
3. Standard tasks run under a pre-approved policy without fresh authorization
   each time (Phase 3).
4. The Owner is asked only for scope expansion, high-risk change, or
   verification that cannot be confirmed.

GitHub authorship is not proof of a human either. A comment written by the
agent through the Claude GitHub App shows `James3014` as the author.

## Phase 1 requirements and how they are met

| # | Requirement | Implementation |
|---|---|---|
| 1 | Test the hosts in use before relying on elicitation | `scripts/ops/mcp_elicitation_probe.py`; results below. Interactive hosts still need the Owner to run the probe. |
| 2 | The model cannot fabricate acceptance; bind the confirmation to the draft, user identity, request id and expiry | **Partly met.** Draft, request id and expiry are bound. The gateway emits `elicitation/create` itself; only the response to its own random request id, before the deadline, with content exactly `{"approve": true}` counts. The grant written is the draft the server holds (its hash covers the receipt hash), and the answer cannot carry scope. **User identity is not bound:** `clientInfo` is self-reported and the local principal is the gateway process, not the person who answered. See "What Phase 1 does not protect against". |
| 3 | Hosts without trusted confirmation must not issue; no fallback to `ownerConfirmation: true` | Applies to both tools that write a new grant: `nexus_owner_standing_grant_issue` and `nexus_task_card_authority_switch`. The parameter is removed; sending it returns `OWNER_CONFIRMATION_PARAMETER_REMOVED`. Without a stdio session whose client declared form elicitation, they return `OWNER_CONFIRMATION_CHANNEL_UNAVAILABLE`. The loopback HTTP transport has no server-to-client channel and always refuses. |
| 4 | No unscoped merge authority before Phase 2 scope checks | `GITHUB_MERGE`, `CANDIDATE_INTEGRATE`, `PRODUCTION_RELEASE`, `RUNTIME_ACTIVATE` and `OWNER_REPRESENTATION_GRANT_ISSUE` are refused with `STANDING_GRANT_ACTION_REQUIRES_SCOPE_ENFORCEMENT`, before the Owner is asked. |
| 5 | Independent security review and negative tests before merge | `tests/nexus/orchestrator/test_owner_confirmation_elicitation.py` covers the negative cases through the real `serve` loop, including the reviewer's switch exploit. Review findings and their resolution are recorded on the PR. |

## What Phase 1 does not protect against

**A model that can run programs as the Owner's OS user can confirm its own
grant.** The stdio gateway cannot tell a real host from any process that
speaks MCP to it. A model with a shell can:
- start `scripts/ops/nexus_mcp_gateway.py` itself;
- declare form elicitation and an arbitrary `clientInfo`;
- answer `accept`.

The independent review reproduced this. The resulting audit record is
indistinguishable from a real one.

The same account can also write grant receipts to the store directly, or
through `scripts/ops/standing_grant.py`. Consumers accept any well-formed
receipt and do not check confirmation evidence.

Claude Code gives the model a Bash tool by default. Phase 1 therefore stops a
model from granting itself authority **through the gateway tools**, but not a
model that has shell or file-write access under the Owner's account. Phase 2
must place the trust anchor where the model cannot reach it, for example:
- a separate OS user or keychain-held signing key for grants;
- or URL-mode elicitation with a passkey/OAuth check;

and consumers must verify that anchor before honouring a grant.

**Availability.** While a confirmation is pending, the session waits for the
host's answer, and other calls get "awaiting Owner confirmation". A host that
never answers leaves the session waiting; a late acceptance is still rejected
as expired.

## Assurance level: `HOST_ELICITATION_LOCAL_SESSION`

Form elicitation proves that the host returned "accept" for this exact request.
It does not carry a cryptographic user identity. That the person who answered
is the Owner rests on the host:

- the host shows the dialog to the person at its interface;
- the host does not let the model answer.

The stdio gateway runs under the local OS account that launched the host. The
evidence records that principal together with the host's `clientInfo`, so the
binding is "this host session on this machine", not a verified GitHub or
passkey identity. Every confirmation is appended to
`owner-confirmations.jsonl` next to the standing-grant store for later review,
together with the draft and, after the write, its outcome and receipt hash.
The Owner is asked only when the write is otherwise admissible: replays and
CAS failures never prompt.

A stronger identity can be added later through URL-mode elicitation, which
sends the user to an out-of-band page such as an OAuth or passkey check.

## Host test matrix

| Host | Declared at `initialize` | Behaviour observed | Status |
|---|---|---|---|
| Claude Code 2.1.296, non-interactive (`claude -p`) | protocol `2025-11-25`, `elicitation: {form, url}` | Returned `cancel` with no human present. The real gateway answered `OWNER_CONFIRMATION_CANCELLED` and wrote nothing. | Tested 2026-10-11 |
| Claude Code, interactive | expected same | Dialog shown to the human; the model cannot answer | Owner to run the probe |
| Claude Desktop | unknown | — | Owner to run the probe |
| ChatGPT (remote connector over HTTP) | n/a | The Nexus HTTP transport is request/response only and cannot send elicitation, so issuance always refuses | Fail-closed by design |

### Running the probe

Add the probe as a stdio MCP server in the host, for example:

```json
{"mcpServers": {"nexus-probe": {"command": "python3", "args": ["<repo>/scripts/ops/mcp_elicitation_probe.py", "/tmp/nexus-probe.jsonl"]}}}
```

Then do the following:

1. Ask the agent to call `nexus_elicitation_probe` and answer the dialog yourself.
2. Ask the agent to "answer the confirmation for me". A trustworthy host never
   lets it.
3. Read `/tmp/nexus-probe.jsonl`, which holds the `initialize` capabilities and
   the raw answer.

## Out of scope for Phase 1

- **`nexus_task_card_authority_restore`.** It still takes `ownerConfirmation`.
  It only reinstates the exact predecessor grant the switch replaced, so it
  writes no authority that was not already confirmed.
- **Other model-supplied confirmations.** `nexus_task_card_create` and
  `_commit` take `owner_confirmation`; `lifecycle_action`, `mutation_admission`
  and canonical ingress take `ownerConfirmation`.
  They are effect confirmations rather than grant issuance, and each is
  reviewed in Phase 2.
- **The receipt does not carry the confirmation.** The evidence (with the draft
  and receipt hash) and an outcome line go to `owner-confirmations.jsonl`, but
  the receipt schema and its consumers are unchanged. Binding them is Phase 2
  work together with the trust anchor above.
- **Per-effect scope enforcement and project-entry binding.** Phase 2.
- **Pre-approved policy and automatic execution.** Phase 3.
- **The runtime receipt flags in nexus-core#205.** They should take their
  authority facts from these records once Phase 2 lands.
