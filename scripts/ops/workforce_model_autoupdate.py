#!/usr/bin/env python3
"""Automatic Workforce model-version updater with independent AI review (#1996, option A).

When Agy starts serving a newer model in the same family and tier as a Workforce default
(for example ``gemini-3.8-flash-medium`` -> ``gemini-3.9-flash-medium``), or stops serving the
current default, this tool switches the default to the newest servable same-tier model. No
Owner confirmation is needed, but an independent AI reviewer must ACCEPT the exact PR head
before anything merges. Every stage fails closed.

Stages (each returns a typed result; nothing raises past :func:`run`):

1. :func:`discover` reads ``agy models`` (a catalog fetch, not inference) as ``id<TAB>label``
   lines. Ids that match the ASCII-only :data:`AGY_FLASH_RE`, round-trip to the canonical form
   ``gemini-<maj>.<min>-flash-<tier>`` (no leading zeros) *and* carry the deterministic label
   (``Gemini 3.8 Flash (Medium)``) are recognized; everything else is recorded in
   ``unrecognized`` and never used for a decision. A duplicate id or version fails the whole
   catalog closed. ``agy --version`` is kept only if it is ASCII ``X.Y.Z`` (else ``unknown``).
   Campaign/consumer pins (Owner decision 2026-10-13, F3): they move with the default only when
   the predecessor is retired (unservable); a superseded but still-served predecessor keeps them.
2. :func:`decide` checks each ``route_defaults`` role whose default is an ``agy`` worker: is the
   exact default id still served, and is there a newer version in the same family and tier?
   Result: ``NOOP``, ``SWITCH`` or ``BLOCKED``. It never crosses provider, family or tier,
   never downgrades, and never raises autonomy (a reused worker must not exceed the
   predecessor's autonomy; a new worker copies it exactly).
3. :func:`attest` makes one live call through ``scripts.bench.agy_provider`` (``--mode plan
   --sandbox --model <id>``, no-tools prefix, account lease with a 5-hour-window allowlist that
   skips accounts other processes hold) and requires the observed resolved id and backend label
   to match exactly. A passing attestation is reused for at most ``--attestation-ttl-hours``
   (24 h); a resumed switch whose runtime PR is not merged re-runs discovery (the new model must
   still be served) and re-attests once the TTL expired.
4. :func:`render_change` edits the yaml text surgically (register / flip / retire / bump
   ``last_verified``), checks the parsed result equals the intended dict transform, and runs the
   real ``WorkforcePolicyLoader`` validator on it.
5. :func:`build_plan` / the propose helpers open the nexus-runtime PR, then the Nexus-new pin +
   mirror PR and the trusted-anchor PR (the procedure of #1908/#1914). ``--dry-run`` prints the
   plan and makes no effect (no attestation, no git, no gh). Each branch is built from the exact
   current ``origin/main`` SHA, and the tool persists its authored head, base, per-file sha256,
   PR number, Issue numbers and merge SHA immediately after each effect; a resumed run finds its
   PRs (also merged ones) by branch and Issues by a title tag, so nothing is duplicated.
6. :func:`review` runs an isolated ``claude -p`` (pinned model, ``--tools ""``,
   ``--strict-mcp-config``, ``--setting-sources ""``, plan mode, empty temporary cwd) with the
   exact PR diff inline and a fixed scope prompt; strict JSON ``{verdict, reasons}`` is posted on
   the PR with reasons sanitized (no paths/secrets, length-capped: both repos are public).
   Anything else is ``REJECT``.
7. :func:`merge` needs a recorded ACCEPT for the current head, every required check green on
   that head (no required checks = blocked), the deterministic :func:`verify_pr_scope` guard
   (head == the SHA this tool pushed, changed files == exactly the scope list, each file's bytes at
   that head == the rendered bytes, main still == the base it was built on; a moved base is
   rebuilt once by the tool and re-reviewed), and an optional ``--pre-merge-hook`` GO; it merges
   with ``--match-head-commit``. A head the tool did not author is never merged. Nexus-new
   merges only after nexus-runtime; the pin PR is rebuilt by the tool after the anchor merge.
8. :func:`notify` comments on #1996 (old -> new, receipts, merge SHAs, Gateway reload pending
   Owner #526 activation).
9. :func:`run` adds a lock file, an idempotency key (catalog hash + yaml hash) with PR reuse, and
   a durable JSON receipt per run under ``~/.local/state/nexus-workforce-autoupdate/``.

Issues opened by this tool use ``on_merge: KEEP_OPEN``: #1216 V12 requires ``v12-closable``
before any Issue created after 2026-10-13T04:05:51Z is closed, so closing stays manual.
The live Gateway reload is out of scope (#526 R1, Owner BREAK_GLASS).
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import datetime as _dt
import fcntl
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import textwrap
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

ISSUE_NUMBER = 1996
NEXUS_REPO = "James3014/Nexus-new"
_ISSUE_GATE_WORKFLOW = ".github/workflows/nexus-core-issue-completion.yml"
_TRUSTED_UNIVERSE_RE = re.compile(
    r"^\s*evidence-universe:\s*[\"']?trusted-config[\"']?\s*$", re.MULTILINE
)
RUNTIME_REPO = "James3014/nexus-runtime"
RUNTIME_GIT_URL = "https://github.com/James3014/nexus-runtime.git"
RUNTIME_YAML_PATH = "src/nexus_runtime/planning/config/model_workforce.yaml"
MIRROR_YAML_PATH = "nexus/config/model_workforce.yaml"
DEFAULT_STATE_DIR = Path.home() / ".local/state/nexus-workforce-autoupdate"
DEFAULT_REVIEWER_MODEL = "claude-opus-5-5"
REVIEWER_TOOLS = ""  # no tools: the exact diff is inline in the prompt
REVIEW_COMMENT_MARKER = "<!-- WORKFORCE_AUTOUPDATE_REVIEW_V1"
NOTIFY_MARKER = "<!-- WORKFORCE_AUTOUPDATE_NOTIFY_V1"

AGY_FLASH_RE = re.compile(r"\Agemini-([0-9]+)\.([0-9]+)-flash-(high|medium|low)\Z", re.ASCII)
AGY_VERSION_RE = re.compile(r"\A[0-9]+\.[0-9]+\.[0-9]+\Z", re.ASCII)
_AUTONOMY_RE = re.compile(r"\AL([0-9]+)", re.ASCII)
_SHA40_RE = re.compile(r"\A[0-9a-f]{40}\Z", re.ASCII)
NEW_WORKER_STATE = "REGISTERED_CONDITIONAL"
INHERITABLE_STATES = frozenset({"PROVEN_MAINCHAIN", "REGISTERED_CONDITIONAL"})
# Predecessor keys that describe the old model's evidence, never the new one's.
NOT_INHERITED_KEYS = (
    "calibration_evidence",
    "model_id_note",
    "availability_note",
    "reason",
    "benchmark_ref",
    "runtime_verification",
    "blocker",
    "capability_grade",
    "current_assignment",
)

PIN_FILES = (
    "pyproject.toml",
    "requirements/canonical-runtime.txt",
    "uv.lock",
    ".nexus-core/config.toml",
)
LOCK_DIGEST_FILES = (
    "product/execution/profiles/python-oci-pytest-v1.json",
    "product/execution/profiles/python-oci-pytest-v1.lock",
    "product/execution/python_runner.py",
)
ANCHOR_FILE = "scripts/ops/trusted_deletion_anchor.py"
ANCHOR_TEST_FILE = "tests/ops/test_trusted_deletion_anchor.py"
SCOPE_FILES = {
    "runtime": (RUNTIME_YAML_PATH,),
    "pin": (*PIN_FILES, *LOCK_DIGEST_FILES, MIRROR_YAML_PATH),
    "anchor": (ANCHOR_FILE, ANCHOR_TEST_FILE),
}
MERGE_METHOD = {RUNTIME_REPO: "--merge", NEXUS_REPO: "--squash"}

# Outcomes
NOOP = "NOOP"
SWITCH = "SWITCH"
BLOCKED = "BLOCKED"
ACCEPT = "ACCEPT"
REJECT = "REJECT"


# ---------------------------------------------------------------------------
# Command runner (injectable; tests pass a fake)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CmdResult:
    rc: int
    stdout: str = ""
    stderr: str = ""


Runner = Callable[..., CmdResult]


def subprocess_runner(
    argv: Sequence[str],
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    timeout: float = 600.0,
    env: Mapping[str, str] | None = None,
) -> CmdResult:
    try:
        proc = subprocess.run(
            list(argv),
            cwd=str(cwd) if cwd else None,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env=dict(env) if env is not None else None,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CmdResult(rc=127, stderr=f"{type(exc).__name__}: {exc}")
    return CmdResult(rc=proc.returncode, stdout=proc.stdout or "", stderr=proc.stderr or "")


def _sha256(data: bytes | str) -> str:
    raw = data.encode("utf-8") if isinstance(data, str) else data
    return hashlib.sha256(raw).hexdigest()


# ---------------------------------------------------------------------------
# 1. Discover
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CatalogEntry:
    model_id: str
    label: str
    family: str
    tier: str
    version: tuple[int, int]


@dataclass(frozen=True)
class Catalog:
    ok: bool
    entries: tuple[CatalogEntry, ...] = ()
    unrecognized: tuple[str, ...] = ()
    raw_sha256: str = ""
    agy_version: str = ""
    error: str = ""

    @property
    def served_ids(self) -> frozenset[str]:
        return frozenset(entry.model_id for entry in self.entries)


def parse_model_id(model_id: str) -> tuple[str, str, tuple[int, int]] | None:
    """``gemini-3.8-flash-medium`` -> ``("gemini-flash", "medium", (3, 8))``."""
    match = AGY_FLASH_RE.match(str(model_id or ""))
    if not match:
        return None
    major, minor, tier = int(match.group(1)), int(match.group(2)), match.group(3)
    if f"gemini-{major}.{minor}-flash-{tier}" != model_id:  # canonical: no leading zeros
        return None
    return "gemini-flash", tier, (major, minor)


def safe_agy_version(raw: str) -> str:
    """ASCII ``X.Y.Z`` or ``unknown``: no free provider text reaches the yaml or notes."""
    value = str(raw or "").strip()
    return value if AGY_VERSION_RE.match(value) else "unknown"


def expected_label(model_id: str) -> str | None:
    parsed = parse_model_id(model_id)
    if parsed is None:
        return None
    _, tier, (major, minor) = parsed
    return f"Gemini {major}.{minor} Flash ({tier.capitalize()})"


def parse_catalog(stdout: str, *, agy_version: str = "") -> Catalog:
    """Parse ``agy models`` stdout (``id<TAB>label`` lines). Never reads error text."""
    entries: list[CatalogEntry] = []
    unrecognized: list[str] = []
    seen: set[str] = set()
    versions: set[tuple[str, str, tuple[int, int]]] = set()
    for raw in stdout.splitlines():
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            unrecognized.append(line)
            continue
        model_id, label = parts[0].strip(), parts[1].strip()
        parsed = parse_model_id(model_id)
        if parsed is None or expected_label(model_id) != label:
            unrecognized.append(line)
            continue
        if model_id in seen or parsed in versions:
            return Catalog(
                ok=False, raw_sha256=_sha256(stdout), error=f"CATALOG_DUPLICATE_VERSION:{model_id}"
            )
        seen.add(model_id)
        versions.add(parsed)
        family, tier, version = parsed
        entries.append(CatalogEntry(model_id, label, family, tier, version))
    if not entries and not unrecognized:
        return Catalog(ok=False, raw_sha256=_sha256(stdout), error="CATALOG_EMPTY")
    return Catalog(
        ok=True,
        entries=tuple(entries),
        unrecognized=tuple(unrecognized),
        raw_sha256=_sha256(stdout),
        agy_version=safe_agy_version(agy_version) if agy_version else "",
    )


def discover(
    *,
    agy_bin: str = "agy",
    catalog_file: Path | None = None,
    runner: Runner = subprocess_runner,
) -> Catalog:
    if catalog_file is not None:
        try:
            return parse_catalog(Path(catalog_file).read_text(encoding="utf-8"))
        except OSError as exc:
            return Catalog(ok=False, error=f"CATALOG_FILE_UNREADABLE:{exc}")
    res = runner([agy_bin, "models"], timeout=120.0)
    if res.rc != 0:
        return Catalog(ok=False, error=f"AGY_MODELS_RC_{res.rc}")
    version = runner([agy_bin, "--version"], timeout=30.0)
    agy_version = (
        version.stdout.strip().splitlines()[0] if version.rc == 0 and version.stdout else ""
    )
    return parse_catalog(res.stdout, agy_version=agy_version)


# ---------------------------------------------------------------------------
# 2. Decide
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    kind: str  # NOOP | SWITCH | BLOCKED
    reason: str = ""
    roles: tuple[str, ...] = ()
    old_worker: str = ""
    old_model: str = ""
    new_model: str = ""
    new_label: str = ""
    new_worker: str = ""
    register_new_worker: bool = False
    predecessor_retired: bool = False
    flipped_pins: tuple[str, ...] = ()
    untouched_pins: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


def autonomy_rank(value: object) -> int | None:
    match = _AUTONOMY_RE.match(str(value or ""))
    return int(match.group(1)) if match else None


def new_worker_id(new_model: str, workers: Mapping[str, Any]) -> str | None:
    parsed = parse_model_id(new_model)
    if parsed is None:
        return None
    _, tier, (major, minor) = parsed
    base = f"agy_flash_{major}{minor}"
    for candidate in ((base,) if tier == "medium" else ()) + (f"{base}_{tier}",):
        if candidate not in workers:
            return candidate
    return None


def _role_decision(
    role: str, worker_id: str, workers: Mapping[str, Any], catalog: Catalog
) -> Decision | None:
    worker = workers.get(worker_id)
    if not isinstance(worker, Mapping):
        return Decision(BLOCKED, f"DEFAULT_WORKER_UNKNOWN:{role}:{worker_id}")
    if worker.get("provider") != "agy":
        return None
    model = str(worker.get("model") or "")
    parsed = parse_model_id(model)
    if parsed is None:
        return Decision(NOOP, notes=(f"default_model_format_unknown:{role}:{model}",))
    family, tier, version = parsed
    served = model in catalog.served_ids
    newer = [
        entry
        for entry in catalog.entries
        if entry.family == family and entry.tier == tier and entry.version > version
    ]
    if not newer:
        if served:
            return Decision(NOOP)
        return Decision(BLOCKED, f"DEFAULT_RETIRED_NO_SAME_TIER_SUCCESSOR:{role}:{model}")
    target = max(newer, key=lambda entry: entry.version)
    common = {
        "roles": (role,),
        "old_worker": worker_id,
        "old_model": model,
        "new_model": target.model_id,
        "new_label": target.label,
        "predecessor_retired": not served,
    }
    pred_rank = autonomy_rank(worker.get("autonomy"))
    if pred_rank is None:
        return Decision(BLOCKED, f"PREDECESSOR_AUTONOMY_UNPARSEABLE:{worker_id}", **common)
    existing = [
        wid
        for wid, data in workers.items()
        if isinstance(data, Mapping)
        and data.get("provider") == "agy"
        and data.get("model") == target.model_id
    ]
    if existing:
        reuse = existing[0]
        data = workers[reuse]
        rank = autonomy_rank(data.get("autonomy"))
        if rank is None or rank > pred_rank:
            return Decision(BLOCKED, f"AUTONOMY_WOULD_RAISE:{reuse}", new_worker=reuse, **common)
        if data.get("availability") != "AVAILABLE":
            return Decision(BLOCKED, f"SUCCESSOR_REGISTERED_UNAVAILABLE:{reuse}", **common)
        if role not in (data.get("roles") or []):
            return Decision(BLOCKED, f"SUCCESSOR_LACKS_ROLE:{reuse}:{role}", **common)
        if data.get("state") not in INHERITABLE_STATES:
            return Decision(BLOCKED, f"SUCCESSOR_STATE_NOT_ADMISSIBLE:{reuse}", **common)
        return Decision(SWITCH, new_worker=reuse, register_new_worker=False, **common)
    if worker.get("state") not in INHERITABLE_STATES:
        return Decision(BLOCKED, f"PREDECESSOR_STATE_NOT_INHERITABLE:{worker_id}", **common)
    new_id = new_worker_id(target.model_id, workers)
    if new_id is None:
        return Decision(BLOCKED, f"WORKER_ID_UNAVAILABLE:{target.model_id}", **common)
    return Decision(SWITCH, new_worker=new_id, register_new_worker=True, **common)


def _online(policy: Mapping[str, Any]) -> Mapping[str, Any]:
    routing = policy.get("routing") or {}
    online = routing.get("online") if isinstance(routing, Mapping) else None
    return online if isinstance(online, Mapping) else {}


def decide(policy: Mapping[str, Any], catalog: Catalog) -> Decision:
    """Pure decision over the parsed yaml and the catalog."""
    if not catalog.ok:
        return Decision(BLOCKED, f"CATALOG_NOT_OK:{catalog.error}")
    workers = policy.get("workers")
    online = _online(policy)
    defaults = online.get("route_defaults")
    if not isinstance(workers, Mapping) or not isinstance(defaults, Mapping) or not defaults:
        return Decision(BLOCKED, "POLICY_SHAPE_UNEXPECTED")
    notes: list[str] = [f"unrecognized_catalog_line:{line}" for line in catalog.unrecognized]
    switches: dict[tuple[str, str], Decision] = {}
    for role in defaults:
        worker_id = online.get(role)
        if not isinstance(worker_id, str):
            return Decision(BLOCKED, f"ROUTE_NOT_A_WORKER:{role}")
        result = _role_decision(str(role), worker_id, workers, catalog)
        if result is None:
            continue
        notes.extend(result.notes)
        if result.kind == BLOCKED:
            return Decision(BLOCKED, result.reason, notes=tuple(notes))
        if result.kind == SWITCH:
            key = (result.old_worker, result.new_model)
            prior = switches.get(key)
            switches[key] = (
                result
                if prior is None
                else Decision(**{**asdict(prior), "roles": prior.roles + result.roles})
            )
    if not switches:
        return Decision(NOOP, notes=tuple(notes))
    if len(switches) > 1:
        return Decision(BLOCKED, "MULTIPLE_DISTINCT_SWITCHES", notes=tuple(notes))
    chosen = next(iter(switches.values()))
    pins = [
        f"{section}.{name}.{role}"
        for section in ("campaign_routing", "consumer_routing")
        for name, routes in (online.get(section) or {}).items()
        if isinstance(routes, Mapping)
        for role, target in routes.items()
        if target == chosen.old_worker
    ]
    # A retired predecessor's campaign/consumer pins are unservable and must follow the default;
    # a merely superseded predecessor keeps its pins (exact experiment identities stay intact).
    flipped = tuple(pins) if chosen.predecessor_retired else ()
    untouched = () if chosen.predecessor_retired else tuple(pins)
    return Decision(**{
        **asdict(chosen),
        "flipped_pins": flipped,
        "untouched_pins": untouched,
        "notes": tuple(notes),
    })


# ---------------------------------------------------------------------------
# 3. Attest
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Attestation:
    ok: bool
    model_id: str
    expected_label: str
    reason: str = ""
    observed_model: str = ""
    observed_label: str = ""
    receipt: dict[str, Any] = field(default_factory=dict)
    attested_at: str = ""


AttestFn = Callable[[str], Mapping[str, Any]]

ATTEST_PROMPT = 'Reply with exactly this JSON and nothing else: {"status": "OK", "patch": ""}'


def live_attest_call(model_id: str) -> Mapping[str, Any]:
    """One leased, contained Agy call; reuses the #1932 bench lane (lease + identity)."""
    from scripts.bench.agy_account_lease import ACCOUNT_ALLOWLIST_ENV
    from scripts.bench.agy_provider import ask_direct_agy_patch

    if not str(os.environ.get(ACCOUNT_ALLOWLIST_ENV) or "").strip():
        return {"error_category": f"ALLOWLIST_REQUIRED:{ACCOUNT_ALLOWLIST_ENV}"}
    env = {**os.environ, "NEXUS_AGY_MODEL": model_id, "NEXUS_AGY_BENCH_NO_TOOLS_PREFIX": "1"}
    payload, _raw = ask_direct_agy_patch(prompt=ATTEST_PROMPT, timeout_sec=120, env=env)
    return payload


