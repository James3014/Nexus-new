#!/usr/bin/env python3
"""#2721 arm scoring and aggregation (scoring pre-registration S0-S6, amendments 1-8).

Three commands, in this order:

``run``      (scorer side, blind; inside ``lab run`` on the Mac mini)
    Reads the blinded ``candidates.jsonl`` written by ``blind.py`` (opaque id, task id,
    repeat, diff sha256, scoring flags; never an arm), seals every candidate into its
    own store in the ``prep_s1_2721`` seal format, and scores each one with the frozen
    S1 driver (``driver_s1_2721.py``) and ``--sandbox os --store --min-free-disk-gib 40``,
    with a fresh ``--work`` per scoring, outside every repository. Before each batch and
    each scoring it re-checks the driver sha256 (pinned + S1 manifest) and the scorer
    blobs; every receipt must carry scorer 1.3.1, ``runner_sandbox: os`` and profile
    ``d150953e...``. Infra (exit 8, no receipt, or an infra label) re-scores that
    task/repeat in all arms, at most twice, then drops it from all arms (S4). Each
    scoring runs in its own session; afterwards any surviving descendant, or any
    process whose cwd is under that ``--work``, is killed and recorded (S2.1(c)).

``finalize`` (scorer side, blind; ``run`` calls it at the end)
    Writes the per-row records, the S4 drop counts, the S4.2 ``host_disk_low`` listing
    per opaque id, the post-candidate oracle-anomaly listing, ``MANIFEST.sha256`` and
    its sha256, then makes the archive read-only. Create-only throughout: nothing that
    exists is ever overwritten.

``analyze``  (custodian side, after unblinding)
    Verifies the archive manifest, binds the arm map to the archived candidate set, and
    computes S5: per-task solve rate (mean over repeats), paired bootstrap (10,000
    resamples, ``numpy.random.default_rng(20261020)``, percentile 95% CI), exact McNemar
    on per-task majority-of-3, BROKE_EXISTING rate per arm, the decision band, per
    stratum, and the NOOP void check.

Label rules (S0 + amendment 8.3, applied before unblinding, identically in all arms):

* ``RESOLVED`` -> solved; ``PARTIAL``/``UNRESOLVED``/``BROKE_EXISTING``/``NO_CANDIDATE``
  -> not solved (BROKE_EXISTING also counted separately).
* ``NOT_RUNNABLE`` whose sub-reason is the candidate's own (patch does not apply, scope,
  a scratch or host-disk cap charged to the candidate) -> not solved, kept (S4: never
  drop a row because the model's patch was bad; S4.1). Any other ``NOT_RUNNABLE`` -> infra.
* ``NOT_SCORABLE_*`` / ``PENDING_GROUND_TRUTH``: a scratch-cap trip or ORACLE_RUN_FAILED
  once the candidate tree was built -> that candidate's failure (S4.1); anything else ->
  infra (listed when it happened after the candidate tree was built).
* ``HARNESS_TAMPER``, ``OUT_OF_SCOPE_STRIPPED``, ``PATCH_DOES_NOT_APPLY`` or
  ``RUN_INVALID_NOT_SOLVED`` (a non-infra invalid run: TAMPERED, a non-infra Gateway error,
  STATE_LEAK, a void reason) in ``scoring_flags`` -> not solved, kept in the denominator;
  the remainder is still scored, for diagnostics only. Only true infra leaves the
  candidate set (blind.py), and that task/repeat is then dropped from all arms.

Scheduling: ``--concurrency`` defaults to 1; above 1, workers take whole tasks, so rows
of the same task (any arm, any repeat) are never scored at the same time.

This file is stdlib-only except ``analyze`` (numpy), so ``run`` works under the same
``python3.12 -I`` interpreter as S1.

Usage on the Mac mini (paths default to the S1 archive, export, bank venvs and synth repos)::

    PY=~/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12
    lab run --profile m5 --name score2721-<phase> --kind cpu --mem-gb 12 --wall 43200 \\
        --holder layer1-rie -- $PY -I <worktree>/scripts/bench/measure_2721/score_arms.py run \\
        --blind-dir <blind.py --out> --archive ~/workspace/.scratch/score2721/<phase>-<UTC> \\
        --arms-per-group 3 --concurrency 1
    # post MANIFEST.sha256.sha256 from the archive, then the custodian runs:
    <python with numpy> score_arms.py analyze --archive <archive> --arm-map <arm_map.json> \\
        --treatment NEXUS --control BARE --noop NOOP --primary-set M --expect-manifest-sha256 <posted sha> \\
        --out <report>
"""

from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import math
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

SCHEMA = "nexus.measure_2721.arm_scoring.v1"

# -- pinned identities (issue #2721: amendment 6 item 1, amendment 7, S1 result) --------
DRIVER_SHA256 = "2116984be6c4a77bbc8a9f0e49369776bdf9c943f1baba209cc35c9faec48ae3"
DRIVER_MANIFEST_PATH = "./harness/driver_s1_2721.py"
S1_MANIFEST_SHA256 = "72f949d267d0286661415bc7aa31477584bf8c2246755736351d0a21c11e9d62"
SCORER_BLOB = "0b5936bfebc8f39b393e075cf1a956c7ac1775be"
CLI_BLOB = "929b56e292482bb8744136381b9219444704d12e"
SCORER_FILES = {"nexus/research/real_outcome_scorer.py": SCORER_BLOB,
                "nexus/research/score_real_outcome_cli.py": CLI_BLOB}
SCORER_VERSION = "1.3.1"
PROFILE_SHA256 = "d150953e2433454487c3050c1c8683b441d074828c14dcc3f5c19efe1faa2ec0"
SANDBOX = "os"
MIN_FREE_DISK_GIB = "40"
MAX_RERUNS = 2  # S4: re-run at most twice, then drop from all arms
BOOTSTRAP_SEED = 20261020  # amendment 8.1
BOOTSTRAP_RESAMPLES = 10_000
BROKE_MARGIN = 0.05  # S5 WORKS band: BROKE_EXISTING may rise by at most 5 pp
INFRA_EXIT = 8
FATAL_EXITS = {2: "usage", 3: "REFUSED_SEAL", 7: "NO_OS_SANDBOX"}

HOME = Path.home()
S1_ARCHIVE = HOME / "workspace/.scratch/s1-2721/20261020T024321Z"
S1_WORK = HOME / "workspace/.scratch/s1-2721-work"
DEFAULTS = {
    "s1_archive": S1_ARCHIVE,
    "driver": S1_ARCHIVE / "harness/driver_s1_2721.py",
    "export": S1_WORK / "nexus-main-6b400dcdb",
    "venvs": HOME / "workspace/.scratch/taskbank-2721/venvs",
    "synth_root": S1_WORK / "synth",
    "task_index": S1_ARCHIVE / "inputs/stores/index.json",
    "s1_result": S1_ARCHIVE / "S1_RESULT.json",
    "s1_receipts": S1_ARCHIVE / "receipts",
    "python": "/Users/james/.local/share/uv/python/cpython-3.12-macos-aarch64-none/bin/python3.12",
    "work_root": HOME / "workspace/.scratch/score2721-work",
}

