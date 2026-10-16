"""Seatbelt write boundary for the headless Agy dispatcher (#2202, Owner decision on #1912).

``scripts/ops/nexus-agy-dispatch`` owns its own ``Popen`` loop (stream
telemetry, quota and stall watchdogs), so it cannot hand the run to
``run_cli_worker``.  This module gives it the same confinement the worker
adapter gets from ``run_cli_worker``:

* a disposable per-run HOME holding only the copied Agy auth files and an
  explicit settings profile (``materialize_run_home``);
* an exact, allowlisted child environment (``agy_child_env``) plus the
  per-run tag the descendant sweep looks for;
* a Seatbelt profile (``build_seatbelt_profile``) that denies every file
  write except the target worktree (minus ``.git``/``.agents``) and the
  per-run root, plus literal files the dispatcher itself must let Agy append
  to (its ``--log-file`` attestation log);
* a post-exit descendant sweep over the process tree, the run tag and the
  processes whose cwd is inside the target or the run root; it runs exactly
  once per launched run, also when the launch frame raised.

The ``--log-file`` attestation log is writable by the confined process, so
attestation parsing must not treat its content as trusted (follow-up #2260).

There is no unconfined fallback: when ``sandbox-exec`` is unavailable the
boundary cannot be prepared and the dispatcher refuses the run.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Optional

from nexus.executors import cli_worker
from nexus.executors.agy_write_admission import (
    KEYCHAIN_ISOLATED,
    KEYCHAIN_NOT_APPLICABLE,
    SANDBOX_EXEC_PATH,
    SECURITY_TOOL_PATH,
    _sbpl_path,
    agy_child_env,
    build_seatbelt_profile,
    materialize_run_home,
    path_inside,
    seatbelt_available,
    worker_home,
)

AGY_WRITE_BOUNDARY_UNAVAILABLE = "AGY_WRITE_BOUNDARY_UNAVAILABLE"
KEEP_RUN_ROOT_ENV = "NEXUS_AGY_KEEP_RUN_ROOT"


class AgyWriteBoundaryError(RuntimeError):
    """The boundary could not be prepared; the run must not start."""


def boundary_available() -> bool:
    return seatbelt_available()


# Agy's own startup writes under the disposable HOME's locked ``.gemini/config``
# are denied by the #1912 profile by design; Seatbelt reports them as EPERM
# (observed in agy.log of agyop_2bdee3a289264238a3667857302c7fca).  Only that
# exact error for exactly these run-HOME paths is expected boundary noise; any
# other denied path, inside the run HOME or not, is a real permission signal.
EXPECTED_RUN_HOME_DENIED_PATHS = (
    Path(".gemini") / "config" / "mcp_config.json",
    Path(".gemini") / "config" / ".migrated",
)
_SEATBELT_DENIAL_MARKER = "operation not permitted"
_ABSOLUTE_PATH_RE = re.compile(r"/[^\s:'\"]+")


def _path_key(path: Path) -> str:
    return os.path.normcase(os.path.realpath(path))


def is_expected_run_home_denial(line: str, run_home: str | Path) -> bool:
    """True for a Seatbelt EPERM line naming only the expected run-HOME paths.

    Paths compare as realpaths, so macOS's ``/var`` alias of the
    ``/private/var`` run root matches too.
    """
    if _SEATBELT_DENIAL_MARKER not in line.lower():
        return False
    paths = _ABSOLUTE_PATH_RE.findall(line)
    expected = {_path_key(Path(run_home) / rel) for rel in EXPECTED_RUN_HOME_DENIED_PATHS}
    return bool(paths) and all(_path_key(Path(raw)) in expected for raw in paths)


def strip_expected_run_home_denials(text: str, run_home: str | Path | None) -> str:
    """Drop the expected run-HOME Seatbelt denials before permission-marker matching."""
    if not text or run_home is None:
        return text
    return "".join(
        line
        for line in text.splitlines(keepends=True)
        if not is_expected_run_home_denial(line, run_home)
    )


def _prepare_run_home_keychain(run_home: Path) -> str:
    """Give the run HOME its own default keychain before Seatbelt starts.

    Without one, agy's OAuth token store finds no default keychain and macOS
    raises a modal "no keychain" dialog that blocks until a human answers.
    ``security`` runs here, unsandboxed and with ``HOME=<run_home>``; the
    sandboxed agy only reads/writes that keychain file, which lies inside the
    writable run root.
    """
    from nexus.services.agy_account_pool import (
        AgyAccountPoolManagerError,
        ensure_macos_isolated_keychain,
    )

    try:
        keychain = ensure_macos_isolated_keychain(str(run_home), security=SECURITY_TOOL_PATH)
    except AgyAccountPoolManagerError as exc:
        raise AgyWriteBoundaryError(f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:{exc}") from exc
    return KEYCHAIN_NOT_APPLICABLE if keychain is None else KEYCHAIN_ISOLATED


def _with_literal_writes(profile: str, files: Iterable[Path]) -> str:
    entries = [f'  (literal "{_sbpl_path(path)}")' for path in files]
    if not entries:
        return profile
    return profile + "\n".join(["(allow file-write*", *entries, ")"]) + "\n"


@dataclass
class AgyDispatchBoundary:
    """One accept-edits run's write boundary; call ``cleanup`` when done."""

    target: Path
    run_root: Path
    run_home: Path
    run_tmp: Path
    env: dict[str, str]
    profile: str
    profile_path: Path
    run_tag: str
    home_profile_sha256: str
    keychain_state: str = KEYCHAIN_NOT_APPLICABLE
    _baseline: Any = field(default=None, repr=False)
    _tracker: Any = field(default=None, repr=False)
    _launched: bool = field(default=False, repr=False)
    _swept: Optional[bool] = field(default=None, repr=False)

    @property
    def seatbelt_sha256(self) -> str:
        return hashlib.sha256(self.profile.encode("utf-8")).hexdigest()

    @property
    def sweep_roots(self) -> tuple[str, ...]:
        return (str(self.target), str(self.run_root))

    def wrap_argv(self, argv: Iterable[str]) -> list[str]:
        return [SANDBOX_EXEC_PATH, "-f", str(self.profile_path), *argv]

    def before_launch(self) -> None:
        """Record the pre-start process facts the sweep compares against."""
        self._baseline = cli_worker.sweep_baseline()

    def after_launch(self, pid: int) -> None:
        self._launched = True
        self._tracker = cli_worker.track_run(self.run_tag, pid)

    def sweep(self) -> bool:
        """Kill every surviving worker descendant; True only when provably clean.

        Runs once per launched run; later calls return the first result.
        """
        if not self._launched:
            return True
        if self._swept is not None:
            return self._swept
        tracker, self._tracker = self._tracker, None
        if tracker is None:
            self._swept = False
            return False
        self._swept = cli_worker.sweep_run(self.run_tag, tracker, self._baseline, self.sweep_roots)
        return self._swept

    def cleanup(self) -> None:
        # A launched run whose frame raised before its sweep is swept here.
        if self._launched and self._swept is None:
            self.sweep()
        tracker, self._tracker = self._tracker, None
        if tracker is not None:
            tracker.stop()
        cli_worker.release_run(self.run_tag)
        # Diagnostics only: keep the run root (disposable HOME, keychain) for
        # inspection; the operator deletes it afterwards.
        if os.environ.get(KEEP_RUN_ROOT_ENV) != "1":
            shutil.rmtree(self.run_root, ignore_errors=True)
        shutil.rmtree(self.profile_path.parent, ignore_errors=True)


