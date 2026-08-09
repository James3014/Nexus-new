import hashlib
import json
import os
import stat
import sys
import tempfile
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator

from nexus.services.local_heal.context import HealContext
from nexus.services.local_heal.evaluation_gate import EvaluationGate
from nexus.services.local_heal.interface import (
    IPhase,
    PhaseResult,
    VerificationInput,
    VerificationOutput,
)
from nexus.services.local_heal.isolated_verifier import (
    IsolatedVerifierReceipt,
    IsolatedVerifierRequest,
    run_isolated_verifier,
)


@dataclass(frozen=True)
class OracleMaterialPaths:
    oracle_path: Path
    source_path: Path
    suite_path: Path


@dataclass(frozen=True)
class FrozenOracleIdentity:
    command: tuple[str, ...]
    oracle_path: str
    oracle_bytes: bytes
    material_paths: tuple[str, str, str]
    material_sha256: tuple[str, str, str]
    oracle_sha256: str


@dataclass(frozen=True)
class SameOracleVerificationResult:
    eligible: bool
    reason_code: str
    oracle_sha256: str
    base_receipt: IsolatedVerifierReceipt | None = None
    candidate_receipt: IsolatedVerifierReceipt | None = None


class _OracleMaterialError(ValueError):
    pass


@dataclass(frozen=True)
class _HeldFile:
    path: Path
    descriptor: int
    file_id: tuple[int, int]
    snapshot: bytes