def attest(model_id: str, label: str, *, call: AttestFn = live_attest_call) -> Attestation:
    try:
        payload = dict(call(model_id))
    except Exception as exc:  # noqa: BLE001 - any failure is a fail-closed attestation
        return Attestation(
            False, model_id, label, reason=f"ATTEST_CALL_FAILED:{type(exc).__name__}"
        )
    safe = {
        key: payload.get(key)
        for key in (
            "requested_model",
            "observed_model",
            "observed_model_label",
            "model_identity_status",
            "model_identity_reason",
            "provider_call_attempted",
            "account_pool_source",
            "account_alias_hash",
            "lease_id_hash",
            "account_quota_state",
            "agy_no_tools_prefix_applied",
            "error_category",
        )
        if key in payload
    }
    observed = str(payload.get("observed_model") or "")
    observed_label = str(payload.get("observed_model_label") or "")
    common = {"observed_model": observed, "observed_label": observed_label, "receipt": safe}
    if payload.get("model_identity_status") != "MODEL_IDENTITY_OK":
        reason = str(payload.get("model_identity_status") or payload.get("error_category") or "")
        return Attestation(False, model_id, label, reason=f"IDENTITY_NOT_OK:{reason}", **common)
    if observed != model_id or observed_label != label:
        return Attestation(False, model_id, label, reason="IDENTITY_MISMATCH", **common)
    if payload.get("agy_no_tools_prefix_applied") is not True:
        return Attestation(False, model_id, label, reason="NO_TOOLS_PREFIX_MISSING", **common)
    return Attestation(True, model_id, label, **common)


# ---------------------------------------------------------------------------
# 4. Render (surgical text edit + dict cross-check + real validator)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RenderResult:
    ok: bool
    text: str = ""
    reason: str = ""
    validator: str = ""


def _section(lines: list[str], header: str) -> tuple[int, int]:
    start = lines.index(header)
    end = start + 1
    while end < len(lines) and not (lines[end] and not lines[end][0].isspace()):
        end += 1
    return start, end


def _block(lines: list[str], start: int, end: int, header: str, indent: int) -> tuple[int, int]:
    """Span of ``<indent>header`` and its deeper-indented body inside ``[start, end)``."""
    prefix = " " * indent
    begin = lines.index(prefix + header, start, end)
    stop = begin + 1
    while stop < end and (not lines[stop].strip() or _indent(lines[stop]) > indent):
        stop += 1
    while stop > begin + 1 and not lines[stop - 1].strip():
        stop -= 1
    return begin, stop


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _key_span(block: list[str], key: str, indent: int = 4) -> tuple[int, int] | None:
    pattern = re.compile(rf"^ {{{indent}}}{re.escape(key)}:(\s|$)")
    for i, line in enumerate(block):
        if pattern.match(line):
            j = i + 1
            while j < len(block) and block[j].strip() and _indent(block[j]) > indent:
                j += 1
            return i, j
    return None


def _set_key(block: list[str], key: str, value: str, *, after: str | None = None) -> None:
    new = f"    {key}: {value}"
    span = _key_span(block, key)
    if span is not None:
        block[span[0] : span[1]] = [new]
        return
    anchor = _key_span(block, after) if after else None
    block.insert(anchor[1] if anchor else len(block), new)


def _remove_key(block: list[str], key: str) -> None:
    span = _key_span(block, key)
    if span is not None:
        del block[span[0] : span[1]]


def _folded(key: str, text: str) -> list[str]:
    body = textwrap.wrap(text, width=74, break_on_hyphens=False, break_long_words=False)
    return [f"    {key}: >-", *[f"      {line}" for line in body]]


def _set_folded(block: list[str], key: str, text: str) -> None:
    _remove_key(block, key)
    block.extend(_folded(key, text))


