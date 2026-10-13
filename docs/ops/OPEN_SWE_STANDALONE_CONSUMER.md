# OpenSWE standalone consumer configuration

`external_intelligence_open_swe_activation_v1.json` is an activation overlay,
not a complete service configuration. The service has no automatic renderer or
merger for this fragment. Deployment must merge it into the complete host JSON
before passing that file to `scripts/ops/external_intelligence_service.py`.

The host configuration owns repositories, repository roots, `state_root`, and
`workspace_root`. The overlay owns backend selection, provider/model binding,
the absolute installed `nexus-open-swe-runtime` executable, its expected
artifact hash, and the OpenCLI WEB transport binding. Replace all angle-
bracket values before activation. The runtime executable and artifact-hash
placeholders are deliberately rejected by `load_config()`; deployment must
also replace the OpenCLI executable and profile placeholders because they are
deployment identity, not personal credentials.

With `opencli_chatgpt`, OpenSWE invokes the installed OpenCLI executable with
the configured profile and an ephemeral site session. OpenCLI then uses its
ChatGPT WEB transport. This browser-backed WEB transport is distinct from a
Google or OpenAI API provider; no API key or API client is configured here.
Before activation, the selected Chrome profile must already be logged in, the
OpenCLI daemon must be reachable, and the host must be unlocked so the
foreground browser window can be attached. The configured OpenCLI launcher must
forward `--window foreground` and set the fixed browser command timeout
`OPENCLI_BROWSER_COMMAND_TIMEOUT=180`; an inherited `OPENCLI_WINDOW` value is
not sufficient under the runtime environment allowlist. The ChatGPT adapter
must be in conversation mode rather than Work mode. `balanced` names the
ChatGPT UI capability level; it is not a fixed model slug. OpenCLI 1.8.7 also
requires the accepted local ChatGPT compatibility correction, including
model-picker hydration handling and exact JSON whitespace readback; this
overlay does not install or activate that correction.

With `worker_backend=open_swe` the service requests Workforce routing as consumer
`external_intelligence`, which the runtime policy routes to
`opencli_chatgpt_advanced_web` (owner decision 2026-10-12, moved from
`balanced` to the free-plan Thinking level `advanced` on 2026-10-13; set
`open_swe_model` to `advanced`). The `opencode`
rollback backend sends no consumer and keeps the global route.

`open_swe_runtime_artifact_sha256` is the independently supplied SHA256 of the
runtime identity module reported by the executable's identity response. It is
not the wheel/archive SHA256. The service passes the same executable and module
hash to semantic and worker consumers and derives their shared runtime state as
`<host state_root>/open_swe_runtime`.

The value is `artifact_identity.module_sha256`, the SHA256 of the installed
`nexus_open_swe_runtime/cli.py`, and it changes whenever a runtime upgrade
changes that file. The service fails closed with
`OPEN_SWE_RUNTIME_ARTIFACT_MISMATCH` until the host JSON is updated. Upgrade the
runtime and the hash together: install the new runtime, run
`<installed executable> --identity`, copy `artifact_identity.module_sha256`
into `open_swe_runtime_artifact_sha256`, then restart the service. Do not
compute it by hand from a source checkout, and do not use `package_sha256` or
`runtime_identity_sha256`; Nexus-new compares only `module_sha256`.
For reference, `nexus-open-swe-runtime` PR #108 changed `cli.py`: runtimes
before it report `6ba52e55f0fa6036a557fbfbff2999a96d8e2046c3ed173a26288e66c0c6eb82`,
and main at `64656b98ef2027c630e5b5a6cf9856496223d550` reports
`6cbab468c7be847c6c5bae176d57aecb930ce9f2096fbb1a9a792ea93866b133`.

`open_swe_semantic_timeout_seconds` and `open_swe_worker_timeout_seconds`
bound the overall deadline for their respective OpenSWE task operations. They
default to 180 and 300 seconds for older host configurations and accept integer
values from 30 through 3600. These are task deadlines, not per-turn guarantees;
the existing tool-turn and no-resend rules remain unchanged. The resident Web
configuration uses 1200 seconds for semantic work and 2400 seconds for worker
work because a production-shaped semantic packet exceeded the earlier
600-second synthetic qualification budget without reaching a terminal result.

The overlay does not enable or reload a service, start a daemon, or contain a
temporary acceptance virtualenv path. Rollback keeps the overlay's
provider/model fields if desired and changes only `semantic_backend` to `opencli` and
`worker_backend` to `opencode`.
