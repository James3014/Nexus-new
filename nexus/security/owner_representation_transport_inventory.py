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
through that seam and home its authority in a one-shot Owner grant.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping


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

    def as_dict(self) -> dict[str, str]:
        return {
            "route_id": self.route_id,
            "capability_surface": self.capability_surface,
            "observed_write_seam": self.observed_write_seam,
            "state": self.state.value,
            "evidence": self.evidence,
        }


NONE_KNOWN_EXTERNAL_PUBLICATION_WRITE = "none_known_external_publication_write"
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
        state=PublicationRouteState.OWNER_INTERACTIVE_GATED,
        evidence="UI 'ask before write' is defense-in-depth only, not canonical "
        "authority proof; any third-party write must be bound by an exact "
        "one-shot Owner-representation grant through the canonical seam.",
    ),
    PublicationRoute(
        route_id="codex_cli_pat",
        capability_surface="Codex CLI / GitHub PAT-backed paths",
        observed_write_seam="external interactive CLI; no nexus/ source call",
        state=PublicationRouteState.OWNER_INTERACTIVE_GATED,
        evidence="Interactive human/owner-driven only. Not autonomous Nexus "
        "publication; owner-bound final write by design.",
    ),
    PublicationRoute(
        route_id="devspace_worker",
        capability_surface="Delegated workers with arbitrary shell",
        observed_write_seam="unbounded remote execution outside nexus/ source",
        state=PublicationRouteState.UNKNOWN_BLOCKED,
        evidence="Fails closed: delegated workers cannot publish on Owner's "
        "behalf in third-party repositories without an exact grant through "
        "the canonical seam.",
    ),
    PublicationRoute(
        route_id="morning_report_gh_guidance",
        capability_surface="scripts/core/morning_report.py",
        observed_write_seam="gh pr create rendered as human guidance/display text only",
        state=PublicationRouteState.INCAPABLE_OF_EXTERNAL_PUBLICATION,
        evidence="Command text is emitted for a human operator; the script never "
        "subprocess-invokes gh against a third-party repo.",
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


__all__ = [
    "EXTERNAL_CLASSIFICATION_IDS",
    "FORBIDDEN_PROGRAMMATIC_GITHUB_WRITE_PATTERNS",
    "INTERNAL_ONLY_ROUTE_IDS",
    "PublicationRoute",
    "PublicationRouteState",
    "assert_no_unknown_routes",
    "classify_transport_route",
    "expected_write_seam_for",
    "transport_inventory_status",
]