def _yaml_scalar(value: str) -> str:
    return yaml.safe_dump(value, default_style=None, width=1000).strip().removesuffix("...").strip()


ValidatorFn = Callable[[str], str]  # returns "" when valid, else the error text


def validate_with_runtime(text: str, *, runtime_src: Path | None = None) -> str:
    """Run the real ``WorkforcePolicyLoader`` on ``text`` ("" = valid).

    ``runtime_src`` is a nexus-runtime ``src`` directory (the checkout being changed); without it
    the installed (pinned) ``nexus_runtime`` package validates.
    """
    with tempfile.TemporaryDirectory(prefix="wf-autoupdate-") as tmp:
        path = Path(tmp) / "model_workforce.yaml"
        path.write_text(text, encoding="utf-8")
        code = (
            "import sys\n"
            "if sys.argv[2]: sys.path.insert(0, sys.argv[2])\n"
            "from nexus_runtime.planning.services.model_workforce_policy import "
            "WorkforcePolicyLoader\n"
            "WorkforcePolicyLoader(sys.argv[1]).load()\n"
        )
        res = subprocess_runner(
            [sys.executable, "-c", code, str(path), str(runtime_src or "")], timeout=120.0
        )
    if res.rc == 0:
        return ""
    tail = (res.stderr or res.stdout).strip().splitlines()
    return tail[-1] if tail else f"validator_rc_{res.rc}"


def _retire_note(decision: Decision, agy_version: str, today: str) -> str:
    return (
        f"Unavailable since {today}: Agy {safe_agy_version(agy_version)} no longer lists "
        f"{decision.old_model} in its model catalog (agy models). Replaced as default by "
        f"{decision.new_worker} ({decision.new_model}) by the #1996 automatic updater after a "
        "live identity attestation. Kept registered for history."
    )


def _new_worker_note(decision: Decision, attestation_sha: str, today: str) -> str:
    return (
        f"Registered {today} by the #1996 automatic updater as the same-family, same-tier "
        f"successor of {decision.old_worker} ({decision.old_model}). Model id "
        f"{decision.new_model} is live-attested (observed id and backend label "
        f'"{decision.new_label}", receipt sha256:{attestation_sha}). Autonomy is inherited '
        "from the predecessor and not raised; the predecessor's calibration evidence is not "
        "inherited."
    )


def render_change(
    text: str,
    decision: Decision,
    *,
    today: str,
    agy_version: str = "",
    attestation_sha: str = "",
    validator: ValidatorFn | None = None,
) -> RenderResult:
    if decision.kind != SWITCH:
        return RenderResult(False, reason="NOT_A_SWITCH")
    policy = yaml.safe_load(text)
    expected = copy.deepcopy(policy)
    lines = text.split("\n")
    try:
        w_start, w_end = _section(lines, "workers:")
        old_start, old_end = _block(lines, w_start, w_end, f"{decision.old_worker}:", 2)
    except ValueError:
        return RenderResult(False, reason="WORKER_BLOCK_NOT_FOUND")
    old_block = lines[old_start:old_end]
    workers = expected["workers"]
    pred = workers[decision.old_worker]

    # Predecessor: no longer the default; unavailable when the provider stopped serving it.
    _set_key(old_block, "default_route", "false", after="preferred_context")
    pred["default_route"] = False
    if decision.predecessor_retired:
        reason = f"provider_no_longer_serves_model_agy_{safe_agy_version(agy_version)}_{today}"
        _set_key(old_block, "availability", "UNAVAILABLE")
        _set_key(old_block, "reason", reason, after="availability")
        note = _retire_note(decision, agy_version, today)
        _set_folded(old_block, "availability_note", note)
        pred.update(availability="UNAVAILABLE", reason=reason, availability_note=note)

    new_lines: list[str] = []
    if decision.register_new_worker:
        block = [f"  {decision.new_worker}:", *lines[old_start + 1 : old_end]]
        for key in NOT_INHERITED_KEYS:
            _remove_key(block, key)
        _set_key(block, "model", decision.new_model)
        _set_key(block, "state", NEW_WORKER_STATE)
        _set_key(block, "availability", "AVAILABLE")
        _set_key(block, "default_route", "true", after="preferred_context")
        note = _new_worker_note(decision, attestation_sha, today)
        _set_folded(block, "model_id_note", note)
        new_lines = block
        original = yaml.safe_load(text)["workers"][decision.old_worker]
        entry = {
            **{k: v for k, v in copy.deepcopy(original).items() if k not in NOT_INHERITED_KEYS},
            "model": decision.new_model,
            "state": NEW_WORKER_STATE,
            "availability": "AVAILABLE",
            "default_route": True,
            "model_id_note": note,
        }
        workers[decision.new_worker] = entry
        lines[old_start:old_end] = old_block + new_lines
    else:
        lines[old_start:old_end] = old_block
        w_start, w_end = _section(lines, "workers:")
        n_start, n_end = _block(lines, w_start, w_end, f"{decision.new_worker}:", 2)
        new_block = lines[n_start:n_end]
        _set_key(new_block, "default_route", "true", after="preferred_context")
        lines[n_start:n_end] = new_block
        workers[decision.new_worker]["default_route"] = True

    # Routes: routing.online.<role> and route_defaults.<role>.current_default only.
    try:
        r_start, r_end = _section(lines, "routing:")
        o_start, o_end = _block(lines, r_start, r_end, "online:", 2)
    except ValueError:
        return RenderResult(False, reason="ROUTING_BLOCK_NOT_FOUND")
    online = expected["routing"]["online"]
    for role in decision.roles:
        direct = f"    {role}: {decision.old_worker}"
        hits = [i for i in range(o_start, o_end) if lines[i] == direct]
        if len(hits) != 1:
            return RenderResult(False, reason=f"ROUTE_LINE_NOT_UNIQUE:{role}")
        lines[hits[0]] = f"    {role}: {decision.new_worker}"
        try:
            d_start, d_end = _block(lines, o_start, o_end, "route_defaults:", 4)
            rd_start, rd_end = _block(lines, d_start, d_end, f"{role}:", 6)
        except ValueError:
            return RenderResult(False, reason=f"ROUTE_DEFAULT_NOT_FOUND:{role}")
        cur = f"        current_default: {decision.old_worker}"
        cur_hits = [i for i in range(rd_start, rd_end) if lines[i] == cur]
        if len(cur_hits) != 1:
            return RenderResult(False, reason=f"ROUTE_DEFAULT_LINE_NOT_UNIQUE:{role}")
        lines[cur_hits[0]] = f"        current_default: {decision.new_worker}"
        online[role] = decision.new_worker
        online["route_defaults"][role]["current_default"] = decision.new_worker

    for pin in decision.flipped_pins:
        section, name, role = pin.split(".", 2)
        try:
            s_start, s_end = _block(lines, o_start, o_end, f"{section}:", 4)
            p_start, p_end = _block(lines, s_start, s_end, f"{name}:", 6)
        except ValueError:
            return RenderResult(False, reason=f"PIN_NOT_FOUND:{pin}")
        old = f"        {role}: {decision.old_worker}"
        hits = [i for i in range(p_start, p_end) if lines[i] == old]
        if len(hits) != 1:
            return RenderResult(False, reason=f"PIN_LINE_NOT_UNIQUE:{pin}")
        lines[hits[0]] = f"        {role}: {decision.new_worker}"
        online[section][name][role] = decision.new_worker

    lv = [i for i, line in enumerate(lines) if line.startswith("last_verified:")]
    if len(lv) != 1:
        return RenderResult(False, reason="LAST_VERIFIED_NOT_UNIQUE")
    lines[lv[0]] = f"last_verified: {_yaml_scalar(today)}"
    expected["last_verified"] = today

    new_text = "\n".join(lines)
    try:
        parsed = yaml.safe_load(new_text)
    except yaml.YAMLError as exc:
        return RenderResult(False, new_text, reason=f"RENDERED_YAML_INVALID:{exc}")
    if parsed != expected:
        return RenderResult(False, new_text, reason="RENDER_DIFFERS_FROM_INTENDED_TRANSFORM")
    error = (validator or validate_with_runtime)(new_text)
    if error:
        return RenderResult(False, new_text, reason="VALIDATOR_REJECTED", validator=error)
    return RenderResult(True, new_text, validator="OK")


# ---------------------------------------------------------------------------
# Nexus-new pin + mirror and trusted-anchor file rendering (#1908 / #1914 procedure)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FileSet:
    ok: bool
    files: dict[str, bytes] = field(default_factory=dict)
    reason: str = ""


def render_pin_files(root: Path, *, old_sha: str, new_sha: str, mirror_yaml: bytes) -> FileSet:
    """Pin bump: runtime sha in the four pin files, uv.lock digest in the OCI profile files."""
    if not (_SHA40_RE.match(old_sha) and _SHA40_RE.match(new_sha)) or old_sha == new_sha:
        return FileSet(False, reason="BAD_RUNTIME_SHA")
    files: dict[str, bytes] = {}
    for rel in PIN_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        if old_sha not in text:
            return FileSet(False, reason=f"OLD_PIN_NOT_FOUND:{rel}")
        files[rel] = text.replace(old_sha, new_sha).encode("utf-8")
    old_lock = _sha256((root / "uv.lock").read_bytes())
    new_lock = _sha256(files["uv.lock"])
    for rel in LOCK_DIGEST_FILES:
        text = (root / rel).read_text(encoding="utf-8")
        if text.count(old_lock) != 1:
            return FileSet(False, reason=f"LOCK_DIGEST_NOT_UNIQUE:{rel}")
        files[rel] = text.replace(old_lock, new_lock).encode("utf-8")
    files[MIRROR_YAML_PATH] = mirror_yaml
    return FileSet(True, files)


def render_anchor_files(
    root: Path,
    *,
    old_sha: str,
    new_sha: str,
    pin_pr: int,
    pin_issue: int,
    transition: tuple[str, str, str, str],
) -> FileSet:
    """Trusted anchor: new runtime identity plus a one-use four-way binding for ``pin_pr``."""
    anchor = (root / ANCHOR_FILE).read_text(encoding="utf-8")
    tests = (root / ANCHOR_TEST_FILE).read_text(encoding="utf-8")
    if anchor.count(f'"{old_sha}"') != 1 or tests.count(f'"{old_sha}"') != 1:
        return FileSet(False, reason="OLD_RUNTIME_IDENTITY_NOT_UNIQUE")
    name = f"TRUSTED_PR{pin_pr}_DEPENDENCY_SNAPSHOT_TRANSITION"
    if name in anchor:
        return FileSet(False, reason="TRANSITION_ALREADY_PRESENT")
    hashes = "".join(f'        "{h}",\n' for h in transition)
    record = (
        f"# Exact one-use, four-way binding for PR #{pin_pr} (Issue #{pin_issue}, #1996\n"
        f"# automatic Workforce model update; nexus-runtime {old_sha[:7]} -> {new_sha[:7]}).\n"
        f"{name}: tuple[int, tuple[str, str, str, str]] = (\n"
        f"    {pin_pr},\n    (\n{hashes}    ),\n)\n"
    )
    marker = "\nREQUIRED_EVIDENCE_KEYS = {"
    tuple_re = re.compile(
        r"(        TRUSTED_PR\d+_DEPENDENCY_SNAPSHOT_TRANSITION,\n)(    \)\n    for authorized_transition_record)"
    )
    if anchor.count(marker) != 1 or len(tuple_re.findall(anchor)) != 1:
        return FileSet(False, reason="ANCHOR_LAYOUT_UNEXPECTED")
    anchor = anchor.replace(f'"{old_sha}"', f'"{new_sha}"')
    anchor = anchor.replace(marker, f"{record}{marker}", 1)
    anchor = tuple_re.sub(rf"\g<1>        {name},\n\g<2>", anchor, count=1)
    tests = tests.replace(f'"{old_sha}"', f'"{new_sha}"')
    tests = tests.rstrip("\n") + "\n" + _anchor_tests(name, pin_pr, transition)
    return FileSet(True, {ANCHOR_FILE: anchor.encode(), ANCHOR_TEST_FILE: tests.encode()})