# -- labels (real_outcome_scorer 1.3.1) ------------------------------------------------
RESOLVED, PARTIAL, UNRESOLVED = "RESOLVED", "PARTIAL", "UNRESOLVED"
BROKE_EXISTING, NO_CANDIDATE, NOT_RUNNABLE = "BROKE_EXISTING", "NO_CANDIDATE", "NOT_RUNNABLE"
PENDING_GROUND_TRUTH = "PENDING_GROUND_TRUTH"
CAND_ROLE = "CAND+T"
SCRATCH_SUBS = frozenset({"SCRATCH_TMP_CAP_EXCEEDED", "SCRATCH_TMP_TASK_CAP_EXCEEDED", "HOST_DISK_LOW"})
CANDIDATE_FAULT_SUBS = frozenset({"APPLY_FAILED", "SCOPE_INVALID", "SEALED_WHILE_PROVIDER_RUNNING"}) | SCRATCH_SUBS
ORACLE_RUN_FAILED = "ORACLE_RUN_FAILED"

SOLVED, NOT_SOLVED, INFRA = "SOLVED", "NOT_SOLVED", "INFRA"
FLAG_HARNESS_TAMPER = "HARNESS_TAMPER"
FLAG_OUT_OF_SCOPE = "OUT_OF_SCOPE_STRIPPED"
FLAG_PATCH_DOES_NOT_APPLY = "PATCH_DOES_NOT_APPLY"
FLAG_RUN_INVALID = "RUN_INVALID_NOT_SOLVED"  # blind.py: a non-infra invalid run (arm-neutral)
# amendment 8.3, plus a scored diff that does not apply and a non-infra invalid run
NOT_SOLVED_FLAGS = frozenset({FLAG_HARNESS_TAMPER, FLAG_OUT_OF_SCOPE, FLAG_PATCH_DOES_NOT_APPLY, FLAG_RUN_INVALID})
SCORING_FLAGS = NOT_SOLVED_FLAGS

# -- blind input schema ------------------------------------------------------------------
CANDIDATE_KEYS = frozenset({"opaque_id", "task_id", "repeat", "diff_sha256", "scoring_flags"})
_OPAQUE_RE = re.compile(r"[0-9a-f]{16}")
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_TASK_RE = re.compile(r"[A-Za-z0-9_.-]+-[0-9]+")
_ARMISH_KEY_RE = re.compile(r"arm|run_?id|treat|control|condition|variant|group|phase|nexus|bare|noop", re.I)
_ARM_WORDS = re.compile(r"\b(BARE|NEXUS|NOOP|NEXUS_NOOP|TREATMENT|CONTROL)\b", re.I)


class Refused(RuntimeError):
    """A precondition of the pre-registration is not met; nothing is scored or written."""


# -- small helpers ------------------------------------------------------------------------

def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def git_blob_sha(path: Path) -> str:
    data = Path(path).read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def canon(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, indent=1, ensure_ascii=False) + "\n").encode()


def write_new(path: Path, data: bytes) -> None:
    """Create-only write: refuses to overwrite (S6)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    with os.fdopen(fd, "wb") as fh:
        fh.write(data)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]


def task_key(task_id: str, repo: str) -> str:
    owner, name = repo.split("/", 1)
    return f"{owner}__{name}--{int(task_id.rsplit('-', 1)[1])}"


# -- identity checks ----------------------------------------------------------------------

def verify_identity(driver: Path, s1_archive: Path, export: Path, *,
                    driver_sha: str = DRIVER_SHA256, s1_manifest_sha: str = S1_MANIFEST_SHA256,
                    scorer_files: Mapping[str, str] = SCORER_FILES) -> dict[str, Any]:
    """Run before every batch and every scoring: the driver must be byte-identical to the
    one archived (with its hash) in the S1 manifest, and the scorer export must carry the
    pinned blobs. Any mismatch refuses."""
    manifest = Path(s1_archive) / "MANIFEST.sha256"
    got_manifest = sha256_file(manifest)
    if got_manifest != s1_manifest_sha:
        raise Refused(f"S1_MANIFEST_MISMATCH: {got_manifest} != {s1_manifest_sha}")
    listed = {line.split(None, 1)[1].strip(): line.split(None, 1)[0]
              for line in manifest.read_text().splitlines() if line.strip()}
    if listed.get(DRIVER_MANIFEST_PATH) != driver_sha:
        raise Refused(f"DRIVER_NOT_IN_S1_MANIFEST: {listed.get(DRIVER_MANIFEST_PATH)} != {driver_sha}")
    got_driver = sha256_file(driver)
    if got_driver != driver_sha:
        raise Refused(f"DRIVER_SHA_MISMATCH: {driver} is {got_driver}, pinned {driver_sha}")
    blobs = {}
    for rel, pinned in scorer_files.items():
        got = git_blob_sha(Path(export) / rel)
        if got != pinned:
            raise Refused(f"SCORER_BLOB_MISMATCH: {rel} is {got}, pinned {pinned}")
        blobs[rel] = got
    return {"driver_sha256": got_driver, "s1_manifest_sha256": got_manifest, "scorer_blobs": blobs}


def s1_reference(receipts_root: Path, key: str) -> dict[str, str]:
    """The task's venv identity (``env_key``) and spec hash from its S1 self-check
    receipts; every S1 receipt of the task that has them must agree."""
    seen = set()
    for path in sorted(Path(receipts_root).glob(f"*/tasks/{key}/real_outcome.json")):
        r = json.loads(path.read_text())
        if r.get("env_key") and r.get("spec_sha256"):
            seen.add((r["env_key"], r["spec_sha256"]))
    if len(seen) != 1:
        raise Refused(f"S1_REFERENCE_{'MISSING' if not seen else 'AMBIGUOUS'} {key}: {len(seen)} identities")
    env_key, spec = seen.pop()
    return {"env_key": env_key, "spec_sha256": spec}


def check_receipt_identity(receipt: Mapping[str, Any], key: str, ref: Mapping[str, str]) -> None:
    """Every scored row must carry exactly the pinned scorer, sandbox and profile, and
    the same venv identity and spec as the task's S1 receipts."""
    want = {"scorer_version": SCORER_VERSION, "runner_sandbox": SANDBOX,
            "runner_sandbox_profile_sha256": PROFILE_SHA256, "task_key": key,
            "env_key": ref["env_key"], "spec_sha256": ref["spec_sha256"]}
    bad = {k: receipt.get(k) for k, v in want.items() if receipt.get(k) != v}
    if bad:
        raise Refused(f"RECEIPT_IDENTITY_MISMATCH {key}: {bad}")


# -- blind input ----------------------------------------------------------------------------