@dataclass(frozen=True)
class _HeldWorkspace:
    path: Path
    descriptor: int
    file_id: tuple[int, int]


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _identity_hash(
    command: tuple[str, ...],
    paths: tuple[str, str, str],
    hashes: tuple[str, str, str],
) -> str:
    payload = json.dumps(
        {"command": list(command), "paths": paths, "hashes": hashes},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return _sha256(payload)


def _read_descriptor(descriptor: int) -> bytes:
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks = []
    while chunk := os.read(descriptor, 64 * 1024):
        chunks.append(chunk)
    return b"".join(chunks)


@contextmanager
def _hold_regular_file(path: Path) -> Iterator[_HeldFile]:
    try:
        path = Path(path)
        if path.is_symlink():
            raise _OracleMaterialError("MATERIAL_SYMLINK")
        resolved = path.resolve(strict=True)
        descriptor = os.open(
            resolved,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
    except _OracleMaterialError:
        raise
    except (OSError, TypeError, ValueError) as exc:
        raise _OracleMaterialError("MATERIAL_UNAVAILABLE") from exc
    try:
        try:
            metadata = os.fstat(descriptor)
            current = os.stat(resolved, follow_symlinks=False)
            if not stat.S_ISREG(metadata.st_mode):
                raise _OracleMaterialError("MATERIAL_NOT_REGULAR")
            if (metadata.st_dev, metadata.st_ino) != (current.st_dev, current.st_ino):
                raise _OracleMaterialError("MATERIAL_IDENTITY_DRIFT")
            snapshot = _read_descriptor(descriptor)
        except OSError as exc:
            raise _OracleMaterialError("MATERIAL_UNAVAILABLE") from exc
        yield _HeldFile(resolved, descriptor, (metadata.st_dev, metadata.st_ino), snapshot)
    finally:
        os.close(descriptor)


@contextmanager
def _hold_materials(
    material: OracleMaterialPaths,
) -> Iterator[tuple[_HeldFile, _HeldFile, _HeldFile]]:
    with ExitStack() as stack:
        held = tuple(
            stack.enter_context(_hold_regular_file(path))
            for path in (
                material.oracle_path,
                material.source_path,
                material.suite_path,
            )
        )
        if len({item.file_id for item in held}) != 3:
            raise _OracleMaterialError("MATERIAL_NOT_DISTINCT")
        yield held


def _command_error(command: tuple[str, ...], oracle: _HeldFile) -> str:
    if (
        type(command) is not tuple
        or len(command) < 2
        or any(type(part) is not str or not part for part in command)
    ):
        return "COMMAND_FORM_INVALID"
    if oracle.path.suffix != ".py":
        return "ORACLE_NOT_PYTHON"
    if any(argument.startswith("-") or not argument.isprintable() for argument in command[2:]):
        return "LITERAL_ARG_INVALID"
    executable = Path(command[0])
    try:
        resolved = executable.resolve(strict=True)
        trusted = Path(sys.executable).resolve(strict=True)
        metadata = os.stat(executable, follow_symlinks=False)
    except (OSError, ValueError):
        return "COMMAND_FORM_INVALID"
    if (
        executable.is_symlink()
        or executable != resolved
        or executable != trusted
        or not stat.S_ISREG(metadata.st_mode)
        or command[1] != str(oracle.path)
        or command.count(str(oracle.path)) != 1
    ):
        return "COMMAND_FORM_INVALID"
    return ""


def _make_identity(
    command: tuple[str, ...],
    held: tuple[_HeldFile, _HeldFile, _HeldFile],
) -> FrozenOracleIdentity:
    reason = _command_error(command, held[0])
    if reason:
        raise _OracleMaterialError(reason)
    paths = tuple(str(item.path) for item in held)
    hashes = tuple(_sha256(item.snapshot) for item in held)
    return FrozenOracleIdentity(
        command=command,
        oracle_path=paths[0],
        oracle_bytes=held[0].snapshot,
        material_paths=paths,
        material_sha256=hashes,
        oracle_sha256=_identity_hash(command, paths, hashes),
    )


def freeze_oracle_identity(
    *,
    command: tuple[str, ...],
    material: OracleMaterialPaths,
) -> FrozenOracleIdentity:
    """Freeze exact structured command and descriptor-held material snapshots."""
    if type(material) is not OracleMaterialPaths:
        raise TypeError("oracle_material_paths_required")
    with _hold_materials(material) as held:
        return _make_identity(command, held)


def _result(
    frozen: FrozenOracleIdentity,
    reason_code: str,
    *,
    eligible: bool = False,
    base_receipt: IsolatedVerifierReceipt | None = None,
    candidate_receipt: IsolatedVerifierReceipt | None = None,
) -> SameOracleVerificationResult:
    return SameOracleVerificationResult(
        eligible,
        reason_code,
        frozen.oracle_sha256,
        base_receipt,
        candidate_receipt,
    )


def _frozen_error(frozen: FrozenOracleIdentity) -> str:
    if (
        type(frozen.command) is not tuple
        or len(frozen.command) < 2
        or any(type(part) is not str or not part for part in frozen.command)
        or type(frozen.oracle_bytes) is not bytes
        or type(frozen.material_paths) is not tuple
        or len(frozen.material_paths) != 3
        or type(frozen.material_sha256) is not tuple
        or len(frozen.material_sha256) != 3
        or frozen.oracle_path != frozen.material_paths[0]
        or any(type(path) is not str or not path for path in frozen.material_paths)
        or any(type(value) is not str or len(value) != 64 for value in frozen.material_sha256)
    ):
        return "FROZEN_ORACLE_INCOMPLETE"
    if _sha256(frozen.oracle_bytes) != frozen.material_sha256[0]:
        return "FROZEN_ORACLE_BYTES_HASH_MISMATCH"
    if frozen.oracle_sha256 != _identity_hash(
        frozen.command, frozen.material_paths, frozen.material_sha256
    ):
        return "FROZEN_ORACLE_HASH_MISMATCH"
    return ""


def _refresh(item: _HeldFile) -> tuple[bytes | None, str]:
    try:
        if item.path.is_symlink():
            return None, "MATERIAL_SYMLINK"
        metadata = os.stat(item.path, follow_symlinks=False)
        if not stat.S_ISREG(metadata.st_mode) or (metadata.st_dev, metadata.st_ino) != item.file_id:
            return None, "MATERIAL_IDENTITY_DRIFT"
        return _read_descriptor(item.descriptor), ""
    except OSError:
        return None, "MATERIAL_UNAVAILABLE"


def _observe(
    frozen: FrozenOracleIdentity,
    request: IsolatedVerifierRequest,
    held: tuple[_HeldFile, _HeldFile, _HeldFile],
    prefix: str,
) -> str:
    reason = _command_error(request.verifier_command, held[0])
    if reason:
        return f"{prefix}_{reason}"
    snapshots = []
    for item in held:
        snapshot, reason = _refresh(item)
        if reason:
            return f"{prefix}_{reason}"
        snapshots.append(snapshot)
    paths = tuple(str(item.path) for item in held)
    hashes = tuple(_sha256(snapshot) for snapshot in snapshots)
    comparisons = (
        (request.verifier_command, frozen.command, "COMMAND_DRIFT"),
        (paths[0], frozen.material_paths[0], "ORACLE_PATH_DRIFT"),
        (hashes[0], frozen.material_sha256[0], "CONTENT_DRIFT"),
        (paths[1], frozen.material_paths[1], "SOURCE_IDENTITY_DRIFT"),
        (hashes[1], frozen.material_sha256[1], "SOURCE_HASH_DRIFT"),
        (paths[2], frozen.material_paths[2], "SUITE_IDENTITY_DRIFT"),
        (hashes[2], frozen.material_sha256[2], "SUITE_HASH_DRIFT"),
    )
    for actual, expected, drift in comparisons:
        if actual != expected:
            return f"{prefix}_{drift}"
    return ""


@contextmanager
def _hold_workspace(path: str) -> Iterator[_HeldWorkspace]:
    try:
        requested = Path(path)
        if requested.is_symlink():
            raise _OracleMaterialError("WORKSPACE_SYMLINK")
        workspace = requested.resolve(strict=True)
        descriptor = os.open(
            workspace,
            os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
        )
    except _OracleMaterialError:
        raise
    except (OSError, TypeError, ValueError):
        raise _OracleMaterialError("WORKSPACE_UNAVAILABLE") from None
    try:
        try:
            metadata = os.fstat(descriptor)
            current = os.stat(workspace, follow_symlinks=False)
            if not stat.S_ISDIR(metadata.st_mode):
                raise _OracleMaterialError("WORKSPACE_NOT_DIRECTORY")
            if (metadata.st_dev, metadata.st_ino) != (current.st_dev, current.st_ino):
                raise _OracleMaterialError("WORKSPACE_IDENTITY_DRIFT")
        except OSError as exc:
            raise _OracleMaterialError("WORKSPACE_UNAVAILABLE") from exc
        yield _HeldWorkspace(
            workspace,
            descriptor,
            (metadata.st_dev, metadata.st_ino),
        )
    finally:
        os.close(descriptor)


def _workspace_error(workspace: _HeldWorkspace, prefix: str) -> str:
    try:
        held = os.fstat(workspace.descriptor)
        current = os.stat(workspace.path, follow_symlinks=False)
    except OSError:
        return f"{prefix}_WORKSPACE_UNAVAILABLE"
    identity = (held.st_dev, held.st_ino), (current.st_dev, current.st_ino)
    if not stat.S_ISDIR(current.st_mode) or identity != (workspace.file_id,) * 2:
        return f"{prefix}_WORKSPACE_IDENTITY_DRIFT"
    return ""


def _receipt_error(
    receipt: object,
    request: IsolatedVerifierRequest,
    prefix: str,
) -> str:
    if type(receipt) is not IsolatedVerifierReceipt:
        return f"{prefix}_RECEIPT_TYPE_INVALID"
    if receipt.task_id != request.task_id:
        return f"{prefix}_RECEIPT_TASK_ID_MISMATCH"
    if receipt.verifier_allowed is not True:
        return f"{prefix}_RECEIPT_NOT_ALLOWED"
    if (
        type(receipt.stdout_tail) is not str
        or type(receipt.stderr_tail) is not str
        or type(receipt.verifier_error) is not str
    ):
        return f"{prefix}_RECEIPT_INCOHERENT"
    exit_code = receipt.exit_code
    coherent = (
        (
            receipt.verifier_status == "pass"
            and type(exit_code) is int
            and exit_code == 0
            and not receipt.verifier_error
        )
        or (
            receipt.verifier_status == "fail"
            and type(exit_code) is int
            and exit_code != 0
            and not receipt.verifier_error
        )
        or (
            receipt.verifier_status == "blocked"
            and exit_code is None
            and bool(receipt.verifier_error)
        )
    )
    return "" if coherent else f"{prefix}_RECEIPT_INCOHERENT"


def _sealed_error(sealed: _HeldFile, frozen: FrozenOracleIdentity, prefix: str) -> str:
    content, reason = _refresh(sealed)
    if reason:
        return f"{prefix}_SEALED_ORACLE_INVALID"
    if content != frozen.oracle_bytes or _sha256(content) != frozen.material_sha256[0]:
        return f"{prefix}_SEALED_ORACLE_TAMPERED"
    return ""


def _sealed_request(
    request: IsolatedVerifierRequest,
    sealed_path: Path,
    workspace: _HeldWorkspace,
) -> IsolatedVerifierRequest:
    command = (request.verifier_command[0], str(sealed_path), *request.verifier_command[2:])
    return replace(
        request,
        workspace_path=str(workspace.path),
        verifier_command=command,
    )


@contextmanager
def _sealed_copy(content: bytes) -> Iterator[_HeldFile]:
    with tempfile.TemporaryDirectory(prefix="nexus-g2-oracle-") as directory:
        path = Path(directory) / "frozen_oracle.py"
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            stat.S_IRUSR | stat.S_IWUSR,
        )
        try:
            remaining = memoryview(content)
            while remaining:
                remaining = remaining[os.write(descriptor, remaining) :]
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        path.chmod(stat.S_IRUSR)
        with _hold_regular_file(path) as sealed:
            yield sealed


def _execute(
    frozen: FrozenOracleIdentity,
    identity_request: IsolatedVerifierRequest,
    execution_request: IsolatedVerifierRequest,
    held: tuple[_HeldFile, _HeldFile, _HeldFile],
    sealed: _HeldFile,
    workspace: _HeldWorkspace,
    prefix: str,
) -> tuple[IsolatedVerifierReceipt | None, str]:
    reason = _workspace_error(workspace, f"{prefix}_PRE")
    if not reason:
        reason = _observe(frozen, identity_request, held, f"{prefix}_PRE")
    if not reason:
        reason = _sealed_error(sealed, frozen, f"{prefix}_PRE")
    if reason:
        return None, reason
    try:
        receipt = run_isolated_verifier(execution_request)
    except Exception:
        return None, f"{prefix}_VERIFIER_EXECUTION_ERROR"
    reason = _workspace_error(workspace, f"{prefix}_POST")
    if not reason:
        reason = _receipt_error(receipt, execution_request, prefix)
    if not reason:
        reason = _sealed_error(sealed, frozen, f"{prefix}_POST")
    if not reason:
        reason = _observe(frozen, identity_request, held, f"{prefix}_POST")
    return (receipt, reason) if not reason else (None, reason)


def run_frozen_same_oracle(
    *,
    frozen: FrozenOracleIdentity,
    base_request: IsolatedVerifierRequest | None,
    candidate_request: IsolatedVerifierRequest | None,
    base_material: OracleMaterialPaths | None,
    candidate_material: OracleMaterialPaths | None,
) -> SameOracleVerificationResult:
    """Prove a physical base FAIL and Candidate PASS under one frozen oracle."""
    if type(frozen) is not FrozenOracleIdentity:
        return SameOracleVerificationResult(False, "FROZEN_ORACLE_TYPE_INVALID", "")
    reason = _frozen_error(frozen)
    if reason:
        return _result(frozen, reason)
    required = (
        (base_request, IsolatedVerifierRequest, "BASE_REQUEST"),
        (candidate_request, IsolatedVerifierRequest, "CANDIDATE_REQUEST"),
        (base_material, OracleMaterialPaths, "BASE_MATERIAL"),
        (candidate_material, OracleMaterialPaths, "CANDIDATE_MATERIAL"),
    )
    for value, expected_type, label in required:
        if value is None:
            return _result(frozen, f"MISSING_{label}")
        if type(value) is not expected_type:
            return _result(frozen, f"{label}_TYPE_INVALID")
    assert base_request is not None and candidate_request is not None
    assert base_material is not None and candidate_material is not None
    if type(base_request.task_id) is not str or not base_request.task_id:
        return _result(frozen, "BASE_TASK_ID_MISSING")
    if type(candidate_request.task_id) is not str or not candidate_request.task_id:
        return _result(frozen, "CANDIDATE_TASK_ID_MISSING")
    if base_request.task_id == candidate_request.task_id:
        return _result(frozen, "BASE_CANDIDATE_TASK_ID_NOT_DISTINCT")

    with ExitStack() as stack:
        try:
            base_workspace = stack.enter_context(_hold_workspace(base_request.workspace_path))
        except _OracleMaterialError as exc:
            return _result(frozen, f"BASE_{exc}")
        except OSError:
            return _result(frozen, "BASE_WORKSPACE_UNAVAILABLE")
        try:
            candidate_workspace = stack.enter_context(
                _hold_workspace(candidate_request.workspace_path)
            )
        except _OracleMaterialError as exc:
            return _result(frozen, f"CANDIDATE_{exc}")
        except OSError:
            return _result(frozen, "CANDIDATE_WORKSPACE_UNAVAILABLE")
        if base_workspace.file_id == candidate_workspace.file_id:
            return _result(frozen, "BASE_CANDIDATE_WORKSPACE_NOT_DISTINCT")

        try:
            base_held = stack.enter_context(_hold_materials(base_material))
        except _OracleMaterialError as exc:
            return _result(frozen, f"BASE_{exc}")
        try:
            candidate_held = stack.enter_context(_hold_materials(candidate_material))
        except _OracleMaterialError as exc:
            return _result(frozen, f"CANDIDATE_{exc}")
        for request, held, prefix in (
            (base_request, base_held, "BASE"),
            (candidate_request, candidate_held, "CANDIDATE"),
        ):
            reason = _observe(frozen, request, held, prefix)
            if reason:
                return _result(frozen, reason)

        try:
            with _sealed_copy(frozen.oracle_bytes) as sealed:
                base_execution = _sealed_request(base_request, sealed.path, base_workspace)
                candidate_execution = _sealed_request(
                    candidate_request,
                    sealed.path,
                    candidate_workspace,
                )
                base_receipt, reason = _execute(
                    frozen,
                    base_request,
                    base_execution,
                    base_held,
                    sealed,
                    base_workspace,
                    "BASE",
                )
                if reason:
                    return _result(frozen, reason)
                assert base_receipt is not None
                if base_receipt.verifier_status == "pass":
                    return _result(frozen, "BASE_ALREADY_PASS", base_receipt=base_receipt)
                if base_receipt.verifier_status != "fail":
                    return _result(frozen, "BASE_NOT_PHYSICAL_FAIL", base_receipt=base_receipt)

                candidate_receipt, reason = _execute(
                    frozen,
                    candidate_request,
                    candidate_execution,
                    candidate_held,
                    sealed,
                    candidate_workspace,
                    "CANDIDATE",
                )
                if reason:
                    return _result(frozen, reason, base_receipt=base_receipt)
                assert candidate_receipt is not None
                if candidate_receipt.verifier_status == "fail":
                    return _result(
                        frozen,
                        "CANDIDATE_FAIL",
                        base_receipt=base_receipt,
                        candidate_receipt=candidate_receipt,
                    )
                if candidate_receipt.verifier_status != "pass":
                    return _result(
                        frozen,
                        "CANDIDATE_NOT_PHYSICAL_PASS",
                        base_receipt=base_receipt,
                        candidate_receipt=candidate_receipt,
                    )
                return _result(
                    frozen,
                    "SAME_ORACLE_VERIFIED",
                    eligible=True,
                    base_receipt=base_receipt,
                    candidate_receipt=candidate_receipt,
                )
        except (_OracleMaterialError, OSError):
            return _result(frozen, "SEALED_ORACLE_UNAVAILABLE")


# fmt: off
class VerificationPhase(IPhase):
    """Phase 5: Verification (代數驗證)"""
    def __init__(self, eval_gate: EvaluationGate, hidden_required: bool = False):
        self.eval_gate = eval_gate
        self.hidden_required = hidden_required

    def run(self, input_data: VerificationInput) -> VerificationOutput:
        """Stateless TDD-ready execution logic."""
        if not input_data.final_patch:
            return VerificationOutput(
                success=False,
                evaluation_report="",
                hidden_verifier_passed=False,
                solve_eligible=False,
                error_reason="NO_PATCH_TO_VERIFY"
            )

        repro_path = input_data.repo_dir / "reproduce_bug.py"
        wrote_repro_script = bool(input_data.repro_script)
        if wrote_repro_script:
            repro_path.write_text(input_data.repro_script, encoding="utf-8")

        try:
            verification_python = input_data.python_executable or "python3"
            verifier_command = list(input_data.verifier_command or [])
            if verifier_command:
                if (
                    input_data.python_executable
                    and verifier_command[0] in {"python", "python3"}
                ):
                    verifier_command[0] = verification_python
                visible_cmds = [verifier_command]
            else:
                visible_cmds = [[verification_python, "reproduce_bug.py"]]

            visible_results = self.eval_gate.run_visible_tests(visible_cmds)
            hidden_results = []
            if self.hidden_required:
                hidden_results = self.eval_gate.run_hidden_verifier([])

            passed = all(r.passed for r in visible_results + hidden_results)
            report = self.eval_gate.get_redacted_report(visible_results, hidden_results)

            if passed:
                return VerificationOutput(
                    success=True,
                    evaluation_report=report,
                    hidden_verifier_passed=True,
                    solve_eligible=True
                )
            else:
                return VerificationOutput(
                    success=False,
                    evaluation_report=report,
                    hidden_verifier_passed=False,
                    solve_eligible=False,
                    error_reason="VERIFICATION_FAILED"
                )
        finally:
            if wrote_repro_script and repro_path.exists():
                try:
                    os.remove(repro_path)
                except OSError:
                    pass

    def execute(self, ctx: HealContext) -> PhaseResult:
        route_ctx = ctx.op.route_context if isinstance(ctx.op.route_context, dict) else {}
        verifier_command = tuple(route_ctx.get("verifier_command", []) or []) if isinstance(route_ctx, dict) else ()

        input_data = VerificationInput(
            instance_id=ctx.op.instance_id,
            repo_dir=ctx.op.repo_dir,
            problem_statement=ctx.op.problem_statement,
            final_patch=ctx.op.final_patch,
            repro_script=ctx.op.repro_script,
            python_executable=ctx.op.python_executable,
            verifier_command=verifier_command,
        )

        output = self.run(input_data)
        
        ctx.op.evaluation_report = output.evaluation_report
        ctx.op.hidden_verifier_passed = output.hidden_verifier_passed
        ctx.op.solve_eligible = output.solve_eligible
        ctx.op.verifier_command_present = bool(verifier_command)
        ctx.op.verifier_command_source = "route_context" if verifier_command else ""
        
        if not output.success:
            ctx.op.failure_reason = output.failure_reason
            return PhaseResult(success=False, exit_layer="verification", failure_reason=output.failure_reason)

        ctx.op.failure_reason = ""
        return PhaseResult(success=True)
# fmt: on