def _anchor_tests(name: str, pr: int, transition: tuple[str, str, str, str]) -> str:
    hashes = "".join(f'            "{h}",\n' for h in transition)
    return f"""

def test_pr{pr}_dependency_snapshot_transition_is_exact_and_separate() -> None:
    assert trusted_anchor.{name} == (
        {pr},
        (
{hashes}        ),
    )


def test_pr{pr}_dependency_snapshot_transition_allows_only_exact_binding(monkeypatch) -> None:
    values = [b"trusted pyproject\\n", b"trusted lock\\n", b"head pyproject\\n", b"head lock\\n"]
    hashes = trusted_anchor.{name}[1]
    original_sha = trusted_anchor._sha
    digest_by_value = dict(zip(values, hashes, strict=True))
    monkeypatch.setattr(
        trusted_anchor,
        "_sha",
        lambda value: digest_by_value.get(value, original_sha(value)),
    )

    trusted_anchor._validate_trusted_dependency_contract(
        values[0],
        values[2],
        values[1],
        values[3],
        pull_request_number={pr},
        head_product_init_is_regular=True,
    )

    for index in range(4):
        tampered = list(values)
        tampered[index] += b"tampered"
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                tampered[0],
                tampered[2],
                tampered[1],
                tampered[3],
                pull_request_number={pr},
                head_product_init_is_regular=True,
            )

    for other_pr in ({pr - 1}, {pr + 1}):
        with pytest.raises(ValueError, match="PR dependency contract drifts from trusted default"):
            trusted_anchor._validate_trusted_dependency_contract(
                values[0],
                values[2],
                values[1],
                values[3],
                pull_request_number=other_pr,
                head_product_init_is_regular=True,
            )
"""


# ---------------------------------------------------------------------------
# PR bodies
# ---------------------------------------------------------------------------


def merge_lane_block() -> str:
    from nexus.contracts.github_orchestration import canonical_hash

    unsigned = {
        "attempt_id": None,
        "contract_kind": "OWNER_INLINE",
        "execution_lane": "DIRECT_CANONICAL",
        "issue_number": None,
        "owner_id": "James3014",
        "owner_lane_rebind": None,
        "schema": "nexus.merge_lane_binding.v1",
        "task_card_path": None,
        "task_card_sha256": None,
        "task_id": None,
    }
    payload = dict(sorted({**unsigned, "binding_hash": canonical_hash(unsigned)}.items()))
    return (
        "<!-- NEXUS_MERGE_LANE_V1\n"
        + json.dumps(payload, indent=2, sort_keys=True)
        + "\nNEXUS_MERGE_LANE_V1 -->"
    )


def intent_block(issue: int) -> str:
    body = json.dumps([{"issue": issue, "on_merge": "KEEP_OPEN"}], indent=2)
    return f"<!-- NEXUS_ISSUE_INTENT_V1\n{body}\nNEXUS_ISSUE_INTENT_V1 -->"


SCOPE_NOTE = (
    f"\nScope (Nexus-new#{ISSUE_NUMBER}, Owner decision 2026-10-13): same provider, family and "
    "tier only; autonomy inherited, never raised; fallbacks unchanged. Campaign/consumer pins "
    "move with the default ONLY when the predecessor is retired (no longer served, so the pin is "
    "unservable); a superseded but still-served predecessor keeps its pins, preserving exact "
    "experiment identities. The live Gateway reload stays on #526 (Owner BREAK_GLASS).\n"
)


def summary_lines(decision: Decision) -> str:
    action = "registered" if decision.register_new_worker else "reused"
    return (
        f"- `{decision.old_worker}` (`{decision.old_model}`) -> `{decision.new_worker}` "
        f"(`{decision.new_model}`, {action}) for roles {', '.join(decision.roles)}.\n"
        f"- Predecessor retired (not in `agy models`): {decision.predecessor_retired}.\n"
        f"- Campaign/consumer pins moved (retired predecessor): "
        f"{', '.join(decision.flipped_pins) or 'none'}.\n"
        f"- Campaign/consumer pins left untouched: {', '.join(decision.untouched_pins) or 'none'}.\n"
    )


def runtime_pr_body(decision: Decision, attestation: Attestation, issue: int) -> str:
    receipt = json.dumps(attestation.receipt, indent=2, sort_keys=True)
    return (
        f"Automatic Workforce model update (Nexus-new#{ISSUE_NUMBER}, option A).\n\n"
        f"{summary_lines(decision)}{SCOPE_NOTE}\n"
        "Only `model_workforce.yaml` changes; the real `WorkforcePolicyLoader` validated it. "
        "Merges only after an independent AI review ACCEPTs this exact head.\n\n"
        f"Attestation receipt:\n```json\n{receipt}\n```\n\n"
        f"Refs #{issue}\n<!-- NEXUS_CORE_ISSUE: {issue} -->\n\n"
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"
    )


def nexus_pr_body(kind: str, decision: Decision, issue: int, new_sha: str, extra: str = "") -> str:
    what = (
        f"Pin `nexus-runtime` -> `{new_sha}` and mirror `{MIRROR_YAML_PATH}` byte-identically."
        if kind == "pin"
        else f"Trusted anchor for the nexus-runtime pin bump to `{new_sha}`; merges before the pin PR."
    )
    return (
        f"<!-- NEXUS_CORE_ISSUE: {issue} -->\n\nRefs #{issue}, #{ISSUE_NUMBER}.\n\n{what}\n\n"
        f"{summary_lines(decision)}{SCOPE_NOTE}{extra}\n{intent_block(issue)}\n\n{merge_lane_block()}\n\n"
        "🤖 Generated with [Claude Code](https://claude.com/claude-code)\n"
    )


# ---------------------------------------------------------------------------
# GitHub operations
# ---------------------------------------------------------------------------


@dataclass
class GitHub:
    runner: Runner = subprocess_runner
    gh: str = "gh"

    def _json(self, argv: Sequence[str]) -> Any:
        res = self.runner([self.gh, *argv], timeout=120.0)
        if res.rc != 0 and not res.stdout.strip():
            raise RuntimeError(f"gh_failed:{argv[0]}:{argv[1]}:{res.rc}")
        return json.loads(res.stdout or "null")

    def pr_view(self, repo: str, pr: int) -> dict[str, Any]:
        data = self._json([
            "pr",
            "view",
            str(pr),
            "-R",
            repo,
            "--json",
            "number,state,headRefOid,mergeCommit,files",
        ])
        return data if isinstance(data, dict) else {}

    def prs_for_branch(self, repo: str, branch: str) -> list[dict[str, Any]]:
        """Every PR (any state) whose head is ``branch``: finds a merged one on resume."""
        data = self._json([
            "pr",
            "list",
            "-R",
            repo,
            "--head",
            branch,
            "--state",
            "all",
            "--json",
            "number,state,headRefOid",
        ])
        return [item for item in data or [] if isinstance(item, dict)]

    def file_sha_at(self, repo: str, path: str, ref: str) -> str:
        """sha256 of ``path`` at the exact commit ``ref`` as GitHub serves it."""
        if not _SHA40_RE.match(ref):
            raise RuntimeError("file_ref_not_sha40")
        res = self.runner(
            [
                self.gh,
                "api",
                "-H",
                "Accept: application/vnd.github.raw",
                f"repos/{repo}/contents/{path}?ref={ref}",
            ],
            timeout=120.0,
        )
        if res.rc != 0:
            raise RuntimeError(f"gh_contents_failed:{res.rc}")
        return _sha256(res.stdout)

    def main_sha(self, repo: str) -> str:
        res = self.runner(
            [self.gh, "api", f"repos/{repo}/commits/main", "--jq", ".sha"], timeout=120.0
        )
        sha = res.stdout.strip()
        if res.rc != 0 or not _SHA40_RE.match(sha):
            raise RuntimeError("main_sha_unavailable")
        return sha

    def find_issue_by_title_tag(self, repo: str, tag: str) -> int | None:
        data = self._json([
            "issue",
            "list",
            "-R",
            repo,
            "--state",
            "all",
            "--search",
            f"{tag} in:title",
            "--json",
            "number,title",
        ])
        hits = [
            int(item["number"])
            for item in data or []
            if isinstance(item, dict) and f"[{tag}]" in str(item.get("title"))
        ]
        if len(hits) > 1:
            raise RuntimeError(f"duplicate_issues_for_tag:{tag}")
        return hits[0] if hits else None

    def required_checks(self, repo: str, pr: int) -> list[dict[str, Any]]:
        """Required checks of the PR head; ``[]`` only for an explicit "no required checks"."""
        res = self.runner(
            [self.gh, "pr", "checks", str(pr), "-R", repo, "--required", "--json", "name,bucket"],
            timeout=120.0,
        )
        if res.stdout.strip():
            data = json.loads(res.stdout)
            return [item for item in data or [] if isinstance(item, dict)]
        if "no required checks" in (res.stderr + res.stdout).lower():
            return []
        if res.rc != 0:
            raise RuntimeError(f"gh_checks_failed:{res.rc}")
        return []

    def pr_diff(self, repo: str, pr: int) -> str:
        res = self.runner([self.gh, "pr", "diff", str(pr), "-R", repo], timeout=120.0)
        if res.rc != 0:
            raise RuntimeError(f"gh_pr_diff_failed:{res.rc}")
        return res.stdout

    def comment(self, repo: str, number: int, body: str, *, issue: bool = False) -> bool:
        kind = "issue" if issue else "pr"
        res = self.runner(
            [self.gh, kind, "comment", str(number), "-R", repo, "--body-file", "-"],
            input_text=body,
            timeout=120.0,
        )
        return res.rc == 0

    def merge(self, repo: str, pr: int, head: str) -> CmdResult:
        return self.runner(
            [
                self.gh,
                "pr",
                "merge",
                str(pr),
                "-R",
                repo,
                MERGE_METHOD.get(repo, "--squash"),
                "--match-head-commit",
                head,
            ],
            timeout=300.0,
        )


# ---------------------------------------------------------------------------
# 6. Review
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReviewResult:
    verdict: str
    reasons: tuple[str, ...]
    head: str
    recorded: bool = False


REVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": [ACCEPT, REJECT]},
        "reasons": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verdict", "reasons"],
    "additionalProperties": False,
}

REVIEW_PROMPT = """You are an independent reviewer for Nexus-new Issue #1996 (automatic Workforce
model-version update). You did not write this change. Review ONLY the exact diff below for
{repo} PR #{pr} at head {head} (PR kind: {kind}).

ACCEPT only if every statement holds; otherwise REJECT:
1. Every changed file is in this allow-list: {allowed}.
2. Workforce yaml changes (if any) only: register ONE new worker for the exact model id
   {new_model} under provider agy, copying the predecessor {old_worker} entry (same roles,
   requires, forbidden_actions/claims, preferred_context) with autonomy equal to the
   predecessor's (never higher) and state REGISTERED_CONDITIONAL, OR reuse the already-registered
   worker {new_worker}; flip default_route, routing.online.<role> and
   route_defaults.<role>.current_default from {old_worker} to {new_worker} for roles {roles};
   mark the predecessor UNAVAILABLE only if it is retired ({retired}); move exactly these
   campaign/consumer pins from {old_worker} to {new_worker}: [{flipped_pins}] (only when the
   predecessor is retired); bump last_verified. No other worker, route, fallback, pin, state
   list or policy key changes.
3. The new model stays in the same provider, family (Gemini Flash) and tier as {old_model}.
   No new provider, no tier/family/role change, no autonomy increase.
4. Pin PRs only replace the nexus-runtime commit sha and the matching uv.lock sha256 digests,
   and the mirror yaml content equals the runtime yaml change. Anchor PRs only replace the
   trusted nexus-runtime commit and add one exact four-hash transition record plus its tests.
5. Nothing touches Gateway activation, credentials, CI workflows or unrelated code.

Respond with JSON only: {{"verdict": "ACCEPT" | "REJECT", "reasons": [short strings]}}.

=== DIFF START ===
{diff}
=== DIFF END ===
"""


