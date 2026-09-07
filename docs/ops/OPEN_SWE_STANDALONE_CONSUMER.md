# OpenSWE standalone consumer configuration

`external_intelligence_open_swe_activation_v1.json` is an activation overlay,
not a complete service configuration. The service has no automatic renderer or
merger for this fragment. Deployment must merge it into the complete host JSON
before passing that file to `scripts/ops/external_intelligence_service.py`.

The host configuration owns repositories, repository roots, `state_root`, and
`workspace_root`. The overlay owns backend selection, provider/model binding,
the absolute installed `nexus-open-swe-runtime` executable, and the expected
artifact hash. Replace both angle-bracket values before activation; placeholders
are deliberately rejected by `load_config()`.

`open_swe_runtime_artifact_sha256` is the independently supplied SHA256 of the
runtime identity module reported by the executable's identity response. It is
not the wheel/archive SHA256. The service passes the same executable and module
hash to semantic and worker consumers and derives their shared runtime state as
`<host state_root>/open_swe_runtime`.

The overlay does not enable or reload a service and must not contain a temporary
acceptance virtualenv path. Rollback keeps the overlay's provider/model fields
if desired and changes only `semantic_backend` to `opencli` and
`worker_backend` to `opencode`.
