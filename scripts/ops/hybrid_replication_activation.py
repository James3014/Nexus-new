#!/usr/bin/env python3
"""Single source of truth for the hybrid-replication activation variables.

Authority: RESEARCH_OBSERVATION_ONLY. The manifest is the only place a human
edits activation state; the five per-repository GitHub Actions variables read by
``.github/workflows/hybrid-replication-capture.yml`` are derived from it, pushed
with ``gh variable set`` and verified with ``gh variable list``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess  # nosec B404
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Sequence

MANIFEST_SCHEMA = "nexus.hybrid_replication.activation_manifest.v1"
ACTIVATION_STATES = ("NOT_READY", "READINESS_CONTROL_PENDING", "AUTOMATIC_CAPTURE_READY")
READY_STATE = "AUTOMATIC_CAPTURE_READY"

# Kept equal to scripts/ops/hybrid_replication_daemon.CANDIDATE_REPOSITORIES
# (asserted in tests) so this script stays runnable without the repo on sys.path.
CANDIDATE_REPOSITORIES = (
    "James3014/Nexus-new",
    "James3014/devspace",
    "James3014/nexus-core",
    "James3014/nexus-learning",
    "James3014/nexus-open-swe-runtime",
    "James3014/repository-intelligence-engine",
    "James3014/nexus-runtime",
    "James3014/nexus-opencli-reviewer",
)

VAR_ACTIVATION_STATE = "NEXUS_HYBRID_REPLICATION_ACTIVATION_STATE"
VAR_T_AUTO = "NEXUS_HYBRID_REPLICATION_T_AUTO"
VAR_EXCLUDED_TASKS = "NEXUS_HYBRID_REPLICATION_EXCLUDED_TASKS"
VAR_EXCLUSION_SET_SHA256 = "NEXUS_HYBRID_REPLICATION_EXCLUSION_SET_SHA256"
VAR_READINESS_CONTROL_TOKEN = "NEXUS_HYBRID_REPLICATION_READINESS_CONTROL_TOKEN"
VARIABLE_NAMES = (
    VAR_ACTIVATION_STATE,
    VAR_T_AUTO,
    VAR_EXCLUDED_TASKS,
    VAR_EXCLUSION_SET_SHA256,
    VAR_READINESS_CONTROL_TOKEN,
)

_REQUIRED_KEYS = {
    "schema",
    "generation",
    "activation_state",
    "t_auto",
    "excluded_tasks",
    "readiness_control_token",
}
_ALLOWED_KEYS = _REQUIRED_KEYS | {"repositories"}
_RFC3339_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

Runner = Callable[..., "subprocess.CompletedProcess[str]"]


class ManifestError(ValueError):
    """Raised when the activation manifest is invalid."""


@dataclass(frozen=True)
class ActivationManifest:
    generation: str
    activation_state: str
    t_auto: str | None
    excluded_tasks: tuple[str, ...]
    readiness_control_token: str
    repositories: tuple[str, ...]

    @property
    def exclusion_set_sha256(self) -> str:
        return exclusion_set_sha256(self.excluded_tasks)

    def variables(self) -> dict[str, str]:
        return {
            VAR_ACTIVATION_STATE: self.activation_state,
            VAR_T_AUTO: self.t_auto or "",
            VAR_EXCLUDED_TASKS: ",".join(sorted(self.excluded_tasks)),
            VAR_EXCLUSION_SET_SHA256: self.exclusion_set_sha256,
            VAR_READINESS_CONTROL_TOKEN: self.readiness_control_token,
        }


def exclusion_set_sha256(excluded_tasks: Sequence[str]) -> str:
    """Same formula as the capture workflow: sha256 of the sorted, comma-joined set."""
    return hashlib.sha256(",".join(sorted(excluded_tasks)).encode("utf-8")).hexdigest()


def parse_manifest(payload: Any) -> ActivationManifest:
    if not isinstance(payload, dict):
        raise ManifestError("manifest_must_be_object")
    if "exclusion_set_sha256" in payload:
        raise ManifestError("exclusion_set_sha256_is_derived_and_must_not_be_supplied")
    unknown = sorted(set(payload) - _ALLOWED_KEYS)
    if unknown:
        raise ManifestError(f"unknown_manifest_keys:{','.join(unknown)}")
    missing = sorted(_REQUIRED_KEYS - set(payload))
    if missing:
        raise ManifestError(f"missing_manifest_keys:{','.join(missing)}")
    if payload["schema"] != MANIFEST_SCHEMA:
        raise ManifestError("manifest_schema_mismatch")
    generation = payload["generation"]
    if not isinstance(generation, str) or not generation.strip():
        raise ManifestError("generation_must_be_non_empty_string")
    state = payload["activation_state"]
    if state not in ACTIVATION_STATES:
        raise ManifestError("invalid_activation_state")
    t_auto = payload["t_auto"]
    if t_auto is not None and (not isinstance(t_auto, str) or not _RFC3339_UTC.match(t_auto)):
        raise ManifestError("t_auto_must_be_rfc3339_utc_or_null")
    if state == READY_STATE and t_auto is None:
        raise ManifestError("automatic_capture_ready_requires_t_auto")
    excluded = payload["excluded_tasks"]
    if not isinstance(excluded, list) or not all(
        isinstance(item, str) and item.strip() and "," not in item for item in excluded
    ):
        raise ManifestError("excluded_tasks_must_be_list_of_comma_free_strings")
    if len(set(excluded)) != len(excluded):
        raise ManifestError("excluded_tasks_must_be_unique")
    token = payload["readiness_control_token"]
    if not isinstance(token, str):
        raise ManifestError("readiness_control_token_must_be_string")
    repositories = payload.get("repositories", list(CANDIDATE_REPOSITORIES))
    if (
        not isinstance(repositories, list)
        or not repositories
        or not all(isinstance(item, str) and item.strip() for item in repositories)
    ):
        raise ManifestError("repositories_must_be_non_empty_list_of_strings")
    if len(set(repositories)) != len(repositories):
        raise ManifestError("repositories_must_be_unique")
    return ActivationManifest(
        generation=generation,
        activation_state=state,
        t_auto=t_auto,
        excluded_tasks=tuple(excluded),
        readiness_control_token=token,
        repositories=tuple(repositories),
    )


def load_manifest(path: Path) -> ActivationManifest:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest_unreadable:{exc}") from exc
    return parse_manifest(payload)


def render(manifest: ActivationManifest) -> dict[str, dict[str, str]]:
    variables = manifest.variables()
    return {repository: dict(variables) for repository in manifest.repositories}


def push(
    manifest: ActivationManifest, *, gh: str = "gh", runner: Runner = subprocess.run
) -> list[dict[str, Any]]:
    """Run ``gh variable set`` for every repository and variable; return failures."""
    failures: list[dict[str, Any]] = []
    for repository, variables in render(manifest).items():
        for name, value in variables.items():
            completed = runner(  # nosec B603
                [gh, "variable", "set", name, "--repo", repository, "--body", value],
                check=False,
                capture_output=True,
                text=True,
            )
            if completed.returncode != 0:
                failures.append(
                    {
                        "repository": repository,
                        "variable": name,
                        "returncode": completed.returncode,
                        "stderr": (completed.stderr or "").strip(),
                    }
                )
    return failures


def readback(
    manifest: ActivationManifest, *, gh: str = "gh", runner: Runner = subprocess.run
) -> list[dict[str, Any]]:
    """Compare live repository variables with the manifest; return drift entries."""
    drift: list[dict[str, Any]] = []
    for repository, expected in render(manifest).items():
        completed = runner(  # nosec B603
            [gh, "variable", "list", "--repo", repository, "--json", "name,value"],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            drift.append(
                {
                    "repository": repository,
                    "error": "gh_variable_list_failed",
                    "returncode": completed.returncode,
                    "stderr": (completed.stderr or "").strip(),
                }
            )
            continue
        try:
            listed = json.loads(completed.stdout)
            actual = {str(item["name"]): str(item["value"]) for item in listed}
        except (json.JSONDecodeError, KeyError, TypeError):
            drift.append({"repository": repository, "error": "gh_variable_list_unparseable"})
            continue
        for name, want in expected.items():
            have = actual.get(name)
            if have != want:
                drift.append(
                    {"repository": repository, "variable": name, "expected": want, "actual": have}
                )
    return drift


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, helptext in (
        ("render", "print the per-repository variable map as JSON"),
        ("push", "set the variables in every repository with gh"),
        ("readback", "verify live variables match the manifest (exit 2 on drift)"),
    ):
        command = sub.add_parser(name, help=helptext)
        command.add_argument("--manifest", required=True, type=Path)
        if name != "render":
            command.add_argument("--gh", default="gh", help="gh executable (default: gh)")
    return parser


def main(argv: Sequence[str] | None = None, *, runner: Runner = subprocess.run) -> int:
    args = _build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
    except ManifestError as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 1
    if args.command == "render":
        print(json.dumps(render(manifest), indent=2, sort_keys=True))
        return 0
    if args.command == "push":
        failures = push(manifest, gh=args.gh, runner=runner)
        print(json.dumps({"generation": manifest.generation, "failures": failures}, indent=2))
        return 3 if failures else 0
    drift = readback(manifest, gh=args.gh, runner=runner)
    if drift:
        print(json.dumps({"generation": manifest.generation, "drift": drift}, indent=2))
        return 2
    print(json.dumps({"generation": manifest.generation, "drift": []}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