@dataclass
class Reviewer:
    """Isolated ``claude -p``: no tools, no MCP servers, no settings/hooks, empty cwd.

    The exact diff is inline in the prompt, so the reviewer needs nothing else. Flags verified
    against ``claude --help``: ``--tools ""`` disables every built-in tool,
    ``--strict-mcp-config`` (with no ``--mcp-config``) loads no MCP server, and
    ``--setting-sources ""`` loads no user/project/local settings (hooks, plugins, permissions).
    """

    runner: Runner = subprocess_runner
    claude_bin: str = str(Path.home() / ".local/bin/claude")
    model: str = DEFAULT_REVIEWER_MODEL

    def argv(self) -> list[str]:
        return [
            self.claude_bin,
            "-p",
            "--model",
            self.model,
            "--output-format",
            "json",
            "--json-schema",
            json.dumps(REVIEW_SCHEMA),
            "--tools",
            REVIEWER_TOOLS,
            "--strict-mcp-config",
            "--setting-sources",
            "",
            "--permission-mode",
            "plan",
            "--disallowedTools",
            "Bash,Edit,Write,NotebookEdit,WebFetch,WebSearch,Agent,Read,Grep,Glob",
            "--no-session-persistence",
        ]

    def __call__(self, prompt: str) -> tuple[str, tuple[str, ...]]:
        with tempfile.TemporaryDirectory(prefix="wf-review-") as cwd:
            res = self.runner(self.argv(), cwd=Path(cwd), input_text=prompt, timeout=900.0)
        if res.rc != 0:
            return REJECT, (f"reviewer_unavailable_rc_{res.rc}",)
        return parse_review_output(res.stdout)


def parse_review_output(stdout: str) -> tuple[str, tuple[str, ...]]:
    try:
        envelope = json.loads(stdout)
        if not isinstance(envelope, dict) or envelope.get("is_error"):
            return REJECT, ("reviewer_error_envelope",)
        verdict_obj = envelope.get("structured_output")
        if not isinstance(verdict_obj, dict):
            verdict_obj = json.loads(str(envelope.get("result") or ""))
    except (TypeError, ValueError):
        return REJECT, ("reviewer_output_not_json",)
    if not isinstance(verdict_obj, dict) or set(verdict_obj) != {"verdict", "reasons"}:
        return REJECT, ("reviewer_output_shape",)
    verdict, reasons = verdict_obj.get("verdict"), verdict_obj.get("reasons")
    if verdict not in (ACCEPT, REJECT) or not isinstance(reasons, list):
        return REJECT, ("reviewer_output_values",)
    return str(verdict), sanitize_reasons(reasons)


MAX_REASONS = 10
MAX_REASON_CHARS = 200
_SECRET_RE = re.compile(
    r"(?i)(?:sk-|ghp_|gho_|ghs_|ghu_|github_pat_|xox[abpr]-|ya29\.|akia)[a-z0-9_\-.]{6,}"
    r"|[A-Za-z0-9+/=_\-]{32,}",
    re.ASCII,
)
_PATH_RE = re.compile(
    r"(?:~|\$HOME|\.{1,2})?/[^\s'\"`)\]]+|[A-Za-z]:\\[^\s'\"`]+|\b[\w.\-]+/[\w.\-/]+",
    re.ASCII,
)


def sanitize_reason(text: object) -> str:
    """Both repos are public: no secrets, no paths, no control characters, bounded length."""
    value = _SECRET_RE.sub("<redacted>", str(text))
    value = _PATH_RE.sub("<path>", value)
    value = "".join(ch if ch.isprintable() else " " for ch in value)
    value = " ".join(value.split())
    return value[:MAX_REASON_CHARS]


def sanitize_reasons(reasons: Sequence[object]) -> tuple[str, ...]:
    return tuple(sanitize_reason(item) for item in list(reasons)[:MAX_REASONS])


def review(
    gh: GitHub,
    reviewer: Callable[[str], tuple[str, tuple[str, ...]]],
    *,
    repo: str,
    pr: int,
    head: str,
    kind: str,
    decision: Decision,
) -> ReviewResult:
    try:
        if gh.pr_view(repo, pr).get("headRefOid") != head:
            return ReviewResult(REJECT, ("head_drift_before_review",), head)
        diff = gh.pr_diff(repo, pr)
        if gh.pr_view(repo, pr).get("headRefOid") != head:
            return ReviewResult(REJECT, ("head_drift_during_review",), head)
    except (RuntimeError, ValueError) as exc:
        return ReviewResult(REJECT, (sanitize_reason(f"review_input_unavailable:{exc}"),), head)
    prompt = REVIEW_PROMPT.format(
        repo=repo,
        pr=pr,
        head=head,
        kind=kind,
        allowed=", ".join(SCOPE_FILES[kind]),
        new_model=decision.new_model,
        old_worker=decision.old_worker,
        new_worker=decision.new_worker,
        roles=", ".join(decision.roles),
        retired=decision.predecessor_retired,
        old_model=decision.old_model,
        diff=diff,
        flipped_pins=", ".join(decision.flipped_pins),
    )
    try:
        verdict, reasons = reviewer(prompt)
    except Exception as exc:  # noqa: BLE001 - reviewer failure is a REJECT
        verdict, reasons = REJECT, (f"reviewer_failed:{type(exc).__name__}",)
    if verdict not in (ACCEPT, REJECT):
        verdict, reasons = REJECT, ("reviewer_verdict_invalid",)
    reasons = sanitize_reasons(reasons)
    payload = {"verdict": verdict, "reasons": list(reasons), "head": head, "kind": kind}
    body = (
        f"{REVIEW_COMMENT_MARKER} head={head} -->\n"
        f"Independent review (#{ISSUE_NUMBER}): **{verdict}**\n\n"
        f"```json\n{json.dumps(payload, indent=2)}\n```\n"
    )
    recorded = gh.comment(repo, pr, body)
    if not recorded:
        return ReviewResult(REJECT, (*reasons, "review_not_recorded"), head, False)
    return ReviewResult(verdict, reasons, head, True)


# ---------------------------------------------------------------------------
# 7. Merge
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MergeResult:
    ok: bool
    reason: str = ""
    merge_sha: str = ""


def checks_state(gh: GitHub, repo: str, pr: int, head: str) -> str:
    """``GREEN`` / ``PENDING`` / ``RED:<names>`` / ``HEAD_DRIFT`` / ``NO_REQUIRED_CHECKS``."""
    if gh.pr_view(repo, pr).get("headRefOid") != head:
        return "HEAD_DRIFT"
    checks = gh.required_checks(repo, pr)
    if not checks:
        return "NO_REQUIRED_CHECKS"
    red = sorted(str(c.get("name")) for c in checks if c.get("bucket") in ("fail", "cancel"))
    if red:
        return "RED:" + ",".join(red)
    if any(c.get("bucket") != "pass" for c in checks):
        return "PENDING"
    # The checks belong to the head read before them; a push in between invalidates them.
    if gh.pr_view(repo, pr).get("headRefOid") != head:
        return "HEAD_DRIFT"
    return "GREEN"


def run_pre_merge_hook(
    hook: str | None, runner: Runner, *, repo: str, pr: int, head: str
) -> tuple[bool, str]:
    if not hook:
        return True, "no_hook"
    res = runner([*shlex.split(hook), repo, str(pr), head], timeout=6 * 3600.0)
    lines = res.stdout.strip().splitlines()
    if res.rc == 0 and lines and lines[-1].strip() == "GO":
        return True, "GO"
    return False, f"hook_no_go_rc_{res.rc}"


def merge(
    gh: GitHub,
    *,
    repo: str,
    pr: int,
    head: str,
    review_result: ReviewResult,
    pre_merge_hook: str | None = None,
    guard: Callable[[], str] | None = None,
) -> MergeResult:
    """Merge only an ACCEPTed, recorded, green, in-scope, tool-authored, up-to-date head.

    ``guard`` returns "" when the PR still has exactly the tool-authored head, exactly the scoped
    files with the rendered bytes, and the base it was built on; any text blocks the merge.
    """
    if review_result.verdict != ACCEPT or not review_result.recorded:
        return MergeResult(False, "REVIEW_NOT_ACCEPT")
    if review_result.head != head:
        return MergeResult(False, "REVIEW_HEAD_MISMATCH")
    state = checks_state(gh, repo, pr, head)
    if state != "GREEN":
        return MergeResult(False, f"CHECKS_{state}")
    if guard is not None and (problem := guard()):
        return MergeResult(False, f"GUARD_{problem}")
    ok, detail = run_pre_merge_hook(pre_merge_hook, gh.runner, repo=repo, pr=pr, head=head)
    if not ok:
        return MergeResult(False, f"PRE_MERGE_HOOK:{detail}")
    if checks_state(gh, repo, pr, head) != "GREEN":
        return MergeResult(False, "CHECKS_CHANGED_AFTER_HOOK")
    if guard is not None and (problem := guard()):
        return MergeResult(False, f"GUARD_{problem}")
    res = gh.merge(repo, pr, head)
    if res.rc != 0:
        return MergeResult(False, f"MERGE_FAILED_RC_{res.rc}")
    view = gh.pr_view(repo, pr)
    sha = str((view.get("mergeCommit") or {}).get("oid") or "")
    if view.get("state") != "MERGED" or not _SHA40_RE.match(sha):
        return MergeResult(False, "MERGE_UNCONFIRMED")
    return MergeResult(True, merge_sha=sha)


def verify_pr_scope(gh: GitHub, *, repo: str, kind: str, rec: Mapping[str, Any]) -> str:
    """Deterministic pre-merge scope check ("" = OK); independent of the AI reviewer."""
    head, base, digests = rec.get("head"), rec.get("base"), rec.get("file_sha") or {}
    if not (isinstance(head, str) and _SHA40_RE.match(head)) or not rec.get("pr"):
        return "NO_TOOL_AUTHORED_HEAD"
    view = gh.pr_view(repo, int(rec["pr"]))
    if view.get("headRefOid") != head:
        return "HEAD_NOT_TOOL_AUTHORED"
    paths = sorted(str(item.get("path")) for item in view.get("files") or [])
    if paths != sorted(SCOPE_FILES[kind]) or sorted(digests) != sorted(SCOPE_FILES[kind]):
        return "FILE_SCOPE_MISMATCH"
    for path, digest in sorted(digests.items()):
        if gh.file_sha_at(repo, path, head) != digest:
            return f"CONTENT_MISMATCH:{path}"
    if gh.main_sha(repo) != base:
        return "BASE_MOVED"
    return ""


def notify(gh: GitHub, *, decision: Decision, outcome: str, receipt: Mapping[str, Any]) -> bool:
    merges = receipt.get("merges") or {}
    body = (
        f"{NOTIFY_MARKER} key={receipt.get('idempotency_key', '')} -->\n"
        f"Workforce automatic model update: **{outcome}**\n\n{summary_lines(decision)}"
        f"- Attestation: {json.dumps(receipt.get('attestation', {}).get('receipt', {}))}\n"
        f"- PRs: {json.dumps(receipt.get('prs', {}))}\n"
        f"- Reviews: {json.dumps(receipt.get('reviews', {}))}\n"
        f"- Merge SHAs: {json.dumps(merges)}\n"
        f"- Run id: `{receipt.get('run_id', '')}` (receipt kept on the M5 host)\n"
        f"- Blocker: {sanitize_reason(receipt.get('reason') or 'none')}\n\n"
        "Gateway reload is pending Owner #526 activation (BREAK_GLASS); this run did not "
        "touch the live Gateway. Issues opened here stay open (KEEP_OPEN) until `v12-closable` "
        "says 可關閉.\n"
    )
    return gh.comment(NEXUS_REPO, ISSUE_NUMBER, body, issue=True)


# ---------------------------------------------------------------------------
# 5. Propose (plan + effects)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlanStep:
    repo: str
    action: str
    detail: str


def branch_name(decision: Decision, key: str, kind: str) -> str:
    return f"auto/workforce-{kind}-{decision.new_model}-{key[:12]}"


