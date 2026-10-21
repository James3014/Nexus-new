# OpenCLI ChatGPT adapter contract

Status: accepted 2026-10-16. Tracking: Nexus-new#1729.

## Purpose

Four pieces of code call `opencli chatgpt ...`. Each one is the path by which
prompts, and possibly repository content, leave the machine for an external AI
service. They had drifted apart on prompt passing, conversation reuse,
environment handling and session mode. This document is the one written
contract they all follow, so a fix or a finding in one can be checked against
the others.

## Decision

Keep SEPARATE implementations under ONE written contract. There is no shared
adapter package. The callers are in two languages (Python and TypeScript), live
in different repos, and one of them is a vendored copy. A shared package would
add a cross-repo pin, and pins are already a maintenance problem (#1728).
Consistency comes from this contract plus a conformance test in each repo.

## The four implementations

| Short name | Location |
| --- | --- |
| reviewer | nexus-opencli-reviewer `reviewer/opencli.py` (`OpenCLITransport`) |
| open-swe | nexus-open-swe-runtime `nexus_open_swe_runtime/opencli_web_model.py` (`OpenCLIWebChatModel`) |
| Nexus-new embedded copy | this repo, `runtimes/open_swe/nexus_open_swe_runtime/opencli_web_model.py` |
| devspace | devspace `src/chat-swarm-runtime.ts` (DevSpace development is paused since 2026-10-16) |

## Contract rules

1. Prompt delivery. The installed `opencli chatgpt ask` takes the prompt only
   as a positional argument. It has no stdin or file option (checked with
   `opencli chatgpt ask --help` on 2026-10-16). Passing the prompt in argv is
   therefore the accepted limitation on single-user hosts, where other users
   cannot read the process list. Adapters must never write the prompt into
   records, logs or receipts: record a redacted argv (the reviewer's
   `safe_argv` shows `<prompt>` in place of the text). If opencli adds stdin or
   file input, adapters must switch to it.
2. Conversation policy is explicit on every call. The caller chooses `--new` or
   `--conversation <id>`. An adapter never reuses a conversation implicitly,
   and a call that reuses one says so in its code path and its record.
3. Environment. The target is an allowlist of the variables opencli needs. The
   minimum acceptable behavior is to strip credential-shaped variables before
   spawning the child: `GITHUB_*`, `GH_*`, names containing `TOKEN`, `API_KEY`,
   `SECRET`, `PASSWORD` or `CREDENTIAL`, and provider prefixes (`GOOGLE_`,
   `GEMINI_`, `OPENAI_`, `ANTHROPIC_`). Names containing `OPENCLI` stay,
   because they configure the child itself. open-swe's `_environment()` is the
   reference filter. A full copy of `os.environ` (or an inherited
   `process.env`) is non-conforming.
4. Session mode is `--site-session ephemeral`. A call that needs a persistent
   session must say why, in a comment at the call site.
5. Conformance testing. Each adapter has a test that runs it against a
   recording fake `opencli` executable and asserts, from what the fake
   recorded: the argv shape, that `--new` or `--conversation` is present, the
   `--site-session` value, and that sentinel variables such as `GITHUB_TOKEN`,
   `OPENAI_API_KEY` and `MY_SECRET` are absent from the child environment. The
   test must run on Linux in CI and must not skip.

### Hardened filter (reviewer, embedded copy and open-swe)

The reviewer and the embedded copy use this filter (2026-10-17), and open-swe
adopted it in nexus-open-swe-runtime#152 (2026-10-21). It goes beyond the
minimum in rule 3. It is case-insensitive (name
upper-cased once) and drops a variable when its name:

- contains `TOKEN`, `API_KEY`, `SECRET`, `PASSWORD`, `PASSWD`, `CREDENTIAL`,
  `PRIVATE_KEY`, `KEY_ID`, `COOKIE` or `AUTHORIZATION`, ends in `_KEY` or
  `_PAT`, or contains `AUTH_` or `_AUTH` as a substring, or is exactly `AUTH` (this also drops
  names such as `BASIC_AUTH` and `GIT_AUTHOR_*`);
- starts with `GITHUB_`, `GH_`, `GOOGLE_`, `GEMINI_`, `OPENAI_`, `ANTHROPIC_` or
  `AWS_`;
- is exactly `SSH_AUTH_SOCK`, `KUBECONFIG`, `DOCKER_AUTH_CONFIG` or `DATABASE_URL`.

`OPENCLI_*` names (such as `OPENCLI_PROFILE`) stay, unless they also match a
secret marker (`OPENCLI_TOKEN`, `OPENCLI_API_KEY` are dropped). The word
`OPENCLI` elsewhere in a name no longer exempts it, and the earlier open-swe
filter's `PROVIDER` exemption is dropped (its only history, commit 7f834e2,
gives no reason). `PATH`, `HOME`, `LANG`, `TMPDIR` and `OPENCLI_PROFILE` pass.

