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

## Why a check pinned to the approver App

A per-event check is not enough. GitHub tells a check who triggered *this*
event, not who pushed the commits. After an agent pushes, any later event by
someone else (an edit, a reopen, "Update branch") can re-evaluate the same head
as non-agent. Ordinary approvals are not enough either: the agent identity has
write access, so its own approval counts as soon as someone else pushed last.

The control is therefore a **status check pinned to the approver App and to
the exact head**:

1. The workflow `.github/workflows/owner-attestation-approver.yml` decides
   coverage with the trusted gate (`--mode approve`) in a job with no secrets.
2. A second job posts a check run named **`Owner grant`** on `head.sha`, as the
   approver App:
   - `success` only when an Owner-signed grant covers every change;
   - `failure` otherwise.
3. The ruleset on `main` requires `Owner grant` **from the approver App**.
   Nobody else, including the agent, can produce that check.
4. A new push is a new head with no `Owner grant` yet, so it cannot merge until
   it is decided again. There is no approval to dismiss and no race between
   push and approval.
5. Only the Owner can bypass the ruleset.

The decision looks only at content, never at who sent the event. It approves:
- only pull requests **authored by the granted agent**;
- only when the grant covers every changed path (defined below).

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
  - the allowed actions: 1–8 distinct upper-case names, which must include
    `GITHUB_MERGE`. The gate and the signer both refuse any other shape, so the
    Touch ID prompt always shows exactly what is signed;
  - 1–12 path globs, none starting with a wildcard;
  - issue and expiry time (at most 7 days);
  - a nonce.
- **Coverage checks.** `Owner grant` succeeds for a head only when the pull
  request was opened by the granted agent and all of these hold:
  - the key is pinned in `governance/owner-signing-keys.json` and the agent is
    listed in `governance/agent-identities.json`, both read **from the gate's own
    revision**;
  - the key is P-256;
  - the signature verifies through root-owned `/usr/bin/openssl`;
  - the grant is inside its window;
  - every changed path matches a signed glob, and none is protected.
- **Which paths count as changed.** The union of:
  - `diff(base.sha, head)`;
  - `diff(merge-base(main at the gate's revision, head), head)`.

  The second diff closes a stale-`base.sha` hole: a head built on an old main
  that would revert a newer protected change still shows that path as changed.
  If the history for the merge-base cannot be read, the PR is refused.
- **Protected paths.** No grant can cover these. This is a deny-list: it covers
  the files known to steer or run code on the Owner's machine, not every such
  file. Grant narrow paths.
  - `governance/**`, `.github/**`, `tasks/**`, `requirements/**`;
  - `scripts/ops/trusted_*`, `scripts/ops/owner_attestation.py`,
    `scripts/ops/__init__.py`;
  - `tools/owner-signer/**`;
  - `.claude/**` and `.mcp.json`, at any depth;
  - `AGENTS.md` and `CLAUDE.md`, at any depth;
  - `GEMINI.md`, `.cursorrules`, `.agents/**`, `.gemini/**`, `.vscode/**` and
    `conftest.py`, at any depth;
  - `.gitmodules`, `.gitattributes`, `.nexus-core/**`, `.cargo/**`;
  - `MUSE_PROTO.md`, `pyproject.toml`, `uv.lock`.
  - `docs/governance/**` and `docs/testing/test_impact_map.md`;
  - this gate's own tests: `tests/ops/test_owner_attestation_gate.py` and
    `tests/ops/test_trusted_*`.
- **The per-event lane check.** The trusted merge-lane gate also refuses
  agent-sent events without a valid grant. This is only an extra signal; the
  required `Owner grant` check is what decides merges.
- **Missing trust files.** If either trust file is missing at the gate's
  revision, every PR is refused.

## Owner setup

1. **Signing key on the Mac.**

   ```sh
   cd tools/owner-signer && swift build -c release
   sudo install -o root -g wheel -m 0755 .build/release/owner-signer /usr/local/bin/
   owner-signer init > ~/owner.pem                     # key_id on stderr
   python scripts/ops/owner_attestation.py pin --public-key ~/owner.pem
   ```

   Install the signer root-owned. On some Macs `/usr/local/bin` is
   user-writable, so it must be the `sudo install -o root` copy that you run.
   Put the printed entry into `governance/owner-signing-keys.json` in a pull
   request that you open and merge yourself.

2. **Agent identity.** Create a bot account, or a GitHub App, for the agent.
   - Give it contents and pull-request write access only.
   - Do **not** give it the Workflows permission, so it cannot push files under
     `.github/workflows/` and run arbitrary workflows.
   - Do **not** give it admin or bypass rights.
   - List its login in `governance/agent-identities.json`. For an App, list the
     login as it appears in events, `<slug>[bot]`.
   - Agents get this identity's token, never yours.

3. **Approver App.** Create a separate GitHub App with only **"Checks: read and
   write"**, installed on this repository.
   - Create an environment named `owner-grant-approver`, restricted to the `main`
     branch.
   - Store the App ID as the environment secret `NEXUS_APPROVER_APP_ID`.
   - Store the App's private key as the environment secret
     `NEXUS_APPROVER_PRIVATE_KEY`.
   - Without them the approver posts nothing, and agent pull requests cannot
     merge.

4. **Ruleset on `main`.**
   - Require a pull request.
   - Require the status check `Owner grant`, with its source set to the approver
     App.
   - Require the existing trusted checks.
   - Bypass list: the Owner only.
   - Then verify it once: open a small agent pull request covered by a grant and
     confirm that it becomes mergeable only after `Owner grant` succeeds, and
     that a further push makes it unmergeable again.
   - Also confirm that a check run named `Owner grant` posted by any other
     source (for example a workflow using `GITHUB_TOKEN`) does **not** satisfy
     the rule.
   - Confirm that the `owner-grant-approver` environment refuses a job from a
     branch other than `main`.

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
  - Run the signer only from the root-owned copy installed with
    `sudo install -o root`.
- **The signer has not been built or run.** It needs macOS with a Secure Enclave
  and was written without access to one. Test `init`, `pubkey` and `sign` on the
  Mac before pinning the key.
- **The approver workflow has not run on GitHub yet.** Local checks:
  - YAML and shell syntax;
  - JWT construction;
  - a simulated run of the decide job against a local repository.

  The GitHub API calls and the ruleset's handling of the App-pinned check run
  only once the App, the environment and the ruleset exist. That is what the
  verification in setup step 4 is for.
- **Validity is checked when the check is posted, not at merge time.** A head
  whose `Owner grant` succeeded stays mergeable after `expires_at`, until a new
  push.
- **A success belongs to a commit, not to a pull request.** If a branch is
  force-pushed back to a head that was already decided `success`, or a second
  pull request uses the same head, that earlier check still counts. Its
  decision was made against the base of that moment, so revoke a grant by
  closing the pull request, not only by letting it expire.
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
