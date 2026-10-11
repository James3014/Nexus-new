# Owner-signed grants for agent pull requests — Phase 2 (#1750)

Status: implementation candidate. It stays inactive until the Owner completes
the setup below.

## Why the enforcement point is GitHub

Phase 1 showed that a model with a shell under the Owner's OS account can bypass
anything enforced on that machine. It can:
- use the Owner's git and GitHub credentials directly;
- edit the local Nexus code;
- act as the MCP host.

Phase 2 therefore enforces where the agent cannot write, on GitHub:
- in branch rules;
- in trusted workflows that run code from the default branch, never from the pull
  request.

## Why approval, not a status check

A per-event check is not enough. GitHub tells a check who triggered *this* event,
not who pushed the commits. The independent review showed the gap: after an
agent pushes, any later event by someone else (an edit, a reopen, "Update branch")
can re-evaluate the same head as non-agent and turn the check green.

The control is therefore an **approval pinned to the exact head**:

1. The repository ruleset on `main` requires:
   - one approving review;
   - **dismissal of stale approvals** when new commits are pushed;
   - **approval of the most recent reviewable push** by someone other than the
     pusher.
2. Only the Owner can bypass these rules.
3. A dedicated **approver GitHub App** approves a head only when the workflow
   `.github/workflows/owner-attestation-approver.yml` finds an Owner-signed grant
   that covers it.
4. Any new push dismisses that approval and the decision is taken again for the
   new head.

The approval decision (`trusted_merge_lane_gate.py --mode approve`) looks only at
content: the signed grant and the changed paths. It never looks at who sent the
event.

## How a grant works

- **Signing.** `tools/owner-signer` keeps a P-256 key inside the Mac's Secure
  Enclave. Every signature needs a fresh Touch ID check. The prompt shows:
  - Owner, agent, actions, repository and Issue;
  - every path;
  - the validity window, parsed from the exact bytes being signed.
- **Grant contents.** A grant names:
  - repository and Owner;
  - the agent's login;
  - one Issue;
  - the allowed actions (must include `GITHUB_MERGE`);
  - 1–12 path globs, none starting with a wildcard;
  - issue and expiry time (at most 7 days);
  - a nonce.
- **Approval checks.** The approver approves a head only when all of these hold:
  - the key is pinned in `governance/owner-signing-keys.json` and the agent is
    listed in `governance/agent-identities.json`, both read **from the gate's own
    revision**;
  - the key is P-256;
  - the signature verifies through root-owned `/usr/bin/openssl`;
  - the grant is inside its window;
  - every changed path matches a signed glob, and none is protected.
- **Protected paths.** No grant can cover these:
  - `governance/**`, `.github/**`, `tasks/**`, `requirements/**`;
  - `scripts/ops/trusted_*`, `scripts/ops/owner_attestation.py`,
    `scripts/ops/__init__.py`;
  - `tools/owner-signer/**`;
  - `.claude/**` and `.mcp.json`, at any depth;
  - `AGENTS.md` and `CLAUDE.md`, at any depth;
  - `MUSE_PROTO.md`, `pyproject.toml`, `uv.lock`.
- **The per-event lane check.** The trusted merge-lane gate also refuses
  agent-sent events without a valid grant. This is an extra signal; the approval
  rule above is what decides merges.
- **Missing trust files.** If either trust file is missing at the gate's
  revision, every PR is refused.

## Owner setup

1. **Signing key on the Mac.**

   ```sh
   cd tools/owner-signer && swift build -c release
   cp .build/release/owner-signer /usr/local/bin/      # outside any repo
   owner-signer init > ~/owner.pem                     # key_id on stderr
   python scripts/ops/owner_attestation.py pin --public-key ~/owner.pem
   ```

   Put the printed entry into `governance/owner-signing-keys.json` in a pull
   request you open and merge yourself.

2. **Agent identity.** Create a bot account, or a GitHub App, for the agent.
   - Give it contents and pull-request write access only.
   - Do **not** give it the Workflows permission, so it cannot push files under
     `.github/workflows/` and run arbitrary workflows with secrets.
   - Do **not** give it admin or bypass rights.
   - List its login in `governance/agent-identities.json`. For an App, list the
     login as it appears in events, `<slug>[bot]`.
   - Agents get this identity's token, never yours.

3. **Approver App.** Create a separate GitHub App with only "Pull requests: read
   and write", installed on this repository.
   - Store its ID as the secret `NEXUS_APPROVER_APP_ID`.
   - Store its private key as the secret `NEXUS_APPROVER_PRIVATE_KEY`.
   - Without them the approver does nothing.

4. **Ruleset on `main`.**
   - Require pull requests with one approval, dismissal of stale approvals, and
     approval of the most recent push.
   - Require the trusted checks.
   - Bypass list: the Owner only.

5. **Granting work.**

   ```sh
   python scripts/ops/owner_attestation.py draft --agent <agent-login> --issue <N> \
       --path 'nexus/orchestrator/**' --hours 24 --out grant.json
   owner-signer sign grant.json > grant.sig                     # Touch ID
   python scripts/ops/owner_attestation.py assemble --payload grant.json \
       --signature grant.sig --public-key ~/owner.pem
   ```

   Paste the printed block into the agent's pull request body.

## Limits (read before relying on this)

- **The agent must not run under your OS account with your credentials.** It must
  run in a separate OS account, a VM or a cloud session, with only its own
  identity's token. Otherwise it can use your token directly.
  - It can also replace the signer binary or `grant.json`.
  - It can call the Secure Enclave key with its own prompt text. Touch ID then
    proves only that a finger was presented, not what was approved.
  - Run the signer from a location the agent cannot write, such as
    `/usr/local/bin` installed by you.
- **The signer has not been built or run.** It needs macOS with a Secure Enclave
  and was written without access to one. Test `init`, `pubkey` and `sign` on the
  Mac before pinning the key.
- **The approver workflow has not run on GitHub yet.** It was checked locally (YAML,
  shell syntax, JWT construction, the decision logic), but the GitHub API calls
  only run once the App and secrets exist.
- **Validity is checked when the approval is given, not at merge time.** An
  approved head stays approved after `expires_at` until a new push dismisses it.
- **Issue binding is weak.** The Issue is matched against markers in the pull
  request body, which the agent writes. Treat a grant as reusable within its
  paths and window, and keep windows short.
- **Owner merges are not restricted.** As the bypass actor, you can always merge.
  Make sure only you hold bypass.
- **Cloud sessions cannot sign.** By Owner decision they only use grants signed on
  the Mac.
- **Still open for a later phase.**
  - The local gateway's grant tools.
  - `task_card_authority_switch` and `task_card_authority_restore`.
  - The other model-supplied confirmations in `OWNER_CONFIRMATION_PHASE1.md`.
