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

## Current conformance (origin/main, checked 2026-10-16)

| Adapter | Prompt | Conversation | Environment | Session mode |
| --- | --- | --- | --- | --- |
| reviewer | argv (`opencli.py:123`); records use `safe_argv` (`:37-39`, `:125`) | always `--new` (`:123`) | full copy: `os.environ.copy()` (`:129`) | `ephemeral` (`:124`, `:167`) |
| open-swe | argv (`opencli_web_model.py:2084`) | `--conversation` when bound, else `--new` (`:2085-2088`) | denylist filter (`:1196-1208`, markers `:979-980`); `AWS_*` and other unlisted names pass | `ephemeral` default (`:1015`), passed at `:2094` |
| Nexus-new embedded copy | argv (`opencli_web_model.py:855`) | `--conversation` when bound, else `--new` (`:856-859`) | full copy: `os.environ.copy()` (`:537`) | `ephemeral` default (`:478`) |
| devspace | argv (`chat-swarm-runtime.ts:1476`, `:1531`) | `--new` on the first ask (`:1480`), then `--conversation` (`:1533`) | inherits `process.env`: `spawn` at `:1681` passes no `env` | `ephemeral` (`:1443`, `:1484`, `:1537`, `:1669`) |

Reading the table: argv prompt delivery is accepted (rule 1). Conversation
policy and session mode conform everywhere. Environment is the gap.
open-swe's denylist conforms to the minimum but not to the allowlist target.
Rule 5 tests are not part of this document's change; each repo adds its own.

## Known non-conformances and follow-ups

| Item | Owner | Reference |
| --- | --- | --- |
| reviewer passes the full environment | nexus-opencli-reviewer | nexus-opencli-reviewer#105 |
| Nexus-new embedded copy passes the full environment | Nexus-new | Nexus-new#2394 |
| devspace inherits `process.env` | devspace, paused, not scheduled | none |
| open-swe is a denylist, not an allowlist | nexus-open-swe-runtime, optional hardening | none |
| No recording-fake conformance test yet (rule 5) | each repo, bundled with the fixes above | the two Issues above |

## Earlier findings mapped to this contract

- REV-4 (nexus-opencli-reviewer#78, open): prompt in argv. Covered by rule 1 as
  an accepted limitation. Its remaining parts (redacted records) already hold
  through `safe_argv`.
- SWE-4 (nexus-open-swe-runtime#103, closed): fresh-versus-reused conversation.
  Covered by rule 2.
- SWE-2 (nexus-open-swe-runtime#101, closed): credentials inherited by the
  subprocess. Fixed there with the denylist filter, which is the reference for
  rule 3.