## Current conformance (origin/main, checked 2026-10-16; reviewer and embedded rows updated 2026-10-17; open-swe environment cell updated 2026-10-21)

| Adapter | Prompt | Conversation | Environment | Session mode |
| --- | --- | --- | --- | --- |
| reviewer | argv (`opencli.py:182`); records use `safe_argv` (`:96-98`, `:184`) | always `--new` (`:182`) | hardened denylist `child_environment()` (`opencli.py:10-66`) on every opencli spawn: transport ask/detail/`--version`, `service_cli._opencli_json`/`_opencli_browser`/`_daemon_restart`, `OpenCLIPreflight._run`; nexus-opencli-reviewer#108 (closes #105), tests in `tests/test_opencli_child_environment.py` | `ephemeral` (`:183`, `:224`) |
| open-swe | argv (`opencli_web_model.py:2084`) | `--conversation` when bound, else `--new` (`:2085-2088`) | hardened denylist in `_environment()` (`:1224-1228`, filter `:979-1021`) on the opencli child spawned by `_run` (`:1241`); nexus-open-swe-runtime#152 (refs #151), test `tests/test_opencli_credential_filter_hardened.py` | `ephemeral` default (`:1015`), passed at `:2094` |
| Nexus-new embedded copy | argv (`opencli_web_model.py:906`) | `--conversation` when bound, else `--new` (`:908-910`) | hardened denylist in `_environment()` (`:587`, filter `:461-510`); test `tests/services/test_open_swe_embedded_opencli_environment.py` | `ephemeral` default (`:529`) |
| devspace | argv (`chat-swarm-runtime.ts:1476`, `:1531`) | `--new` on the first ask (`:1480`), then `--conversation` (`:1533`) | inherits `process.env`: `spawn` at `:1681` passes no `env` | `ephemeral` (`:1443`, `:1484`, `:1537`, `:1669`) |

Reading the table: argv prompt delivery is accepted (rule 1). Conversation
policy and session mode conform everywhere. Environment is the gap, now closed to the
minimum for reviewer, open-swe and the embedded copy; only devspace still
inherits `process.env`. The three denylists conform to the minimum but not to
the allowlist target. All three use the hardened filter described above.
Rule 5 tests live in each repo, not in this document.

## Known non-conformances and follow-ups

| Item | Owner | Reference |
| --- | --- | --- |
| ~~reviewer passes the full environment~~ fixed (denylist, rule 5 test) | nexus-opencli-reviewer | nexus-opencli-reviewer#105, PR #108 |
| ~~Nexus-new embedded copy passes the full environment~~ fixed (denylist, rule 5 test) | Nexus-new | Nexus-new#2394 |
| devspace inherits `process.env` | devspace, paused, not scheduled | none |
| ~~open-swe has the older reference filter, not the hardened one~~ fixed (hardened denylist); it is still a denylist, not an allowlist | nexus-open-swe-runtime | nexus-open-swe-runtime#151, PR #152 |
| Rule 5 recording-fake test present for reviewer and the embedded copy; open-swe and devspace not covered here | open-swe, devspace | none |

## Earlier findings mapped to this contract

- REV-4 (nexus-opencli-reviewer#78, open): prompt in argv. Covered by rule 1 as
  an accepted limitation. Its remaining parts (redacted records) already hold
  through `safe_argv`.
- SWE-4 (nexus-open-swe-runtime#103, closed): fresh-versus-reused conversation.
  Covered by rule 2.
- SWE-2 (nexus-open-swe-runtime#101, closed): credentials inherited by the
  subprocess. Fixed there with the denylist filter, which is the reference for
  rule 3.