def build_plan(decision: Decision, key: str, *, runtime_issue: int | None) -> list[PlanStep]:
    rt_branch = branch_name(decision, key, "model")
    issue = f"#{runtime_issue}" if runtime_issue else "new Issue (nexus-certify markers)"
    return [
        PlanStep(
            "local",
            "attest",
            f"agy --mode plan --sandbox --model {decision.new_model} "
            f"(leased account, no-tools prefix); expect label '{decision.new_label}'",
        ),
        PlanStep(RUNTIME_REPO, "issue", f"bind runtime PR to {issue}"),
        PlanStep(RUNTIME_REPO, "branch+commit", f"{rt_branch}: {RUNTIME_YAML_PATH} only"),
        PlanStep(RUNTIME_REPO, "pr", f"gh pr create --base main --head {rt_branch}"),
        PlanStep(
            RUNTIME_REPO,
            "review",
            f"claude -p --model {DEFAULT_REVIEWER_MODEL} "
            "--tools '' --strict-mcp-config --setting-sources '' (diff inline, empty cwd); "
            "sanitized verdict posted on PR",
        ),
        PlanStep(
            RUNTIME_REPO,
            "merge",
            "ACCEPT + required checks green + exact scoped files/bytes at the tool-authored "
            "head + base unmoved; gh pr merge --merge --match-head-commit <head>",
        ),
        PlanStep(
            NEXUS_REPO,
            "issue",
            "pin Issue with the NEXUS_CORE_MATERIAL_TRANSITION canonical-runtime marker "
            "(+ NEXUS_CORE_EVIDENCE_UNIVERSE only if the gate is in issue-marker mode) (KEEP_OPEN)",
        ),
        PlanStep(
            NEXUS_REPO,
            "branch+commit",
            f"{branch_name(decision, key, 'pin')}: " + ", ".join(SCOPE_FILES["pin"]),
        ),
        PlanStep(NEXUS_REPO, "pr", "pin + mirror PR"),
        PlanStep(
            NEXUS_REPO,
            "branch+commit",
            f"{branch_name(decision, key, 'anchor')}: "
            + ", ".join(SCOPE_FILES["anchor"])
            + " (four-way hashes for the pin PR)",
        ),
        PlanStep(NEXUS_REPO, "pr+review+merge", "anchor PR first (--squash --match-head-commit)"),
        PlanStep(
            NEXUS_REPO,
            "rebuild+review+merge",
            "pin PR rebuilt by this tool on the new main after the anchor merged",
        ),
        PlanStep(NEXUS_REPO, "notify", f"comment on #{ISSUE_NUMBER}; Gateway reload pending #526"),
    ]


@dataclass
class Proposer:
    """Git/gh effects for one switch. Callers persist every return value immediately."""

    gh: GitHub
    runner: Runner
    runtime_repo: Path
    nexus_repo: Path
    work_dir: Path
    certify_cmd: str = "nexus-certify"

    def git(self, repo: Path, *args: str) -> CmdResult:
        res = self.runner(["git", "-C", str(repo), *args], timeout=600.0)
        if res.rc != 0:
            raise RuntimeError(f"git_failed:{args[0]}:{res.rc}:{res.stderr.strip()[-200:]}")
        return res

    def trusted_config_universe(self) -> bool:
        """True when the Nexus-new issue gate derives the evidence universe from trusted config.

        Same logic as ``scripts/ops/pr_preflight.py::_trusted_config_universe``, read at the exact
        ``origin/main`` SHA. In that mode Issues carry no NEXUS_CORE_EVIDENCE_UNIVERSE marker.
        """
        try:
            text = self.show(
                self.nexus_repo, self.remote_main(self.nexus_repo), _ISSUE_GATE_WORKFLOW
            )
        except RuntimeError:
            return False
        return _TRUSTED_UNIVERSE_RE.search(text) is not None

    def markers(self, repo: Path, *extra: str) -> list[str]:
        trusted = self.trusted_config_universe()
        if trusted and not extra:
            return []  # the universe marker was the only output; nothing to ask certify for
        res = self.runner([*shlex.split(self.certify_cmd), "markers", "--repo", str(repo), *extra])
        found = re.findall(r"<!-- NEXUS_CORE_[A-Z_]+: [^\n]*? -->", res.stdout)
        has_universe = any("NEXUS_CORE_EVIDENCE_UNIVERSE" in m for m in found)
        if res.rc != 0 or not (trusted or has_universe):
            raise RuntimeError("certify_markers_unavailable")
        skip = (
            ("NEXUS_CORE_ISSUE:", "NEXUS_CORE_EVIDENCE_UNIVERSE:")
            if trusted
            else ("NEXUS_CORE_ISSUE:",)
        )
        return [m for m in found if not any(k in m for k in skip)]

    def create_issue(self, repo: str, title: str, body: str) -> int:
        res = self.runner(
            [self.gh.gh, "issue", "create", "-R", repo, "--title", title, "--body-file", "-"],
            input_text=body,
        )
        match = re.search(r"/issues/([0-9]+)", res.stdout)
        if res.rc != 0 or not match:
            raise RuntimeError(f"issue_create_failed:{repo}")
        return int(match.group(1))

    def remote_main(self, repo: Path) -> str:
        """Fetch and resolve ``origin/main`` to an exact SHA (never a symbolic or index read)."""
        self.git(repo, "fetch", "origin", "main")
        sha = self.git(repo, "rev-parse", "--verify", "origin/main^{commit}").stdout.strip()
        if not _SHA40_RE.match(sha):
            raise RuntimeError("origin_main_unresolved")
        return sha

    def show(self, repo: Path, sha: str, rel: str) -> str:
        if not _SHA40_RE.match(str(sha or "")):
            raise RuntimeError(f"not_a_commit_sha:{rel}")  # ':path' alone would read the index
        return self.git(repo, "show", f"{sha}:{rel}").stdout

    def worktree(self, repo: Path, name: str, branch: str) -> tuple[Path, str]:
        """Fresh worktree for ``branch`` at the exact current ``origin/main``; ``(path, base)``."""
        base = self.remote_main(repo)
        path = self.work_dir / name
        if path.exists():
            self.git(repo, "worktree", "remove", "--force", str(path))
        self.git(repo, "worktree", "add", "-B", branch, str(path), base)
        return path, base

    def commit_push(
        self,
        wt: Path,
        files: Mapping[str, bytes],
        message: str,
        branch: str,
        *,
        lease: str | None = None,
    ) -> str:
        """Commit exactly ``files`` and push; returns the tool-authored head SHA.

        ``lease`` is the head this tool pushed earlier: the branch is only replaced if it still
        points there (``--force-with-lease``), so a foreign commit is never overwritten.
        """
        for rel, data in files.items():
            target = wt / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.git(wt, "add", "--", *files)
        self.git(wt, "commit", "-m", message)
        head = self.git(wt, "rev-parse", "--verify", "HEAD^{commit}").stdout.strip()
        if not _SHA40_RE.match(head):
            raise RuntimeError("authored_head_unresolved")
        changed = self.git(
            wt, "diff-tree", "--no-commit-id", "--name-only", "-r", head
        ).stdout.split()
        if sorted(changed) != sorted(files):
            raise RuntimeError(f"unexpected_committed_files:{changed}")
        if lease:
            if not _SHA40_RE.match(lease):
                raise RuntimeError("bad_lease")
            self.git(
                wt,
                "push",
                f"--force-with-lease=refs/heads/{branch}:{lease}",
                "origin",
                f"{head}:refs/heads/{branch}",
            )
        else:
            self.git(wt, "push", "origin", f"{head}:refs/heads/{branch}")
        return head

    def open_pr(self, repo: str, branch: str, title: str, body: str) -> int:
        res = self.runner(
            [
                self.gh.gh,
                "pr",
                "create",
                "-R",
                repo,
                "--base",
                "main",
                "--head",
                branch,
                "--title",
                title,
                "--body-file",
                "-",
            ],
            input_text=body,
        )
        match = re.search(r"/pull/([0-9]+)", res.stdout)
        if res.rc != 0 or not match:
            raise RuntimeError(f"pr_create_failed:{repo}")
        return int(match.group(1))


# ---------------------------------------------------------------------------
# 9. Run
# ---------------------------------------------------------------------------


@dataclass
class Config:
    runtime_repo: Path
    nexus_repo: Path = REPO_ROOT
    yaml_path: Path | None = None
    catalog_file: Path | None = None
    state_dir: Path = DEFAULT_STATE_DIR
    dry_run: bool = False
    runtime_issue: int | None = None
    pre_merge_hook: str | None = None
    agy_bin: str = "agy"
    certify_cmd: str = "nexus-certify"
    checks_timeout: float = 3600.0
    poll_interval: float = 60.0
    today: str = ""
    clear_pending: bool = False
    attestation_ttl_hours: float = 24.0


@dataclass
class Deps:
    runner: Runner = subprocess_runner
    attest_call: AttestFn = live_attest_call
    reviewer: Callable[[str], tuple[str, tuple[str, ...]]] | None = None
    validator: ValidatorFn | None = None
    sleep: Callable[[float], None] = time.sleep
    now: Callable[[], _dt.datetime] = lambda: _dt.datetime.now(_dt.timezone.utc)


@dataclass
class RunResult:
    outcome: str
    reason: str = ""
    receipt_path: str = ""
    plan: list[PlanStep] = field(default_factory=list)
    decision: Decision | None = None


class LockBusy(RuntimeError):
    pass


@contextlib.contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    try:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise LockBusy(str(path)) from exc
        yield
    finally:
        handle.close()


def idempotency_key(catalog: Catalog, yaml_bytes: bytes) -> str:
    return _sha256(f"{catalog.raw_sha256}:{_sha256(yaml_bytes)}")


def _load_state(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"keys": {}}
    return data if isinstance(data, dict) and isinstance(data.get("keys"), dict) else {"keys": {}}


def _save_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _wait_green(gh: GitHub, cfg: Config, deps: Deps, repo: str, pr: int, head: str) -> str:
    waited = 0.0
    while True:
        state = checks_state(gh, repo, pr, head)
        if state != "PENDING" or waited >= cfg.checks_timeout:
            return state
        deps.sleep(cfg.poll_interval)
        waited += cfg.poll_interval


Builder = Callable[[Path, str], "dict[str, bytes] | str"]


def _rec(ctx: dict[str, Any], kind: str) -> dict[str, Any]:
    return ctx.setdefault("kinds", {}).setdefault(kind, {})


def _sync_views(ctx: dict[str, Any]) -> None:
    kinds = ctx.get("kinds") or {}
    ctx["prs"] = {k: r["pr"] for k, r in kinds.items() if r.get("pr")}
    ctx["merges"] = {k: r["merge"] for k, r in kinds.items() if r.get("merge")}


def _ensure_issue(
    ctx: dict[str, Any],
    save: Callable[[], None],
    prop: Proposer,
    *,
    slot: str,
    repo: str,
    tag: str,
    title: str,
    body: Callable[[], str],
) -> int:
    """One Issue per switch and slot: persisted at once, found again by its title tag."""
    if ctx.get(slot):
        return int(ctx[slot])
    found = prop.gh.find_issue_by_title_tag(repo, tag)
    number = found if found else prop.create_issue(repo, f"{title} [{tag}]", body())
    ctx[slot] = number
    save()
    return number


