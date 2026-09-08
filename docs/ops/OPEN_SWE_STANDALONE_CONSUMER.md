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

`open_swe_runtime_artifact_sha256` is the independently supplied SHA256 of the
runtime identity module reported by the executable's identity response. It is
not the wheel/archive SHA256. The service passes the same executable and module
hash to semantic and worker consumers and derives their shared runtime state as
`<host state_root>/open_swe_runtime`.

`open_swe_semantic_timeout_seconds` and `open_swe_worker_timeout_seconds`
bound the overall deadline for their respective OpenSWE task operations. They
default to 180 and 300 seconds for older host configurations and accept integer
values from 30 through 3600. These are task deadlines, not per-turn guarantees;
the existing tool-turn and no-resend rules remain unchanged.

The overlay does not enable or reload a service, start a daemon, or contain a
temporary acceptance virtualenv path. Rollback keeps the overlay's
provider/model fields if desired and changes only `semantic_backend` to `opencli` and
`worker_backend` to `opencode`.
