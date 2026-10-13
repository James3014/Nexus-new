# Agent App identity (Issue #1750, phase 2)

`scripts/ops/nexus_agent_identity.py` lets an agent session act on GitHub as the
GitHub App `nexus-agent-james3014` (App id 5294709) instead of the Owner's account.

## Why

Agents must not use the Owner's token or `gh` login for Nexus-new work. Once the
Owner-grant ruleset (#1817) is on, PRs authored under the Owner login are
treated as Owner actions, so sessions must not use the Owner's `gh` login for
Nexus-new PRs. The App identity keeps agent activity attributable and
separately revocable.

## Usage

```
python3 -I scripts/ops/nexus_agent_identity.py whoami
python3 -I scripts/ops/nexus_agent_identity.py gh -- pr create --fill
python3 -I scripts/ops/nexus_agent_identity.py git -- push origin HEAD:feat/branch
python3 -I scripts/ops/nexus_agent_identity.py token   # prints the token; avoid logging it
```

Credentials live in `~/.config/nexus-apps/agent.json` and `agent.pem` (mode 0600;
override the directory with `NEXUS_AGENT_APP_DIR`, for tests only). The JWT is
signed by the root-owned `/usr/bin/openssl`; the key never enters this process.

## Token

Installation tokens last 1 hour. The helper caches `{token, expires_at}` in
`~/.config/nexus-apps/agent.token` (0600) and reuses it until under 5 minutes
remain. A cache that is not user-owned or has group/other permissions is refused.
`gh` receives the token via `GH_TOKEN` (`GITHUB_TOKEN` unset); `git` receives an
extraheader via `GIT_CONFIG_*` environment variables, never argv.

## Permissions

The App has contents, pull_requests and issues write. It has no workflow
permission (cannot change `.github/workflows`) and no admin rights.

## Security notes

- `gh` and `git` are resolved once via `PATH` (`shutil.which`) and exec'd by
  absolute path; PATH is trusted.
- The token is passed to the child through its environment, so git hooks and any
  other child processes inherit it. Run only trusted repositories.
- SSH remotes now fail by design (`protocol.ssh.allow=never`); use https remotes.
  Git prompts and askpass helpers are disabled.