def _ensure_pr(
    ctx: dict[str, Any],
    save: Callable[[], None],
    prop: Proposer,
    *,
    kind: str,
    repo: str,
    local_repo: Path,
    branch: str,
    build: Builder,
    message: str,
    title: str,
    body: Callable[[], str],
) -> str:
    """Make sure the tool-authored PR for ``kind`` exists on the current main ("" = ready).

    Every effect is persisted immediately: the authored head and base after the push, the PR
    number after creation, the merge SHA when a resumed PR turns out merged. A PR or branch head
    the tool did not author blocks; a moved base is rebuilt from scratch on the new main and must
    reproduce exactly the bytes rendered before.
    """
    rec = _rec(ctx, kind)
    gh = prop.gh
    if rec.get("merge"):
        return ""
    if not rec.get("pr"):
        found = gh.prs_for_branch(repo, branch)
        if found:
            if len(found) != 1 or not rec.get("head") or found[0].get("headRefOid") != rec["head"]:
                return "UNKNOWN_PR_ON_BRANCH"
            rec["pr"] = int(found[0]["number"])
            save()
    if rec.get("pr"):
        view = gh.pr_view(repo, int(rec["pr"]))
        if view.get("headRefOid") != rec.get("head"):
            return "FOREIGN_HEAD"
        if view.get("state") == "MERGED":
            sha = str((view.get("mergeCommit") or {}).get("oid") or "")
            if not _SHA40_RE.match(sha):
                return "MERGE_UNCONFIRMED"
            rec["merge"] = sha
            _sync_views(ctx)
            save()
            return ""
        if view.get("state") != "OPEN":
            return "PR_NOT_OPEN"
        if rec.get("base") == prop.remote_main(local_repo):
            return ""
    wt, base = prop.worktree(local_repo, kind, branch)
    files = build(wt, base)
    if isinstance(files, str):
        return files
    digests = {path: _sha256(data) for path, data in files.items()}
    if sorted(digests) != sorted(SCOPE_FILES[kind]):
        return "BUILD_FILE_SCOPE_MISMATCH"
    if rec.get("file_sha") and rec["file_sha"] != digests:
        return "SCOPED_CONTENT_CHANGED_ON_NEW_BASE"
    head = prop.commit_push(wt, files, message, branch, lease=rec.get("head"))
    rec.update(file_sha=digests, head=head, base=base)
    save()
    if not rec.get("pr"):
        rec["pr"] = prop.open_pr(repo, branch, title, body())
        _sync_views(ctx)
        save()
    return ""


def _merge_kind(
    ctx: dict[str, Any],
    save: Callable[[], None],
    cfg: Config,
    deps: Deps,
    prop: Proposer,
    reviewer: Any,
    *,
    kind: str,
    repo: str,
    decision: Decision,
    ensure: Callable[[], str],
) -> str:
    """Ensure, wait, review, guard and merge one PR ("" = merged). One rebuild on a moved base."""
    gh = prop.gh
    rec = _rec(ctx, kind)
    for attempt in range(2):
        problem = ensure()
        if problem:
            return problem
        if rec.get("merge"):
            return ""
        pr, head = int(rec["pr"]), str(rec["head"])
        state = _wait_green(gh, cfg, deps, repo, pr, head)
        if state != "GREEN":
            return f"CHECKS_{state}"
        guard = lambda: verify_pr_scope(gh, repo=repo, kind=kind, rec=rec)  # noqa: E731
        problem = guard()
        if problem == "BASE_MOVED" and attempt == 0:
            continue
        if problem:
            return f"GUARD_{problem}"
        reviews = ctx.setdefault("reviews", {})
        key = f"{repo}#{pr}@{head}"
        prior = reviews.get(key)
        if prior and prior.get("verdict") == REJECT:
            return "REVIEW_NOT_ACCEPT"  # the same head is never re-reviewed
        result = review(gh, reviewer, repo=repo, pr=pr, head=head, kind=kind, decision=decision)
        reviews[key] = {"verdict": result.verdict, "reasons": list(result.reasons)}
        save()
        merged = merge(
            gh,
            repo=repo,
            pr=pr,
            head=head,
            review_result=result,
            pre_merge_hook=cfg.pre_merge_hook,
            guard=guard,
        )
        if merged.reason == "GUARD_BASE_MOVED" and attempt == 0:
            continue
        if not merged.ok:
            return merged.reason
        rec["merge"] = merged.merge_sha
        _sync_views(ctx)
        save()
        return ""
    return "BASE_KEEPS_MOVING"


def _propose_and_merge(
    ctx: dict[str, Any],
    cfg: Config,
    deps: Deps,
    decision: Decision,
    attestation: Attestation,
    rendered: str,
    base_yaml: bytes,
    key: str,
    save: Callable[[], None] = lambda: None,
) -> tuple[str, str]:
    gh = GitHub(runner=deps.runner)
    reviewer = deps.reviewer or Reviewer(runner=deps.runner)
    prop = Proposer(
        gh,
        deps.runner,
        cfg.runtime_repo,
        cfg.nexus_repo,
        cfg.state_dir / "work" / key[:12],
        cfg.certify_cmd,
    )
    tag = f"wf-auto-{key[:12]}"

    # --- nexus-runtime: the Workforce yaml only
    rt = _rec(ctx, "runtime")
    if not rt.get("merge"):
        issue = cfg.runtime_issue or _ensure_issue(
            ctx,
            save,
            prop,
            slot="runtime_issue",
            repo=RUNTIME_REPO,
            tag=tag,
            title=f"Workforce auto-update: {decision.old_model} -> {decision.new_model}",
            body=lambda: (
                f"Automatic Workforce model update under Nexus-new#{ISSUE_NUMBER}.\n\n"
                f"{summary_lines(decision)}{SCOPE_NOTE}\n"
                + "\n".join(prop.markers(cfg.runtime_repo))
                + "\n"
            ),
        )

        def build_runtime(wt: Path, _base: str) -> dict[str, bytes] | str:
            if (wt / RUNTIME_YAML_PATH).read_bytes() != base_yaml:
                return "RUNTIME_BASE_DRIFT"
            err = (deps.validator or (lambda t: validate_with_runtime(t, runtime_src=wt / "src")))(
                rendered
            )
            return (
                f"VALIDATOR_REJECTED_ON_BASE:{err}"
                if err
                else {RUNTIME_YAML_PATH: rendered.encode("utf-8")}
            )

        problem = _merge_kind(
            ctx,
            save,
            cfg,
            deps,
            prop,
            reviewer,
            kind="runtime",
            repo=RUNTIME_REPO,
            decision=decision,
            ensure=lambda: _ensure_pr(
                ctx,
                save,
                prop,
                kind="runtime",
                repo=RUNTIME_REPO,
                local_repo=cfg.runtime_repo,
                branch=branch_name(decision, key, "model"),
                build=build_runtime,
                message=(
                    f"feat(workforce): {decision.old_worker} -> {decision.new_worker} "
                    f"({decision.new_model}) (Nexus-new#{ISSUE_NUMBER})"
                ),
                title=f"Workforce auto-update: default {decision.new_model} (#{issue})",
                body=lambda: runtime_pr_body(decision, attestation, int(issue)),
            ),
        )
        if problem:
            return BLOCKED, f"RUNTIME_{problem}"

    new_sha = str(rt["merge"])
    prop.remote_main(cfg.runtime_repo)
    if prop.show(cfg.runtime_repo, new_sha, RUNTIME_YAML_PATH) != rendered:
        return BLOCKED, "MERGED_RUNTIME_YAML_DIFFERS_FROM_RENDER"

    # --- Nexus-new: pin + mirror PR first (its number feeds the anchor), anchor merges first
    pin_issue = _ensure_issue(
        ctx,
        save,
        prop,
        slot="pin_issue",
        repo=NEXUS_REPO,
        tag=tag,
        title=f"Workforce auto-update pin: nexus-runtime {new_sha[:7]} ({decision.new_model})",
        body=lambda: (
            f"Pin bump for the automatic Workforce update under #{ISSUE_NUMBER}.\n\n"
            f"{summary_lines(decision)}{SCOPE_NOTE}\n"
            + "\n".join(
                prop.markers(
                    cfg.nexus_repo,
                    "--material-transition",
                    f"canonical-runtime=git-commit:{new_sha}",
                )
            )
            + "\n"
        ),
    )

    def build_pin(wt: Path, _base: str) -> dict[str, bytes] | str:
        match = re.search(
            r"nexus-runtime\.git@([0-9a-f]{40})", (wt / "pyproject.toml").read_text(), re.ASCII
        )
        if not match:
            return "NEXUS_PIN_NOT_FOUND"
        if ctx.setdefault("old_runtime_sha", match.group(1)) != match.group(1):
            return "NEXUS_PIN_MOVED"
        files = render_pin_files(
            wt, old_sha=match.group(1), new_sha=new_sha, mirror_yaml=rendered.encode("utf-8")
        )
        return files.files if files.ok else f"PIN_RENDER:{files.reason}"

    def ensure_pin() -> str:
        return _ensure_pr(
            ctx,
            save,
            prop,
            kind="pin",
            repo=NEXUS_REPO,
            local_repo=cfg.nexus_repo,
            branch=branch_name(decision, key, "pin"),
            build=build_pin,
            message=f"chore(deps): pin nexus-runtime {new_sha[:7]} (#{pin_issue})",
            title=f"Workforce auto-update: pin nexus-runtime {new_sha[:7]} (#{pin_issue})",
            body=lambda: nexus_pr_body("pin", decision, pin_issue, new_sha),
        )

    pin = _rec(ctx, "pin")
    if not pin.get("pr"):
        problem = ensure_pin()
        if problem:
            return BLOCKED, f"PIN_{problem}"

    def build_anchor(wt: Path, base: str) -> dict[str, bytes] | str:
        pin_head = str(pin.get("head") or "")
        if not _SHA40_RE.match(pin_head):
            return "PIN_HEAD_NOT_SHA40"
        texts = [
            prop.show(cfg.nexus_repo, base, "pyproject.toml"),
            prop.show(cfg.nexus_repo, base, "uv.lock"),
            prop.show(cfg.nexus_repo, pin_head, "pyproject.toml"),
            prop.show(cfg.nexus_repo, pin_head, "uv.lock"),
        ]
        transition = (
            _sha256(texts[0]),
            _sha256(texts[1]),
            _sha256(texts[2]),
            _sha256(texts[3]),
        )
        anchor = render_anchor_files(
            wt,
            old_sha=str(ctx["old_runtime_sha"]),
            new_sha=new_sha,
            pin_pr=int(pin["pr"]),
            pin_issue=pin_issue,
            transition=transition,
        )
        return anchor.files if anchor.ok else f"ANCHOR_RENDER:{anchor.reason}"

    problem = _merge_kind(
        ctx,
        save,
        cfg,
        deps,
        prop,
        reviewer,
        kind="anchor",
        repo=NEXUS_REPO,
        decision=decision,
        ensure=lambda: _ensure_pr(
            ctx,
            save,
            prop,
            kind="anchor",
            repo=NEXUS_REPO,
            local_repo=cfg.nexus_repo,
            branch=branch_name(decision, key, "anchor"),
            build=build_anchor,
            message=f"ci: trusted runtime identity {new_sha[:7]} for #{pin['pr']}",
            title=f"ci: trusted runtime identity {new_sha[:7]} and transition for #{pin['pr']}",
            body=lambda: nexus_pr_body("anchor", decision, pin_issue, new_sha),
        ),
    )
    if problem:
        return BLOCKED, f"ANCHOR_{problem}"
    # The anchor merge moved main: the pin PR is rebuilt on it by this tool (never by GitHub's
    # update-branch, whose merge commit the tool would not have authored) and re-reviewed.
    problem = _merge_kind(
        ctx,
        save,
        cfg,
        deps,
        prop,
        reviewer,
        kind="pin",
        repo=NEXUS_REPO,
        decision=decision,
        ensure=ensure_pin,
    )
    if problem:
        return BLOCKED, f"PIN_{problem}"
    return "MERGED", ""


def run(cfg: Config, deps: Deps | None = None) -> RunResult:
    deps = deps or Deps()
    today = cfg.today or _dt.date.today().isoformat()
    run_id = (
        _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    )
    receipt_path = cfg.state_dir / "runs" / f"{run_id}.json"
    receipt: dict[str, Any] = {
        "schema": "nexus.workforce_model_autoupdate.receipt.v1",
        "issue": ISSUE_NUMBER,
        "run_id": run_id,
        "dry_run": cfg.dry_run,
        "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "receipt_path": str(receipt_path),
    }

    def finish(outcome: str, reason: str = "", **extra: Any) -> RunResult:
        receipt.update(
            outcome=outcome,
            reason=reason,
            finished_at=_dt.datetime.now(_dt.timezone.utc).isoformat(),
        )
        _save_json(receipt_path, receipt)
        return RunResult(outcome, reason, str(receipt_path), **extra)

    try:
        with file_lock(cfg.state_dir / "autoupdate.lock"):
            return _run_locked(cfg, deps, today, receipt, finish)
    except LockBusy:
        return finish("LOCKED", "another run holds the lock")