def load_candidates(blind_dir: Path, survivors: Iterable[str]) -> list[dict[str, Any]]:
    """Strict schema: anything that is not an opaque id, a survivor task id, a repeat,
    a diff hash or a pre-registered scoring flag is refused, so no arm label (or an
    arm-revealing harness flag) can reach the scorer."""
    blind_dir = Path(blind_dir)
    survivors = set(survivors)
    for path in blind_dir.rglob("*"):
        rel = path.relative_to(blind_dir).as_posix()
        if rel in ("candidates.jsonl", "candidates") or re.fullmatch(r"candidates/[0-9a-f]{16}\.diff", rel):
            continue
        raise Refused(f"UNEXPECTED_FILE_IN_BLIND_INPUT: {rel} (arm map or run data must not be here)")
    rows = read_jsonl(blind_dir / "candidates.jsonl")
    if not rows:
        raise Refused("NO_CANDIDATES")
    seen: set[str] = set()
    out = []
    for i, row in enumerate(rows):
        extra = set(row) - CANDIDATE_KEYS
        armish = sorted(k for k in row if _ARMISH_KEY_RE.search(k))
        if armish or extra:
            raise Refused(f"ARM_LABEL_IN_INPUT row {i}: fields {sorted(extra | set(armish))}")
        missing = CANDIDATE_KEYS - set(row)
        if missing:
            raise Refused(f"CANDIDATE_FIELDS_MISSING row {i}: {sorted(missing)}")
        for k, v in row.items():
            if isinstance(v, str) and _ARM_WORDS.search(v):
                raise Refused(f"ARM_LABEL_IN_INPUT row {i}: value of {k!r}")
        opaque, tid, rep = row["opaque_id"], row["task_id"], row["repeat"]
        if not (isinstance(opaque, str) and _OPAQUE_RE.fullmatch(opaque)):
            raise Refused(f"BAD_OPAQUE_ID row {i}")
        if opaque in seen:
            raise Refused(f"DUPLICATE_OPAQUE_ID {opaque}")
        seen.add(opaque)
        if not (isinstance(tid, str) and _TASK_RE.fullmatch(tid)) or tid not in survivors:
            raise Refused(f"TASK_NOT_AN_S1_SURVIVOR row {i}: {tid!r}")
        if not (isinstance(rep, int) and not isinstance(rep, bool) and rep >= 1):
            raise Refused(f"BAD_REPEAT row {i}: {rep!r}")
        if not (isinstance(row["diff_sha256"], str) and _SHA256_RE.fullmatch(row["diff_sha256"])):
            raise Refused(f"BAD_DIFF_SHA row {i}")
        flags = row["scoring_flags"]
        if not isinstance(flags, list) or not set(flags) <= SCORING_FLAGS:
            raise Refused(f"ARM_LABEL_IN_INPUT row {i}: unregistered flags {flags!r}")
        diff = (blind_dir / "candidates" / f"{opaque}.diff").read_bytes()
        if sha256_bytes(diff) != row["diff_sha256"]:
            raise Refused(f"DIFF_SHA_MISMATCH {opaque}")
        out.append({**row, "scoring_flags": sorted(flags), "diff": diff})
    return out


def group_candidates(cands: Sequence[Mapping[str, Any]], arms_per_group: int):
    """(task, repeat) -> opaque ids. A group with fewer candidates than arms is dropped
    from all arms (its missing row was harness infra/void, excluded by blind.py); more
    than one per arm is refused."""
    groups: dict[tuple[str, int], list[str]] = {}
    for c in cands:
        groups.setdefault((c["task_id"], c["repeat"]), []).append(c["opaque_id"])
    complete, incomplete = {}, {}
    for g, ids in sorted(groups.items()):
        if len(ids) > arms_per_group:
            raise Refused(f"GROUP_TOO_LARGE {g}: {len(ids)} candidates for {arms_per_group} arms")
        (complete if len(ids) == arms_per_group else incomplete)[g] = sorted(ids)
    return complete, incomplete


# -- sealing (prep_s1_2721 format) ------------------------------------------------------

def seal_candidate(store: Path, key: str, base: str, merge: str, number: int, diff: bytes) -> str:
    """Byte-identical structure to prep_s1_2721.seal_task, one store per candidate."""
    d = Path(store) / "tasks" / key
    d.mkdir(parents=True, exist_ok=False)
    so: dict[str, Any] = {"status": "VALID", "scope_valid": True}
    if diff:
        so["diff_gzip_base64"] = base64.b64encode(gzip.compress(diff, mtime=0)).decode()
        so["diff_sha256"] = sha256_bytes(diff)
    raw = {"route": "s1-2721-selfcheck",
           "raw_response": {"candidate_packet": {"source_revision": base},
                            "strong_online_raw_response": so}}
    raw_b = canon(raw)
    gt_b = canon({"terminal_state": "CLOSED_WITH_MERGED_PR",
                  "details": {"merged_prs": [{"number": number, "merge_commit_sha": merge,
                                              "merged_at": "2026-10-20T00:00:00Z"}]}})
    seal = {"raw_sha256": sha256_bytes(raw_b)}
    write_new(d / "raw.json", raw_b)
    write_new(d / "raw_seal.json", canon(seal))
    write_new(d / "ground_truth.json", gt_b)
    write_new(d / "state.json", canon({"raw_seal": seal, "ground_truth": {"sha256": sha256_bytes(gt_b)}}))
    return sha256_bytes(raw_b)


# -- classification (S0, S4.1, amendment 8.3) ---------------------------------------------

def classify_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    label, sub = receipt.get("label"), receipt.get("sub_reason")
    cand_reached = CAND_ROLE in (receipt.get("trees") or {})
    detail = str(receipt.get("detail") or "")
    if label == RESOLVED:
        return {"cls": SOLVED, "why": "RESOLVED"}
    if label in (PARTIAL, UNRESOLVED, BROKE_EXISTING, NO_CANDIDATE):
        return {"cls": NOT_SOLVED, "why": label}
    if label == NOT_RUNNABLE:
        if sub in CANDIDATE_FAULT_SUBS or receipt.get("cap_attributed_role") == CAND_ROLE:
            return {"cls": NOT_SOLVED, "why": f"CANDIDATE_FAULT:{sub}"}
        return {"cls": INFRA, "why": f"NOT_RUNNABLE:{sub}", "post_candidate": cand_reached}
    if isinstance(label, str) and (label.startswith("NOT_SCORABLE") or label == PENDING_GROUND_TRUTH):
        cap = sub in SCRATCH_SUBS or sub == ORACLE_RUN_FAILED or detail.split(":", 1)[0] in SCRATCH_SUBS
        if cap and cand_reached:
            return {"cls": NOT_SOLVED, "why": f"S4.1_CAP_AFTER_CANDIDATE:{sub}"}
        return {"cls": INFRA, "why": f"{label}:{sub}", "post_candidate": cand_reached}
    raise Refused(f"UNKNOWN_LABEL {label!r}")


def infra_reason_from_log(text: str) -> str:
    found = re.findall(r"INFRA_ABORT (.*?); stopping", text)
    return found[-1] if found else "INFRA_ABORT:unknown"


def is_post_candidate_host_disk(reason: str) -> bool:
    return reason.startswith("host_disk_low") and "(no candidate run yet)" not in reason


# -- process hygiene (S2.1(c)) ----------------------------------------------------------

def _ps_rows() -> list[tuple[int, int, int, int, str, str]] | None:
    try:
        out = subprocess.run(["/bin/ps", "-axww", "-o", "pid=,ppid=,pgid=,uid=,lstart=,command="],
                             capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    rows = []
    for line in out.splitlines():
        parts = line.split(None, 9)
        if len(parts) < 9:
            continue
        try:
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]),
                         " ".join(parts[4:9]), parts[9] if len(parts) > 9 else ""))
        except ValueError:
            continue
    return rows


class ReapError(RuntimeError):
    """The straggler check could not run: the row is infra, never silently clean."""


