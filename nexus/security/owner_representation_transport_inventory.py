"""Declarative, fail-closed inventory of every route that could publicly write
to an external destination (Owner representation surface).

This is evidence plumbing, not authority.  Each listed route carries its
classification and the source evidence that grounds it.  ``UNKNOWN_BLOCKED`` is
the only acceptable answer for anything not inventoried, and
``assert_no_unknown_routes()`` fails closed so that a silent new publication
channel cannot be added without being classified.

The authoritative write seam for new or actual external publication remains
``nexus/orchestrator/owner_representation.py``; a route labelled
``EXTERNAL_PUBLICATION_AUTHORITY_ENFORCED`` must route its physical write
through that seam and home its authority in a one-shot Owner grant persisted
by the canonical ``owner_representation_store``.

Scope note (INCAPABILITY_IS_SOURCE_SCOPE_ONLY): every
``INCAPABLE_OF_EXTERNAL_PUBLICATION`` classification is grounded in checked-in
``nexus/**`` and ``scripts/**`` source.  It does not certify a live external
binary, connector, or a future source change; re-verification is required
before any such claim.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class PublicationRouteState(str, Enum):
    """Desired fail-closed classification of a publication-capable route."""

    INCAPABLE_OF_EXTERNAL_PUBLICATION = "INCAPABLE_OF_EXTERNAL_PUBLICATION"
    OWNER_INTERACTIVE_GATED = "OWNER_INTERACTIVE_GATED"
    BOUNDED_INTERNAL_ONLY = "BOUNDED_INTERNAL_ONLY"
    EXTERNAL_PUBLICATION_AUTHORITY_ENFORCED = "EXTERNAL_PUBLICATION_AUTHORITY_ENFORCED"
    UNKNOWN_BLOCKED = "UNKNOWN_BLOCKED"


@dataclass(frozen=True)
class PublicationRoute:
    """One inventoried route plus its source-bound evidence."""

    route_id: str
    capability_surface: str
    observed_write_seam: str
    state: PublicationRouteState
    evidence: str
    physical_witnesses: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "capability_surface": self.capability_surface,
            "observed_write_seam": self.observed_write_seam,
            "state": self.state.value,
            "evidence": self.evidence,
            "physical_witnesses": list(self.physical_witnesses),
        }


NONE_KNOWN_EXTERNAL_PUBLICATION_WRITE = "none_known_external_publication_write"
# These are concrete transport identities, not route IDs.  Keeping the
# mapping explicit prevents a caller-controlled string from becoming an
# implicitly trusted route merely because both happen to have the same name.
CANONICAL_TRANSPORT_ROUTE_BINDINGS: Mapping[str, str] = MappingProxyType({
    "canonical_owner_representation": "owner_representation_seam"
})
ALL: tuple[PublicationRoute, ...] = (
    PublicationRoute(
        route_id="github_orchestration",
        capability_surface="Nexus merge intent / GITHUB_MERGE authority",
        observed_write_seam="nexus/contracts/github_orchestration.py + nexus/orchestrator/github_orchestration.py",
        state=PublicationRouteState.BOUNDED_INTERNAL_ONLY,
        evidence="Internal PR completion and merge intent only; covered by "
        "existing GITHUB_MERGE standing-grant authority, never third-party.",
    ),
    PublicationRoute(
        route_id="governed_push",
        capability_surface="REPOSITORY_PUSH standing-grant authority",
        observed_write_seam="nexus/orchestrator/governed_push.py",
        state=PublicationRouteState.BOUNDED_INTERNAL_ONLY,
        evidence="#566 canonical push authority; pushes repository refs under "
        "an explicit grant. A push denial is never external "
        "issue-publication authority (see #827 regression).",
    ),
    PublicationRoute(
        route_id="external_intelligence_service",
        capability_surface="Internal EIA/EI pipelines",
        observed_write_seam="nexus/services/external_intelligence*.py",
        state=PublicationRouteState.BOUNDED_INTERNAL_ONLY,
        evidence="Internal automation/records and local state only; "
        "publication payloads are repository records, not GitHub writes.",
    ),
    PublicationRoute(
        route_id="repository_contract_gate",
        capability_surface="Collaboration boundary provenance checks",
        observed_write_seam="nexus/orchestrator/repository_contract_gate.py + collaboration_realm.py",
        state=PublicationRouteState.INCAPABLE_OF_EXTERNAL_PUBLICATION,
        evidence="Read-only gate over repository/remote topology; no remote "
        "path creates issues, comments, or PRs.",
    ),
    PublicationRoute(
        route_id="chatgpt_connector",
        capability_surface="ChatGPT connector UI (ask-before-write)",
        observed_write_seam="external component surfaced via nexus/orchestrator/unified_mcp_gateway.py owner_confirmation flags",
        state=PublicationRouteState.UNKNOWN_BLOCKED,
        evidence="Source records UI 'ask before write' as defense-in-depth only; "
        "no current external control-plane receipt proves live gating, so this "
        "route is UNKNOWN_BLOCKED and cannot be used as publication authority.",
    ),
    PublicationRoute(
        route_id="codex_cli_pat",
        capability_surface="Codex CLI / GitHub PAT-backed paths",
        observed_write_seam="external interactive CLI; no nexus/ source call",
        state=PublicationRouteState.UNKNOWN_BLOCKED,
        evidence="Interactive human/owner-driven behavior has no current "
        "independent enforcement receipt in this inventory; fail closed as "
        "UNKNOWN_BLOCKED rather than claim a live gate.",
    ),
    PublicationRoute(
        route_id="devspace_worker",
        capability_surface="Delegated workers with arbitrary shell",
        observed_write_seam="unbounded remote execution outside nexus/ source",
        state=PublicationRouteState.UNKNOWN_BLOCKED,
        evidence="No devspace adapter exists in nexus/executors/worker_registry.py "
        "(adapters: codex, gemini, agy, opencode, mimo, ollama, cline, grok), so "
        "no path in checked-in nexus/** source spawns or exercises a devspace "
        "worker.  Local CLI workers run through CliWorkerRequest -> "
        "run_cli_worker, which rejects forbidden publication invocations and "
        "fails closed on GitHub credential env keys (GITHUB_CREDENTIAL_KEYS), "
        "and build_isolated_env strips those credentials before any local "
        "spawn.  Unlike those routes, a real devspace deployment executes on an "
        "uncontrolled remote shell outside nexus/ source where ambient GitHub "
        "credentials, HOME-based gh config, credential helpers, and arbitrary "
        "shell wrappers cannot be excluded; Nexus therefore cannot physically "
        "certify non-publication and classifies the route UNKNOWN_BLOCKED "
        "(never usable as publication authority, fail closed).",
        physical_witnesses=(
            "nexus/executors/worker_registry.py",
            "nexus/executors/cli_worker.py",
            "nexus/services/agy_account_pool.py",
        ),
    ),
    PublicationRoute(
        route_id="morning_report_gh_guidance",
        capability_surface="scripts/core/morning_report.py",
        observed_write_seam="gh pr create rendered as human guidance/display text only",
        state=PublicationRouteState.INCAPABLE_OF_EXTERNAL_PUBLICATION,
        evidence="Command text is emitted for a human operator; the script never "
        "subprocess-invokes gh against a third-party repo.",
    ),
    PublicationRoute(
        route_id="owner_representation_seam",
        capability_surface="Canonical Owner-representation publication seam",
        observed_write_seam="nexus/orchestrator/owner_representation.py + owner_representation_store.py",
        state=PublicationRouteState.EXTERNAL_PUBLICATION_AUTHORITY_ENFORCED,
        evidence="New or actual external publication must route physical writes "
        "through the canonical publisher seam and home authority in a sealed "
        "one-shot issuance permit minted from live Owner standing-grant authority "
        "and consumed once; the Owner-representation grant is persisted as a "
        "durable receipt by the owner_representation_store before any dispatch "
        "effect.",
        physical_witnesses=(
            "nexus/orchestrator/owner_representation.py",
            "nexus/orchestrator/owner_representation_store.py",
        ),
    ),
)

# Internal-only routes never form an Owner-representation surface; they are
# excluded from the external classification set but kept as a positive control
# that existing internal automation is preserved.
INTERNAL_ONLY_ROUTE_IDS = frozenset(
    route.route_id for route in ALL if route.state is PublicationRouteState.BOUNDED_INTERNAL_ONLY
)

EXTERNAL_CLASSIFICATION_IDS = frozenset(
    route.route_id for route in ALL if route.route_id not in INTERNAL_ONLY_ROUTE_IDS
)


def transport_inventory_status() -> Mapping[str, str]:
    return {route.route_id: route.state.value for route in ALL}


def classify_transport_route(route_id: str) -> PublicationRouteState:
    for route in ALL:
        if route.route_id == route_id:
            return route.state
    return PublicationRouteState.UNKNOWN_BLOCKED


def route_for_transport(
    transport_identity: str,
) -> str | None:
    """Resolve a concrete signed transport identity to an inventoried route."""
    route_id = CANONICAL_TRANSPORT_ROUTE_BINDINGS.get(transport_identity)
    if route_id is None:
        return None
    if route_id not in {route.route_id for route in ALL}:
        raise ValueError(f"transport binding names unknown route: {route_id}")
    return route_id


def assert_no_unknown_routes() -> None:
    """Integrity guard: inventory is non-empty, ids unique, states explicit.

    ``UNKNOWN_BLOCKED`` is a *registered* fail-closed state for routes that may
    hold write capability but are not Owner-authorized; it is never treated as
    usable.  Silent new publication sinks are caught physically by the
    source-parity test backed by ``FORBIDDEN_PROGRAMMATIC_GITHUB_WRITE_PATTERNS``.
    """
    ids = [route.route_id for route in ALL]
    if not ids:
        raise AssertionError("publication route inventory is empty")
    if len(set(ids)) != len(ids):
        raise AssertionError("publication route ids are not unique")
    for route in ALL:
        if route.state not in tuple(PublicationRouteState):
            raise AssertionError(f"route {route.route_id} has unknown state")


# Regex patterns that MUST NOT appear in nexus/** and scripts/** Python source
# unless the writing module is added to the inventory as authority-enforced or
# internal-only.  Each captures a genuine remote *write* invocation (verb +
# GitHub host/endpoint), not read-only path fragments or ref strings.  Backed
# by the physical source-parity test.
FORBIDDEN_PROGRAMMATIC_GITHUB_WRITE_PATTERNS: tuple[tuple[str, str, str], ...] = (
    (
        r"gh\s+(issue|pr)\s+create",
        "gh_cli_issue_pr_create",
        "gh CLI object-creation invocation",
    ),
    (
        r"gh\s+api\s+",
        "gh_cli_api_write",
        "gh CLI api invocation (write-capable)",
    ),
    (
        r"\.issues\.create\(",
        "github_issues_create",
        "SDK issue creation call",
    ),
    (
        r"\.comments\.create\(",
        "github_comments_create",
        "SDK comment creation call",
    ),
    (
        r"create_pull_request\(",
        "github_octokit_create_pr",
        "SDK pull-request creation call",
    ),
    (
        r"(?:requests|client|httpx|aiohttp)\.(?:post|put|patch|delete)\([^\n]*github",
        "http_write_to_github",
        "HTTP write verb targeting a GitHub host",
    ),
    (
        r"(?:requests|client|httpx|aiohttp)\.(?:post|put|patch|delete)\([^\n]*/issues/",
        "http_write_to_issues_endpoint",
        "HTTP write verb targeting an issues endpoint",
    ),
)


def expected_write_seam_for(route_id: str) -> str:
    for route in ALL:
        if route.route_id == route_id:
            return route.observed_write_seam
    raise KeyError(route_id)


def physical_witnesses_for(route_id: str) -> tuple[str, ...]:
    """Repository files that physically ground a route classification."""
    for route in ALL:
        if route.route_id == route_id:
            return route.physical_witnesses
    raise KeyError(route_id)


__all__ = [
    "EXTERNAL_CLASSIFICATION_IDS",
    "FORBIDDEN_PROGRAMMATIC_GITHUB_WRITE_PATTERNS",
    "INTERNAL_ONLY_ROUTE_IDS",
    "PublicationRoute",
    "PublicationRouteState",
    "assert_no_unknown_routes",
    "classify_transport_route",
    "expected_write_seam_for",
    "physical_witnesses_for",
    "route_for_transport",
    "transport_inventory_status",
]
