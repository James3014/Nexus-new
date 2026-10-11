# Owner-signed grants for agent pull requests — Phase 2 (#1750)

Status: implementation candidate. The CI enforcement is complete and tested; it
stays inactive until the Owner completes the setup steps below.

## Why the enforcement point is GitHub

Phase 1 showed that a model with a shell under the Owner's OS account can bypass
anything enforced on that machine. It can:
- use the Owner's git and GitHub credentials directly;
- edit the local Nexus code;
- act as the MCP host.

A local check therefore cannot hold. Phase 2 enforces where the model cannot
write: the trusted merge-lane gate. CI runs this gate from the base branch, so a
pull request cannot change the code that judges it.

## How it works

1. **The agent works under its own GitHub identity.** That identity (a bot
   account or GitHub App) is listed in `governance/agent-identities.json`.
2. **The Owner signs grants with Touch ID.**
   - `tools/owner-signer` keeps a P-256 key inside the Mac's Secure Enclave.
   - Every signature needs a fresh biometric check.
   - The prompt shows the grant summary, parsed from the exact bytes being signed.
3. **The grant is a signed scope.** It names:
   - repository and Owner;
   - the agent's login;
   - one Issue;
   - the allowed actions (must include `GITHUB_MERGE`);
   - the allowed path globs;
   - issue and expiry time (at most 7 days);
   - a nonce.
4. **The gate enforces it.** When the agent authored the pull request, or sent
   the event, the gate requires one `NEXUS_OWNER_ATTESTATION_V1` block in the PR
   body and checks all of the following:
   - **Signature:** the key is pinned in `governance/owner-signing-keys.json` *on
     the base revision*, the key is P-256, and the signature verifies through
     root-owned `/usr/bin/openssl`.
   - **Grant contents:** repository, Owner and agent match; the Issue is one the
     PR is bound to; `GITHUB_MERGE` is granted; the grant is inside its validity
     window.
   - **Changed paths:** every path the PR changes matches a signed glob.
   - **Protected paths:** no changed path is under `governance/**`, `.github/**`,
     `scripts/ops/trusted_*`, `AGENTS.md` or `CLAUDE.md`. No grant can cover these.
5. **Pull requests without agent involvement are unaffected.**

### Default state

- **Fail closed.** With no pinned key, every agent pull request is refused.
- **Inactive until configured.** With no agent identity listed, nothing changes.
  The repository ships with both lists empty.

## Owner setup

1. **Build the signer on the Mac and create the key.**

   ```sh
   cd tools/owner-signer && swift build -c release
   .build/release/owner-signer init > ~/owner.pem   # prints key_id on stderr
   ```

2. **Pin the public key.**

   ```sh
   python scripts/ops/owner_attestation.py pin --public-key ~/owner.pem
   ```

   Add the printed entry to `governance/owner-signing-keys.json` in a pull
   request that you open and merge yourself. The agent cannot change `governance/`.

3. **Create the agent's GitHub identity.** Use a bot account or GitHub App with
   write access but no admin or bypass rights.
   - Add its login to `governance/agent-identities.json`, again yourself.
   - Give agents that identity's token instead of yours.
4. **Branch protection on `main`.**
   - Require the trusted gate check.
   - Do not let the agent identity bypass rules.
5. **Grant work.**

   ```sh
   python scripts/ops/owner_attestation.py draft --agent <bot-login> --issue <N> \
       --path 'nexus/orchestrator/**' --hours 24 --out grant.json
   tools/owner-signer/.build/release/owner-signer sign grant.json > grant.sig   # Touch ID
   python scripts/ops/owner_attestation.py assemble --payload grant.json \
       --signature grant.sig --public-key ~/owner.pem
   ```

   Paste the printed block into the agent's pull request body, or hand it to the
   agent.

## Limits

- **The signer could not be compiled or run here.** It needs macOS with a
  Secure Enclave. The Owner must test `init`, `pubkey` and `sign` on the Mac
  before the key is pinned.
- **GitHub cannot tell who clicks merge.** If the agent is still given the
  Owner's own token, it acts as the Owner and nothing here applies. Setup step 3
  is what makes the check meaningful.
- **A grant is a scope, not a single commit.** Within its paths and validity
  window, the agent may push several commits and open several PRs for the bound
  Issue. Keep the windows short.
- **Cloud sessions cannot sign.** By the Owner's decision they only use grants
  signed on the Mac.
- **Still open for a later phase.** The local gateway's grant tools,
  `task_card_authority_switch`/`restore`, and the other model-supplied
  confirmations listed in `OWNER_CONFIRMATION_PHASE1.md` are not yet tied to
  these signatures.