def _cwd_holders(root: Path) -> list[int]:
    """PIDs of this user's processes whose cwd is under ``root`` (fixed lsof path).
    Fails closed (ReapError) when lsof cannot run or returns nothing usable."""
    try:
        res = subprocess.run(["/usr/sbin/lsof", "-nP", "-a", "-u", str(os.getuid()), "-d", "cwd", "-Fpn"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as exc:
        raise ReapError(f"lsof_failed: {type(exc).__name__}: {exc}") from exc
    out = res.stdout
    if not out.strip():  # our own process always has a cwd: empty output is a failure
        raise ReapError(f"lsof_no_output: rc={res.returncode} {res.stderr.strip()[-200:]}")
    pids, pid, prefix = [], None, str(Path(root).resolve())
    for line in out.splitlines():
        if line.startswith("p"):
            pid = int(line[1:])
        elif line.startswith("n") and pid is not None:
            path = os.path.realpath(line[1:])
            if path == prefix or path.startswith(prefix + os.sep):
                pids.append(pid)
    return sorted(set(pids))


def run_tracked(cmd: Sequence[str], log_path: Path, work: Path, *, poll: float = 0.5) -> dict[str, Any]:
    """Run one scoring in its own session, track every descendant by ppid while it runs,
    and afterwards kill (and record) any tracked descendant still alive and any process
    whose cwd is under ``work``. Identity is (pid, start time); never by name."""
    me = os.getpid()
    with open(log_path, "xb") as fh:
        proc = subprocess.Popen(list(cmd), stdout=fh, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                start_new_session=True)
    tracked: dict[int, tuple[str, str]] = {}
    stop = threading.Event()

    def sample() -> None:
        rows = _ps_rows() or []
        members = {proc.pid} | set(tracked)
        changed = True
        while changed:
            changed = False
            for pid, ppid, _pgid, uid, start, command in rows:
                if pid in members or pid in (0, 1, me) or uid != os.getuid():
                    continue
                if ppid in members:
                    members.add(pid)
                    tracked.setdefault(pid, (start, command[:120]))
                    changed = True

    def loop() -> None:
        while not stop.is_set():
            sample()
            stop.wait(poll)

    th = threading.Thread(target=loop, daemon=True)
    th.start()
    rc = proc.wait()
    stop.set()
    th.join()
    sample()
    killed = []
    try:
        os.killpg(proc.pid, signal.SIGKILL)
        killed.append({"pgid": proc.pid, "how": "session_group"})
    except (ProcessLookupError, PermissionError):
        pass
    try:
        rows = _ps_rows()
        if rows is None:
            raise ReapError("ps_failed")
        alive = {r[0]: r for r in rows}
        _reap_after(tracked, alive, work, me, killed)
    except ReapError as exc:
        return {"rc": rc, "stragglers_killed": killed, "descendants_seen": len(tracked), "reap_error": str(exc)}
    return {"rc": rc, "stragglers_killed": killed, "descendants_seen": len(tracked)}


def _reap_after(tracked, alive, work, me, killed) -> None:
    for pid, (start, command) in sorted(tracked.items()):
        row = alive.get(pid)
        if row is not None and row[4] == start:
            try:
                os.kill(pid, signal.SIGKILL)
                killed.append({"pid": pid, "start": start, "cmd": command, "how": "descendant"})
            except (ProcessLookupError, PermissionError):
                pass
    for pid in _cwd_holders(work):
        if pid in (me, 1):
            continue
        row = alive.get(pid)
        try:
            os.kill(pid, signal.SIGKILL)
            killed.append({"pid": pid, "cmd": row[5][:120] if row else None, "how": "cwd_under_work"})
        except (ProcessLookupError, PermissionError):
            pass


def assert_outside_repos(path: Path) -> None:
    for p in [Path(path).resolve(), *Path(path).resolve().parents]:
        if (p / ".git").exists():
            raise Refused(f"WORK_DIR_INSIDE_REPO: {path} is under {p}")


# -- the scoring run ----------------------------------------------------------------------

class Scorer:
    """Scores sealed candidates. ``runner(cmd, log_path, work) -> {"rc", ...}`` is the
    real ``run_tracked`` in production and a fake in tests."""

    def __init__(self, arch: Path, cfg: Mapping[str, Any], runner: Callable[..., dict[str, Any]] = run_tracked,
                 identity: Callable[[], dict[str, Any]] | None = None):
        self.arch = Path(arch)
        self.cfg = dict(cfg)
        self.runner = runner
        self.identity = identity or (lambda: verify_identity(Path(cfg["driver"]), Path(cfg["s1_archive"]),
                                                              Path(cfg["export"])))
        self.run_id = self.arch.name
        self.lock = threading.Lock()
        self._refs: dict[str, dict[str, str]] = {}

    def reference(self, key: str) -> dict[str, str]:
        with self.lock:
            if key not in self._refs:
                self._refs[key] = s1_reference(Path(self.cfg["s1_receipts"]), key)
            return self._refs[key]

    # One scoring attempt of one candidate in one round.
    def score_one(self, cand: Mapping[str, Any], task: Mapping[str, Any], rnd: int) -> dict[str, Any]:
        ident = self.identity()  # before every scoring: driver + scorer blobs
        opaque, key = cand["opaque_id"], task["key"]
        base_dir = self.arch / "attempts" / opaque
        k = 0
        while (base_dir / f"r{rnd}-a{k}").exists():
            done = base_dir / f"r{rnd}-a{k}" / "attempt.json"
            if done.exists():
                prev = json.loads(done.read_text())
                if "cls" in prev:
                    return prev  # resume: this attempt already finished
            # an interrupted or fatal attempt stays as it is (create-only); take a new slot
            k += 1
        adir = base_dir / f"r{rnd}-a{k}"
        adir.mkdir(parents=True)
        work = Path(self.cfg["work_root"]) / self.run_id / f"{opaque}-r{rnd}-a{k}-{uuid.uuid4().hex[:8]}"
        if work.exists():
            raise Refused(f"WORK_DIR_EXISTS {work}")
        work.parent.mkdir(parents=True, exist_ok=True)
        assert_outside_repos(work.parent)
        out = adir / "out"
        store = self.arch / "inputs" / "stores" / opaque
        cmd = [str(self.cfg["python"]), "-I", str(self.cfg["driver"]), str(self.cfg["export"]),
               str(self.cfg["venvs"]), "--",
               "--store", str(store), "--out", str(out), "--work", str(work), "--task", key,
               "--sandbox", SANDBOX, "--min-free-disk-gib", MIN_FREE_DISK_GIB,
               "--repo-source", f"{task['venv']}={Path(self.cfg['synth_root']) / task['venv']}"]
        ref = self.reference(key)  # S1 venv identity, before the run
        t0 = time.time()
        res = self.runner(cmd, adir / "driver.log", work)
        seconds = round(time.time() - t0, 1)
        rc = res["rc"]
        shutil.rmtree(work, ignore_errors=True)
        receipt_path = out / "tasks" / key / "real_outcome.json"
        att: dict[str, Any] = {"opaque_id": opaque, "round": rnd, "slot": k, "rc": rc, "seconds": seconds,
                               "work": str(work), "cmd": cmd, "identity": ident,
                               "stragglers_killed": res.get("stragglers_killed", []),
                               "descendants_seen": res.get("descendants_seen"),
                               "concurrency": int(self.cfg.get("concurrency", 1))}
        if rc in FATAL_EXITS:
            write_new(adir / "attempt.json", canon({**att, "fatal": FATAL_EXITS[rc]}))
            raise Refused(f"SCORER_FATAL rc={rc} ({FATAL_EXITS[rc]}) on {opaque}")
        if rc == 0 and receipt_path.exists():
            receipt = json.loads(receipt_path.read_text())
            check_receipt_identity(receipt, key, ref)
            c = classify_receipt(receipt)
            att.update(receipt_sha256=sha256_file(receipt_path), label=receipt.get("label"),
                       sub_reason=receipt.get("sub_reason"), cls=c["cls"], why=c["why"],
                       post_candidate=c.get("post_candidate", False),
                       reaped_pids_scorer=(receipt.get("timing") or {}).get("reaped_pids"))
        else:
            log = (adir / "driver.log").read_text(errors="replace") if (adir / "driver.log").exists() else ""
            reason = infra_reason_from_log(log) if rc == INFRA_EXIT else f"SCORER_RC_{rc}_NO_RECEIPT"
            att.update(cls=INFRA, why=f"EXIT_{rc}:{reason}", label=None, infra_reason=reason,
                       host_disk_low_post_candidate=rc == INFRA_EXIT and is_post_candidate_host_disk(reason))
        if res.get("reap_error"):
            # S2.1(c) fails closed: without a straggler check the row is infra (re-run in all
            # arms); the receipt's label stays recorded as a diagnostic.
            att.update(cls=INFRA, why=f"REAP_FAILED:{res['reap_error']}", reap_error=res["reap_error"],
                       post_candidate=False)
        write_new(adir / "attempt.json", canon(att))
        return att

    def score_round(self, items: list[tuple[dict[str, Any], dict[str, Any]]], rnd: int) -> dict[str, dict]:
        """Task-disjoint batches: all rows of one task (every arm and repeat) are scored
        one after another by a single worker, so rows of the same task/repeat are never
        co-scheduled; with concurrency > 1 only different tasks run side by side."""
        self.identity()  # before each batch
        conc = max(1, int(self.cfg.get("concurrency", 1)))
        by_task: dict[str, list[tuple[dict[str, Any], dict[str, Any]]]] = {}
        for c, t in items:
            by_task.setdefault(c["task_id"], []).append((c, t))
        results: dict[str, dict] = {}

        def one_task(batch):
            return [(c["opaque_id"], self.score_one(c, t, rnd)) for c, t in batch]

        with ThreadPoolExecutor(conc) as ex:
            futs = [ex.submit(one_task, batch) for _, batch in sorted(by_task.items())]
            for f in futs:
                results.update(f.result())
        return results


def effective_infra(att: Mapping[str, Any], cand: Mapping[str, Any]) -> bool:
    """A row needs the S4 re-run only if its outcome is not already fixed: a flagged row
    (amendment 8.3) is not solved whatever happens to its diagnostic scoring."""
    return att["cls"] == INFRA and not (set(cand["scoring_flags"]) & NOT_SOLVED_FLAGS)


def final_row(cand: Mapping[str, Any], att: Mapping[str, Any] | None, group_status: str) -> dict[str, Any]:
    flags = set(cand["scoring_flags"])
    flagged = bool(flags & NOT_SOLVED_FLAGS)
    row = {"opaque_id": cand["opaque_id"], "task_id": cand["task_id"], "repeat": cand["repeat"],
           "diff_sha256": cand["diff_sha256"], "scoring_flags": sorted(flags), "group_status": group_status,
           "scorer_label": att.get("label") if att else None,
           "scorer_sub_reason": att.get("sub_reason") if att else None,
           "scorer_class": att.get("cls") if att else None, "why": att.get("why") if att else None}
    if group_status != "KEPT":
        row.update(counted=False, solved=None, broke_existing=None)
        return row
    solved = bool(att and att["cls"] == SOLVED) and not flagged
    row.update(counted=True, solved=solved,
               broke_existing=bool(att and att.get("label") == BROKE_EXISTING),
               flag_override=flagged,
               diagnostic_stripped_resolved=bool(flagged and att and att.get("label") == RESOLVED))
    return row


def run_scoring(arch: Path, blind_dir: Path, cfg: Mapping[str, Any], *, arms_per_group: int,
                runner: Callable[..., dict[str, Any]] = run_tracked,
                identity: Callable[[], dict[str, Any]] | None = None,
                resume: bool = False, require_lab: bool = True) -> dict[str, Any]:
    arch = Path(arch)
    if require_lab and not os.environ.get("LAB_RID"):
        raise Refused("NOT_UNDER_LAB: run this through `lab run` on the Mac mini (S2.1(c), amendment 7.6)")
    if (arch / "MANIFEST.sha256").exists():
        raise Refused(f"ARCHIVE_SEALED: {arch} already has a manifest")
    if arch.exists() and not resume:
        raise Refused(f"ARCHIVE_EXISTS: {arch} (create-only; use --resume to continue an unsealed run)")
    scorer = Scorer(arch, cfg, runner, identity)
    ident = scorer.identity()
    s1 = json.loads(Path(cfg["s1_result"]).read_text())
    survivors = {r["id"] for r in s1["rows"] if r.get("survives")}
    index = {t["id"]: t for t in json.loads(Path(cfg["task_index"]).read_text())}
    cands = load_candidates(blind_dir, survivors)
    by_id = {c["opaque_id"]: c for c in cands}
    complete, incomplete = group_candidates(cands, arms_per_group)
    cand_jsonl = (Path(blind_dir) / "candidates.jsonl").read_bytes()
    if not resume:
        arch.mkdir(parents=True)
        write_new(arch / "inputs" / "candidates.jsonl", cand_jsonl)
        write_new(arch / "run.json", canon({
            "schema": SCHEMA, "run_id": arch.name, "started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "candidates_jsonl_sha256": sha256_bytes(cand_jsonl), "arms_per_group": arms_per_group,
            "identity": ident, "scorer_version": SCORER_VERSION, "profile_sha256": PROFILE_SHA256,
            "flags": ["--sandbox", SANDBOX, "--store", "--min-free-disk-gib", MIN_FREE_DISK_GIB],
            "score_arms_sha256": sha256_file(Path(__file__)), "max_reruns": MAX_RERUNS,
            "lab_rid": os.environ.get("LAB_RID"),
            "concurrency": int(cfg.get("concurrency", 1)), "scheduling": "task-disjoint",
            "config": {k: str(v) for k, v in cfg.items()}}))
        for c in cands:
            t = index[c["task_id"]]
            seal_candidate(arch / "inputs" / "stores" / c["opaque_id"], t["key"], t["base"], t["merge"],
                           int(c["task_id"].rsplit("-", 1)[1]), c["diff"])
    else:
        recorded = json.loads((arch / "run.json").read_text())["candidates_jsonl_sha256"]
        if recorded != sha256_bytes(cand_jsonl):
            raise Refused("RESUME_INPUT_CHANGED: candidates.jsonl differs from the archived one")

    history: dict[tuple[str, int], list[dict[str, dict]]] = {g: [] for g in [*complete, *incomplete]}
    if incomplete:
        # Never counted, but scored once so the NOOP void (S3) sees every NOOP row.
        res = scorer.score_round([(by_id[o], index[g[0]]) for g in sorted(incomplete) for o in incomplete[g]], 0)
        for g in incomplete:
            history[g].append({o: res[o] for o in incomplete[g]})
    pending = sorted(complete)
    for rnd in range(MAX_RERUNS + 1):
        if not pending:
            break
        items = [(by_id[o], index[g[0]]) for g in pending for o in complete[g]]
        res = scorer.score_round(items, rnd)
        nxt = []
        for g in pending:
            atts = {o: res[o] for o in complete[g]}
            history[g].append(atts)
            if any(effective_infra(atts[o], by_id[o]) for o in complete[g]):
                nxt.append(g)
        pending = nxt
    return finalize(arch, by_id, complete, incomplete, history, dropped=set(pending))


def finalize(arch: Path, by_id: Mapping[str, Mapping[str, Any]], complete, incomplete, history,
             dropped: set) -> dict[str, Any]:
    arch = Path(arch)
    if (arch / "MANIFEST.sha256").exists():
        raise Refused("ARCHIVE_SEALED")
    groups, s42, anomalies, rows = [], [], [], []
    for g, ids in sorted(complete.items()):
        rounds = history[g]
        last = rounds[-1]
        status = "DROPPED_INFRA" if g in dropped else "KEPT"
        hd = [{"opaque_id": o, "task_id": g[0], "repeat": g[1], "round": r, "reason": atts[o].get("infra_reason")}
              for r, atts in enumerate(rounds) for o in ids if atts[o].get("host_disk_low_post_candidate")]
        s42.extend(hd)
        for r, atts in enumerate(rounds):
            for o in ids:
                if atts[o]["cls"] == INFRA and atts[o].get("post_candidate"):
                    anomalies.append({"opaque_id": o, "task_id": g[0], "repeat": g[1], "round": r,
                                      "why": atts[o]["why"]})
        possible_evasion = sorted({h["opaque_id"] for h in hd}) if status != "KEPT" else []
        groups.append({"task_id": g[0], "repeat": g[1], "opaque_ids": ids, "rounds": len(rounds),
                       "status": status, "possible_evasion_opaque_ids": possible_evasion,
                       "infra_whys": [sorted({atts[o]["why"] for o in ids if atts[o]["cls"] == INFRA})
                                      for atts in rounds]})
        for o in ids:
            row = final_row(by_id[o], last[o], status)
            row["attempts"] = [atts[o].get("receipt_sha256") or atts[o]["why"] for atts in rounds]
            row["round_labels"] = [atts[o].get("label") for atts in rounds]
            row["stragglers_killed"] = sum(len(atts[o].get("stragglers_killed") or []) for atts in rounds)
            row["identity"] = last[o].get("identity")
            if last[o].get("receipt_sha256"):
                rdir = arch / "attempts" / o / f"r{last[o]['round']}-a{last[o]['slot']}"
                key = next((rdir / "out" / "tasks").iterdir()).name
                row["receipt_path"] = str((rdir / "out" / "tasks" / key / "real_outcome.json").relative_to(arch))
                row["receipt_sha256"] = last[o]["receipt_sha256"]
            rows.append(row)
    for g, ids in sorted(incomplete.items()):
        rounds = history.get(g) or []
        groups.append({"task_id": g[0], "repeat": g[1], "opaque_ids": ids, "rounds": len(rounds),
                       "status": "DROPPED_INCOMPLETE_GROUP", "possible_evasion_opaque_ids": [], "infra_whys": []})
        for o in ids:
            row = final_row(by_id[o], rounds[-1][o] if rounds else None, "DROPPED_INCOMPLETE_GROUP")
            row["round_labels"] = [atts[o].get("label") for atts in rounds]
            rows.append(row)
    for row in rows:
        write_new(arch / "rows" / f"{row['opaque_id']}.json", canon(row))
    kept = [r for r in rows if r["counted"]]
    summary = {
        "candidates": len(rows), "groups": len(groups),
        "groups_kept": sum(g["status"] == "KEPT" for g in groups),
        "groups_dropped_infra": sum(g["status"] == "DROPPED_INFRA" for g in groups),
        "groups_dropped_incomplete": sum(g["status"] == "DROPPED_INCOMPLETE_GROUP" for g in groups),
        "groups_dropped_possible_evasion": sum(bool(g["possible_evasion_opaque_ids"]) for g in groups),
        "rows_counted": len(kept), "rows_solved_blind_total": sum(r["solved"] for r in kept),
        "rows_flag_override": sum(r["flag_override"] for r in kept),
        "s42_host_disk_low_post_candidate": len(s42), "post_candidate_oracle_anomalies": len(anomalies),
        "stragglers_killed_total": sum(r.get("stragglers_killed", 0) for r in rows),
    }
    write_new(arch / "groups.json", canon(groups))
    write_new(arch / "s42_host_disk_low.json", canon({
        "rule": "amendment 6 item 2 (S4.2): host_disk_low infra aborts after a candidate run, per opaque id,"
                " listed before unblinding; dropped groups that contain one are possible evasion and need a"
                " manual lingering-process inspection before unblinding", "aborts": s42,
        "possible_evasion_groups": [g for g in groups if g["possible_evasion_opaque_ids"]]}))
    write_new(arch / "post_candidate_anomalies.json", canon(anomalies))
    write_new(arch / "summary.json", canon(summary))
    manifest_sha = seal_archive(arch)
    return {**summary, "manifest_sha256": manifest_sha, "archive": str(arch)}


def seal_archive(arch: Path) -> str:
    """S6: hash every file into MANIFEST.sha256 (written before unblinding), record the
    manifest's own sha256 beside it, and make the whole archive read-only."""
    lines = []
    for p in sorted(Path(arch).rglob("*")):
        if p.is_file() and not p.is_symlink():
            lines.append(f"{sha256_file(p)}  ./{p.relative_to(arch).as_posix()}")
    data = ("\n".join(lines) + "\n").encode()
    write_new(Path(arch) / "MANIFEST.sha256", data)
    msha = sha256_bytes(data)
    write_new(Path(arch) / "MANIFEST.sha256.sha256", (msha + "\n").encode())
    for p in sorted(Path(arch).rglob("*"), reverse=True):
        if not p.is_symlink():
            os.chmod(p, 0o555 if p.is_dir() else 0o444)
    os.chmod(arch, 0o555)
    return msha


def verify_archive(arch: Path, expect_manifest_sha: str | None = None) -> str:
    arch = Path(arch)
    data = (arch / "MANIFEST.sha256").read_bytes()
    msha = sha256_bytes(data)
    if msha != (arch / "MANIFEST.sha256.sha256").read_text().strip():
        raise Refused("ARCHIVE_MANIFEST_SHA_MISMATCH")
    if expect_manifest_sha and msha != expect_manifest_sha:
        raise Refused(f"ARCHIVE_MANIFEST_NOT_THE_POSTED_ONE: {msha}")
    listed = {}
    for line in data.decode().splitlines():
        h, rel = line.split("  ", 1)
        listed[rel[2:]] = h
    actual = {p.relative_to(arch).as_posix() for p in arch.rglob("*") if p.is_file()} - {
        "MANIFEST.sha256", "MANIFEST.sha256.sha256"}
    if actual != set(listed):
        raise Refused(f"ARCHIVE_FILES_CHANGED: {sorted(actual ^ set(listed))[:5]}")
    for rel, h in listed.items():
        if sha256_file(arch / rel) != h:
            raise Refused(f"ARCHIVE_FILE_MODIFIED: {rel}")
    return msha


# -- analysis (S5, amendment 8) ----------------------------------------------------------

def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar (binomial, p = 0.5) on the discordant pairs."""
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(b, c) + 1)) / 2 ** n
    return min(1.0, 2 * tail)


def paired_bootstrap(diffs: Sequence[float], *, seed: int = BOOTSTRAP_SEED,
                     resamples: int = BOOTSTRAP_RESAMPLES) -> dict[str, float]:
    """Percentile 95% CI of the mean per-task difference; a fresh generator with the
    registered seed for every CI (amendment 8.1)."""
    import numpy as np

    d = np.asarray(diffs, dtype=float)
    if d.size == 0:
        return {"mean": float("nan"), "lo": float("nan"), "hi": float("nan"), "n": 0}
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, d.size, size=(resamples, d.size))
    means = d[idx].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return {"mean": float(d.mean()), "lo": float(lo), "hi": float(hi), "n": int(d.size)}


def decision_band(ci: Mapping[str, float], broke_delta: float) -> str:
    if ci["n"] and ci["lo"] > 0 and broke_delta <= BROKE_MARGIN + 1e-12:
        return "WORKS"
    if ci["n"] and ci["hi"] < 0:
        return "HARMS"
    return "NO_DETECTABLE_DIFFERENCE"


MDE_REGISTERED = {19: 0.24, 30: 0.18, 46: 0.14}  # amendment 8.2, 80% power


def compare(rows: Sequence[Mapping[str, Any]], treatment: str, control: str, tasks: Iterable[str] | None = None):
    per: dict[str, dict[str, list[Mapping[str, Any]]]] = {}
    for r in rows:
        if r["counted"] and (tasks is None or r["task_id"] in tasks):
            per.setdefault(r["task_id"], {}).setdefault(r["arm"], []).append(r)
    diffs, b, c, tasks_used = [], 0, 0, []
    for tid in sorted(per):
        t_rows, c_rows = per[tid].get(treatment, []), per[tid].get(control, [])
        if not t_rows or not c_rows:
            continue
        tasks_used.append(tid)
        rt = sum(r["solved"] for r in t_rows) / len(t_rows)
        rc = sum(r["solved"] for r in c_rows) / len(c_rows)
        diffs.append(rt - rc)
        mt = sum(r["solved"] for r in t_rows) * 2 > len(t_rows)
        mc = sum(r["solved"] for r in c_rows) * 2 > len(c_rows)
        b += mt and not mc
        c += mc and not mt
    ci = paired_bootstrap(diffs)

    def broke(arm: str) -> float:
        rs = [r for tid in tasks_used for r in per[tid].get(arm, [])]
        return sum(r["broke_existing"] for r in rs) / len(rs) if rs else float("nan")

    def solve_rate(arm: str) -> float:
        """Macro mean: the mean over tasks of the per-task repeat mean (what the CI is on)."""
        rates = [sum(r["solved"] for r in per[tid][arm]) / len(per[tid][arm]) for tid in tasks_used]
        return sum(rates) / len(rates) if rates else float("nan")

    def pooled(arm: str) -> float:
        rs = [r for tid in tasks_used for r in per[tid].get(arm, [])]
        return sum(r["solved"] for r in rs) / len(rs) if rs else float("nan")

    bd = broke(treatment) - broke(control)
    n = len(tasks_used)
    mde_n = min(MDE_REGISTERED, key=lambda k: abs(k - n)) if n else None
    return {"treatment": treatment, "control": control, "tasks": n, "ci95": ci,
            "solve_rate": {treatment: solve_rate(treatment), control: solve_rate(control)},
            "solve_rate_pooled_rows": {treatment: pooled(treatment), control: pooled(control)},
            "mcnemar_majority_of_3": {"treatment_only": b, "control_only": c, "p_exact": mcnemar_exact(b, c)},
            "broke_existing_rate": {treatment: broke(treatment), control: broke(control), "delta": bd},
            "band": decision_band(ci, bd),
            "mde_registered_80pct": {"n_nearest": mde_n, "mde": MDE_REGISTERED.get(mde_n)} if mde_n else None}


def analyze(arch: Path, arm_map_path: Path, *, treatment: str, control: str, noop: str | None,
            strata: Mapping[str, str], primary_set: str, expect_manifest_sha: str) -> dict[str, Any]:
    if not expect_manifest_sha:
        raise Refused("EXPECT_MANIFEST_SHA_REQUIRED: pass the manifest sha256 posted before unblinding")
    arch = Path(arch)
    msha = verify_archive(arch, expect_manifest_sha)
    run = json.loads((arch / "run.json").read_text())
    amap = json.loads(Path(arm_map_path).read_text())
    if amap.get("candidates_jsonl_sha256") != run["candidates_jsonl_sha256"]:
        raise Refused("ARM_MAP_NOT_FOR_THIS_CANDIDATE_SET")
    rows = []
    for p in sorted((arch / "rows").glob("*.json")):
        r = json.loads(p.read_text())
        m = amap["map"].get(r["opaque_id"])
        if m is None or m["task_id"] != r["task_id"] or int(m["repeat"]) != r["repeat"]:
            raise Refused(f"ARM_MAP_ROW_MISMATCH {r['opaque_id']}")
        rows.append({**r, "arm": m["arm"]})
    excluded = amap.get("excluded") or []
    arms = sorted({r["arm"] for r in rows})
    all_arms = sorted(set(arms) | {e["arm"] for e in excluded})
    for a in (treatment, control, *([noop] if noop else [])):
        if a not in arms:
            raise Refused(f"ARM_NOT_IN_MAP {a}: {arms}")
    noop_arms = [a for a in all_arms if "NOOP" in str(a).upper()]
    if noop_arms and not noop:
        raise Refused(f"NOOP_REQUIRED: the arm map has {noop_arms}; pass --noop")
    unknown = sorted({r["task_id"] for r in rows if r["task_id"] not in strata})
    if unknown:
        raise Refused(f"TASK_SET_UNKNOWN: {unknown[:5]}")
    if primary_set not in set(strata.values()):
        raise Refused(f"PRIMARY_SET_UNKNOWN {primary_set!r}: {sorted(set(strata.values()))}")
    groups = json.loads((arch / "groups.json").read_text())

    # Incomplete groups: every missing arm must be a true-infra exclusion in the arm map.
    exclusions_by_arm: dict[str, dict[str, int]] = {}
    for e in excluded:
        if e.get("infra") is not True:
            raise Refused(f"NON_INFRA_EXCLUSION {e.get('arm')} {e.get('task_id')}#{e.get('repeat')}: "
                          f"{e.get('reason') or e.get('outcome')} (only infra may leave the candidate set)")
        reason = str(e.get("reason") or e.get("outcome"))
        exclusions_by_arm.setdefault(e["arm"], {}).setdefault(reason, 0)
        exclusions_by_arm[e["arm"]][reason] += 1
    incomplete_report = []
    for g in groups:
        if g["status"] != "DROPPED_INCOMPLETE_GROUP":
            continue
        present = {amap["map"][o]["arm"] for o in g["opaque_ids"]}
        why = {e["arm"]: str(e.get("reason") or e.get("outcome")) for e in excluded
               if e["task_id"] == g["task_id"] and int(e["repeat"]) == g["repeat"]}
        missing = sorted(set(all_arms) - present)
        unexplained = [a for a in missing if a not in why]
        if unexplained:
            raise Refused(f"INCOMPLETE_GROUP_UNEXPLAINED {g['task_id']}#{g['repeat']}: {unexplained}")
        incomplete_report.append({"task_id": g["task_id"], "repeat": g["repeat"],
                                  "excluded_by_arm": {a: why[a] for a in missing}})

    per_arm = {}
    for a in arms:
        rs = [r for r in rows if r["arm"] == a]
        kept = [r for r in rs if r["counted"]]
        per_arm[a] = {"rows": len(rs), "counted": len(kept), "solved": sum(r["solved"] for r in kept),
                      "scorer_resolved": sum(r["scorer_label"] == RESOLVED for r in kept),
                      "broke_existing": sum(r["broke_existing"] for r in kept),
                      "flag_override_not_solved": sum(r["flag_override"] for r in kept),
                      "run_invalid_not_solved": sum(FLAG_RUN_INVALID in r["scoring_flags"] for r in kept),
                      "flagged_but_stripped_remainder_resolved": sum(r["diagnostic_stripped_resolved"] for r in kept),
                      "dropped": sum(not r["counted"] for r in rs)}
    void = []
    if "noop_nonempty_diff" not in amap:
        # Fail closed: an arm map from a blind.py without the check must not skip it.
        raise Refused("NOOP_CHECK_MISSING: the arm map has no noop_nonempty_diff (re-run blind.py)")
    if amap["noop_nonempty_diff"]:
        # PREREG v0.9.7: a non-empty diff in any NOOP / NEXUS_NOOP row (any attempt, any
        # block) voids the run without scoring.
        void.append({"reason": "NOOP_NONEMPTY_DIFF: the run is void; stop and investigate",
                     "rows": [{k: e.get(k) for k in ("arm", "run_id", "diff_sha256")}
                              for e in amap["noop_nonempty_diff"]]})
    if noop:
        # S3: any RESOLVED in any round of any NOOP row (counted, dropped or incomplete).
        noop_resolved = [r["opaque_id"] for r in rows if r["arm"] == noop and (
            RESOLVED in (r.get("round_labels") or []) or r["scorer_label"] == RESOLVED)]
        if noop_resolved:
            void.append({"reason": "NOOP_RESOLVED (S3): the run is void; stop and investigate",
                         "opaque_ids": noop_resolved})
    sets = {s: {t for t, v in strata.items() if v == s} for s in sorted(set(strata.values()))}
    primary = compare(rows, treatment, control, sets[primary_set])
    other_sets = {s: compare(rows, treatment, control, tasks) for s, tasks in sets.items() if s != primary_set}
    # S4.2: possible-evasion drops, per arm; if they fall on one arm only, report the
    # primary result with those groups too (their suspect rows counted as not solved).
    evasion = [g for g in groups if g["possible_evasion_opaque_ids"]]
    ev_by_arm: dict[str, int] = {}
    for g in evasion:
        for o in g["possible_evasion_opaque_ids"]:
            a = amap["map"][o]["arm"]
            ev_by_arm[a] = ev_by_arm.get(a, 0) + 1
    with_evasion = None
    if evasion and len(ev_by_arm) == 1:
        keys = {(g["task_id"], g["repeat"]) for g in evasion}
        suspects = {o for g in evasion for o in g["possible_evasion_opaque_ids"]}
        alt = []
        for r in rows:
            if (r["task_id"], r["repeat"]) in keys:
                solved = r["opaque_id"] not in suspects and r["scorer_class"] == SOLVED and not (
                    set(r["scoring_flags"]) & NOT_SOLVED_FLAGS)
                r = {**r, "counted": True, "solved": solved, "broke_existing": r["scorer_label"] == BROKE_EXISTING}
            alt.append(r)
        with_evasion = compare(alt, treatment, control, sets[primary_set])
    return {"schema": SCHEMA + ".analysis", "archive_manifest_sha256": msha, "arms": per_arm,
            "primary_set": primary_set, "primary": primary, "other_sets": other_sets, "void": void,
            "verdict": "VOID" if void else primary["band"],
            "drops": {"infra": sum(g["status"] == "DROPPED_INFRA" for g in groups),
                      "incomplete_group": sum(g["status"] == "DROPPED_INCOMPLETE_GROUP" for g in groups),
                      "incomplete_groups_by_arm": incomplete_report,
                      "exclusions_by_arm": exclusions_by_arm,
                      "possible_evasion_by_arm": ev_by_arm},
            "primary_with_possible_evasion_groups": with_evasion,
            "concurrency": run.get("concurrency"),
            "seed": BOOTSTRAP_SEED, "resamples": BOOTSTRAP_RESAMPLES}


# -- CLI --------------------------------------------------------------------------------

def _cfg_from(args: argparse.Namespace) -> dict[str, Any]:
    return {k: getattr(args, k) for k in (*DEFAULTS, "concurrency")}


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="seal + score + archive (blind; inside lab run)")
    r.add_argument("--blind-dir", required=True, type=Path, help="blind.py --out (candidates.jsonl + candidates/)")
    r.add_argument("--archive", required=True, type=Path, help="new create-only archive dir")
    r.add_argument("--arms-per-group", required=True, type=int, help="number of arms (rows per task x repeat)")
    r.add_argument("--concurrency", type=int, default=1,
                   help="task-disjoint workers (rows of one task always run one after another)")
    r.add_argument("--resume", action="store_true", help="continue an unsealed archive (finished attempts kept)")
    r.add_argument("--allow-outside-lab", action="store_true", help="smoke/tests only")
    for k, v in DEFAULTS.items():
        r.add_argument("--" + k.replace("_", "-"), dest=k, default=v)
    a = sub.add_parser("analyze", help="S5 after unblinding (custodian)")
    a.add_argument("--archive", required=True, type=Path)
    a.add_argument("--arm-map", required=True, type=Path)
    a.add_argument("--treatment", required=True)
    a.add_argument("--control", required=True)
    a.add_argument("--noop")
    a.add_argument("--s1-result", type=Path, default=DEFAULTS["s1_result"], help="for strata (row 'set')")
    a.add_argument("--primary-set", required=True, help="the S1 set the verdict is on (M for Q1)")
    a.add_argument("--expect-manifest-sha256", required=True)
    a.add_argument("--out", type=Path, help="write the report here (create-only)")
    v = sub.add_parser("verify-identity", help="check the driver and scorer pins only")
    for k in ("driver", "s1_archive", "export"):
        v.add_argument("--" + k.replace("_", "-"), dest=k, default=DEFAULTS[k])
    args = p.parse_args(argv)
    try:
        if args.cmd == "verify-identity":
            print(json.dumps(verify_identity(Path(args.driver), Path(args.s1_archive), Path(args.export)), indent=1))
            return 0
        if args.cmd == "run":
            res = run_scoring(args.archive, args.blind_dir, _cfg_from(args), arms_per_group=args.arms_per_group,
                              resume=args.resume, require_lab=not args.allow_outside_lab)
            print(json.dumps(res, indent=1, sort_keys=True))
            return 0
        s1 = json.loads(Path(args.s1_result).read_text())
        strata = {row["id"]: row["set"] for row in s1["rows"] if row.get("survives")}
        rep = analyze(args.archive, args.arm_map, treatment=args.treatment, control=args.control,
                      noop=args.noop, strata=strata, primary_set=args.primary_set,
                      expect_manifest_sha=args.expect_manifest_sha256)
        text = json.dumps(rep, indent=1, sort_keys=True)
        if args.out:
            write_new(args.out, (text + "\n").encode())
        print(text)
        return 3 if rep["void"] else 0
    except Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