def _admit_extra_writable_file(
    raw: str | Path, *, target: Path, roots: list[Path], lease_home: Optional[Path]
) -> Path:
    """Admit one literal write grant, or refuse the boundary with a typed code."""

    def refuse(reason: str) -> AgyWriteBoundaryError:
        return AgyWriteBoundaryError(f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:{reason}")

    candidate = Path(raw).expanduser()
    if not candidate.is_absolute():
        raise refuse("relative_extra_path")
    # The confined process can write (and so replace) a literal-allowed path;
    # a symlinked leaf would redirect the next attempt's grant elsewhere.
    # Only the parent may resolve (e.g. /var -> /private/var).
    if candidate.is_symlink():
        raise refuse("extra_path_is_symlink")
    parent_real = os.path.realpath(candidate.parent)
    real = Path(os.path.realpath(candidate))
    if str(real) != os.path.join(parent_real, candidate.name):
        raise refuse("extra_path_is_symlink")
    # A literal re-allow inside the target could reopen the .git/.agents denies.
    if path_inside(real, target):
        raise refuse("extra_path_in_target")
    if real.is_dir():
        raise refuse("extra_path_is_directory")
    if real.exists() and not real.is_file():
        raise refuse("extra_path_not_regular_file")
    real_home = Path(os.path.realpath(Path.home()))
    # (A lease HOME equal to the real HOME is covered by the dotfile rule below.)
    if lease_home is not None and lease_home != real_home and path_inside(real, lease_home):
        raise refuse("extra_path_in_lease_home")
    if not any(path_inside(real, root) for root in roots):
        raise refuse("extra_path_outside_allowed_roots")
    # Even under an allowed root, never a real-HOME dotfile dir other than
    # ~/.local/state (where the operations state dir lives).
    if path_inside(real, real_home) and real != real_home:
        relative = Path(os.path.relpath(real, real_home))
        if relative.parts[0].startswith(".") and not path_inside(
            real, real_home / ".local" / "state"
        ):
            raise refuse("extra_path_in_home_dotfiles")
    return real


def prepare_accept_edits_boundary(
    *,
    source_env: Optional[Mapping[str, str]],
    target: str | Path,
    extra_writable_files: Iterable[str | Path] = (),
    extra_writable_roots: Iterable[str | Path] = (),
) -> AgyDispatchBoundary:
    """Build the disposable HOME, exact env and Seatbelt profile for one run.

    ``source_env`` is the leased account environment; only its HOME (for the
    copied auth files) and the ``agy_child_env`` allowlist reach the child.
    ``extra_writable_files`` (the dispatcher's ``--log-file``) are honoured only
    inside one of ``extra_writable_roots`` (the operations state dir); see
    ``_admit_extra_writable_file``.
    """
    if not boundary_available():
        raise AgyWriteBoundaryError(f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:seatbelt_unavailable")
    target_real = Path(os.path.realpath(Path(target).expanduser()))
    if not target_real.is_dir():
        raise AgyWriteBoundaryError(f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:target_missing")
    roots = [Path(os.path.realpath(Path(root).expanduser())) for root in extra_writable_roots]
    extras = [
        _admit_extra_writable_file(
            raw,
            target=target_real,
            roots=roots,
            lease_home=worker_home(source_env) if (source_env or {}).get("HOME") else None,
        )
        for raw in extra_writable_files
    ]
    run_root = Path(os.path.realpath(tempfile.mkdtemp(prefix="nexus-agy-dispatch-run-")))
    profile_dir = Path(os.path.realpath(tempfile.mkdtemp(prefix="nexus-agy-dispatch-sb-")))
    try:
        run_home = run_root / "home"
        run_tmp = run_root / "tmp"
        run_tmp.mkdir(parents=True)
        refusal, home_profile_sha256 = materialize_run_home(
            worker_home(source_env), run_home, read_only=False, isolate_keychain=False
        )
        if refusal is not None:
            raise AgyWriteBoundaryError(f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:{refusal}")
        # The boundary isolates the keychain itself so its refusal carries the
        # security(1) detail; materialize_run_home does it for the other callers.
        keychain_state = _prepare_run_home_keychain(run_home)
        try:
            profile = _with_literal_writes(
                build_seatbelt_profile(
                    run_root=run_root, writable_target=target_real, run_home=run_home
                ),
                extras,
            )
        except ValueError as exc:
            raise AgyWriteBoundaryError(
                f"{AGY_WRITE_BOUNDARY_UNAVAILABLE}:profile_unrepresentable"
            ) from exc
        profile_path = profile_dir / "agy-dispatch.sb"
        profile_path.write_text(profile, encoding="utf-8")
        run_tag = secrets.token_hex(16)
        env = agy_child_env(source_env, home=run_home, tmpdir=run_tmp)
        env[cli_worker.RUN_TAG_ENV] = run_tag
    except BaseException:
        shutil.rmtree(run_root, ignore_errors=True)
        shutil.rmtree(profile_dir, ignore_errors=True)
        raise
    return AgyDispatchBoundary(
        target=target_real,
        run_root=run_root,
        run_home=run_home,
        run_tmp=run_tmp,
        env=env,
        profile=profile,
        profile_path=profile_path,
        run_tag=run_tag,
        home_profile_sha256=home_profile_sha256,
        keychain_state=keychain_state,
    )