def _run_locked(
    cfg: Config,
    deps: Deps,
    today: str,
    receipt: dict[str, Any],
    finish: Callable[..., RunResult],
) -> RunResult:
    state_path = cfg.state_dir / "state.json"
    state = _load_state(state_path)
    if cfg.clear_pending and not cfg.dry_run and state.pop("pending", None):
        receipt["cleared_pending"] = True
        _save_json(state_path, state)
    pending = state.get("pending")
    if pending and not cfg.dry_run:
        # A switch already in flight (e.g. runtime merged, Nexus-new pin pending) resumes first:
        # its runtime merge changed the yaml, so a fresh decision would wrongly see NOOP.
        pctx = state["keys"].get(pending) or {}
        if pctx.get("decision") and pctx.get("attestation") and pctx.get("rendered"):
            decision = _decision_from(pctx["decision"])
            receipt.update(resumed=True, idempotency_key=pending, decision=pctx["decision"])
            attestation = Attestation(**pctx["attestation"])
            if not _rec(pctx, "runtime").get("merge"):
                # Nothing merged yet: the model must still be served and the attestation fresh.
                catalog = discover(
                    agy_bin=cfg.agy_bin, catalog_file=cfg.catalog_file, runner=deps.runner
                )
                receipt["catalog"] = asdict(catalog)
                reason = ""
                if not catalog.ok or decision.new_model not in catalog.served_ids:
                    reason = "RESUME_NEW_MODEL_NOT_SERVED"
                elif not _attestation_fresh(attestation, cfg, deps):
                    attestation = _attest_now(decision, deps)
                    pctx["attestation"] = asdict(attestation)
                    _save_json(state_path, state)
                    if not attestation.ok:
                        reason = f"RESUME_ATTESTATION:{attestation.reason}"
                if reason:
                    receipt["attestation"] = asdict(attestation)
                    _notify_once(pctx, deps, decision, BLOCKED, reason, receipt)
                    _save_json(state_path, state)
                    return finish(BLOCKED, reason, decision=decision)
            receipt["attestation"] = asdict(attestation)
            return _execute_switch(
                cfg, deps, state, state_path, pending, decision, attestation, receipt, finish
            )
        state.pop("pending", None)

    catalog = discover(agy_bin=cfg.agy_bin, catalog_file=cfg.catalog_file, runner=deps.runner)
    receipt["catalog"] = asdict(catalog)
    yaml_path = cfg.yaml_path or (cfg.runtime_repo / RUNTIME_YAML_PATH)
    try:
        if cfg.yaml_path is None and not cfg.dry_run:
            # Live runs decide on nexus-runtime main, never on a local working tree.
            fetched = deps.runner(["git", "-C", str(cfg.runtime_repo), "fetch", "origin", "main"])
            shown = deps.runner([
                "git",
                "-C",
                str(cfg.runtime_repo),
                "show",
                f"origin/main:{RUNTIME_YAML_PATH}",
            ])
            if fetched.rc != 0 or shown.rc != 0:
                return finish(BLOCKED, "RUNTIME_MAIN_YAML_UNAVAILABLE")
            yaml_bytes = shown.stdout.encode("utf-8")
            yaml_path = Path(f"origin/main:{RUNTIME_YAML_PATH}")
        else:
            yaml_bytes = yaml_path.read_bytes()
        policy = yaml.safe_load(yaml_bytes)
    except (OSError, yaml.YAMLError) as exc:
        return finish(BLOCKED, f"YAML_UNREADABLE:{type(exc).__name__}")
    key = idempotency_key(catalog, yaml_bytes)
    receipt.update(idempotency_key=key, yaml_sha256=_sha256(yaml_bytes), yaml_path=str(yaml_path))
    ctx = state["keys"].setdefault(key, {})
    if ctx.get("outcome") in (NOOP, "MERGED") and not cfg.dry_run:
        return finish("SKIPPED_IDEMPOTENT", f"key already {ctx['outcome']}")

    decision = decide(policy if isinstance(policy, dict) else {}, catalog)
    receipt["decision"] = asdict(decision)

    def blocked(reason: str) -> RunResult:
        if not cfg.dry_run:
            _notify_once(ctx, deps, decision, BLOCKED, reason, receipt)
            _save_json(state_path, state)
        return finish(BLOCKED, reason, decision=decision)

    if decision.kind == BLOCKED:
        return blocked(decision.reason)
    if decision.kind != SWITCH:
        if not cfg.dry_run:
            ctx["outcome"] = decision.kind
            _save_json(state_path, state)
        return finish(decision.kind, decision.reason, decision=decision)

    attestation: Attestation | None = None
    if not cfg.dry_run:
        cached = ctx.get("attestation")
        if (
            isinstance(cached, dict)
            and cached.get("ok")
            and _attestation_fresh(Attestation(**cached), cfg, deps)
        ):
            attestation = Attestation(**cached)
        else:
            attestation = _attest_now(decision, deps)
            ctx["attestation"] = asdict(attestation)
            _save_json(state_path, state)
        receipt["attestation"] = asdict(attestation)
        if not attestation.ok:
            ctx.pop("attestation", None)  # a failed attestation is retried on the next run
            return blocked(f"ATTESTATION:{attestation.reason}")
    att_sha = _sha256(json.dumps(attestation.receipt, sort_keys=True)) if attestation else "dry-run"
    rendered = render_change(
        yaml_bytes.decode("utf-8"),
        decision,
        today=today,
        agy_version=catalog.agy_version,
        attestation_sha=att_sha,
        validator=deps.validator
        or (lambda t: validate_with_runtime(t, runtime_src=cfg.runtime_repo / "src")),
    )
    receipt["render"] = {
        "ok": rendered.ok,
        "reason": rendered.reason,
        "validator": rendered.validator,
        "rendered_sha256": _sha256(rendered.text) if rendered.text else "",
    }
    if not rendered.ok:
        return blocked(f"RENDER:{rendered.reason}:{rendered.validator}")
    plan = build_plan(decision, key, runtime_issue=cfg.runtime_issue)
    receipt["plan"] = [asdict(step) for step in plan]
    if cfg.dry_run:
        receipt["rendered_diff"] = _unified_diff(yaml_bytes.decode("utf-8"), rendered.text)
        return finish("DRY_RUN", "", plan=plan, decision=decision)
    assert attestation is not None
    ctx.update(
        decision=asdict(decision), rendered=rendered.text, base_yaml=yaml_bytes.decode("utf-8")
    )
    state["pending"] = key
    _save_json(state_path, state)
    return _execute_switch(
        cfg, deps, state, state_path, key, decision, attestation, receipt, finish
    )


def _attest_now(decision: Decision, deps: Deps) -> Attestation:
    result = attest(decision.new_model, decision.new_label, call=deps.attest_call)
    return replace(result, attested_at=deps.now().isoformat())


def _attestation_fresh(attestation: Attestation, cfg: Config, deps: Deps) -> bool:
    try:
        stamp = _dt.datetime.fromisoformat(attestation.attested_at)
    except ValueError:
        return False
    if stamp.tzinfo is None:
        return False
    age = deps.now() - stamp
    return attestation.ok and _dt.timedelta(0) <= age <= _dt.timedelta(
        hours=cfg.attestation_ttl_hours
    )


def _decision_from(data: Mapping[str, Any]) -> Decision:
    fields: dict[str, Any] = {
        key: tuple(value) if isinstance(value, list) else value for key, value in data.items()
    }
    return Decision(**fields)


def _execute_switch(
    cfg: Config,
    deps: Deps,
    state: dict[str, Any],
    state_path: Path,
    key: str,
    decision: Decision,
    attestation: Attestation,
    receipt: dict[str, Any],
    finish: Callable[..., RunResult],
) -> RunResult:
    ctx = state["keys"][key]
    try:
        outcome, reason = _propose_and_merge(
            ctx,
            cfg,
            deps,
            decision,
            attestation,
            str(ctx["rendered"]),
            str(ctx["base_yaml"]).encode("utf-8"),
            key,
            save=lambda: _save_json(state_path, state),
        )
    except (RuntimeError, OSError, ValueError) as exc:
        outcome, reason = BLOCKED, sanitize_reason(f"PROPOSE_ERROR:{exc}")
    _sync_views(ctx)
    receipt.update(
        prs=ctx.get("prs", {}), merges=ctx.get("merges", {}), reviews=ctx.get("reviews", {})
    )
    if outcome == "MERGED":
        ctx["outcome"] = outcome
        state.pop("pending", None)
    _notify_once(ctx, deps, decision, outcome, reason, receipt)
    _save_json(state_path, state)
    return finish(outcome, reason, decision=decision)


def _notify_once(
    ctx: dict[str, Any],
    deps: Deps,
    decision: Decision,
    outcome: str,
    reason: str,
    receipt: Mapping[str, Any],
) -> None:
    """Comment on #1996 once per (idempotency key, outcome, reason)."""
    notified = ctx.setdefault("notified", [])
    tag = f"{outcome}:{reason}"
    if tag in notified:
        return
    if notify(
        GitHub(runner=deps.runner),
        decision=decision,
        outcome=outcome,
        receipt={**receipt, "reason": reason},
    ):
        notified.append(tag)


def _unified_diff(old: str, new: str) -> str:
    import difflib

    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"a/{RUNTIME_YAML_PATH}",
            tofile=f"b/{RUNTIME_YAML_PATH}",
        )
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument(
        "--runtime-repo",
        type=Path,
        required=True,
        help="local nexus-runtime clone (origin = James3014/nexus-runtime)",
    )
    parser.add_argument("--nexus-repo", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--yaml",
        type=Path,
        default=None,
        help="Workforce yaml to decide on (default: runtime repo copy)",
    )
    parser.add_argument(
        "--catalog-file",
        type=Path,
        default=None,
        help="captured `agy models` stdout instead of running agy",
    )
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE_DIR)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--runtime-issue", type=int, default=None)
    parser.add_argument(
        "--pre-merge-hook",
        default=None,
        help="command run as `<hook> <repo> <pr> <head>`; last stdout line GO",
    )
    parser.add_argument("--agy-bin", default="agy")
    parser.add_argument("--certify-cmd", default="nexus-certify")
    parser.add_argument("--reviewer-model", default=DEFAULT_REVIEWER_MODEL)
    parser.add_argument("--claude-bin", default=str(Path.home() / ".local/bin/claude"))
    parser.add_argument("--checks-timeout", type=float, default=3600.0)
    parser.add_argument(
        "--clear-pending",
        action="store_true",
        help="drop the in-flight switch pointer (Owner decision after a permanent block)",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    cfg = Config(
        runtime_repo=args.runtime_repo,
        nexus_repo=args.nexus_repo,
        yaml_path=args.yaml,
        catalog_file=args.catalog_file,
        state_dir=args.state_dir,
        dry_run=args.dry_run,
        runtime_issue=args.runtime_issue,
        pre_merge_hook=args.pre_merge_hook,
        agy_bin=args.agy_bin,
        certify_cmd=args.certify_cmd,
        checks_timeout=args.checks_timeout,
        clear_pending=args.clear_pending,
    )
    deps = Deps(reviewer=Reviewer(claude_bin=args.claude_bin, model=args.reviewer_model))
    result = run(cfg, deps)
    if args.json:
        print(json.dumps(json.loads(Path(result.receipt_path).read_text()), indent=2))
    else:
        print(f"outcome: {result.outcome}" + (f" ({result.reason})" if result.reason else ""))
        if result.decision is not None:
            d = result.decision
            if d.old_worker:
                print(
                    f"decision: {d.kind} {d.old_worker} ({d.old_model}) -> "
                    f"{d.new_worker or '-'} ({d.new_model or '-'}) roles={list(d.roles)} "
                    f"retired={d.predecessor_retired} register={d.register_new_worker}"
                )
            else:
                print(f"decision: {d.kind}" + (f" ({d.reason})" if d.reason else ""))
            for note in d.notes:
                print(f"note: {note}")
        for i, step in enumerate(result.plan, 1):
            print(f"plan {i:2d}. [{step.repo}] {step.action}: {step.detail}")
        print(f"receipt: {result.receipt_path}")
    return {"BLOCKED": 2, "LOCKED": 3}.get(result.outcome, 0)


if __name__ == "__main__":
    raise SystemExit(main())
