"""Deterministic, dependency-free boundary for the Python OCI witness.

The product core does not start containers or acquire dependencies.  A
controller supplies an injected ``executor`` implementing that effect.  This
module validates its result, binds it to the exact request/profile, and runs
the same request twice before returning a certifiable result.
"""

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Mapping, Optional

IMAGE = "python:3.12-alpine"
IMAGE_DIGEST = "sha256:d09d15e60962ca365d1cd544a48773bac9d33f2fb1b00f2aa0deec78ade7dc31"
LOCK_DIGEST = "sha256:3e753af334885a2f434a94d40fc8860abd151516950e7f1e3647971f2e0dfc51"
PROFILE_ID = "python-oci-pytest-v1"


def _digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _text(value: str, field: str) -> None:
    if type(value) is not str or not value or value != value.strip() or "\x00" in value:
        raise ValueError(f"{field} must be a normalized non-empty string")


def _hash(value: str, field: str) -> None:
    _text(value, field)
    if len(value) != 71 or not value.startswith("sha256:") or any(
        c not in "0123456789abcdef" for c in value[7:]
    ):
        raise ValueError(f"{field} must be sha256:<64 lowercase hex>")


class RunnerStatus(str, Enum):
    VERIFIED = "VERIFIED"
    FAILED_VERIFICATION = "FAILED_VERIFICATION"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class PythonOCIProfile:
    profile_id: str = PROFILE_ID
    image: str = IMAGE
    image_digest: str = IMAGE_DIGEST
    lock_digest: str = LOCK_DIGEST
    network: str = "none"
    rootfs: str = "read-only"
    command: tuple[str, ...] = ("python", "-m", "pytest", "--junitxml=/evidence/junit.xml")
    timeout_seconds: int = 300
    memory_bytes: int = 1_073_741_824
    cpu_seconds: int = 60

    def __post_init__(self):
        _text(self.profile_id, "profile_id")
        _text(self.image, "image")
        _hash(self.image_digest, "image_digest")
        _hash(self.lock_digest, "lock_digest")
        if self.network != "none" or self.rootfs != "read-only":
            raise ValueError("profile must disable network and use a read-only rootfs")
        if type(self.command) is not tuple or not self.command or any(
            type(part) is not str or not part for part in self.command
        ):
            raise ValueError("command must be a non-empty argv tuple")
        if any(part in {"sh", "bash", "-c", "--command"} for part in self.command):
            raise ValueError("shell invocation is forbidden")
        if self.timeout_seconds <= 0 or self.memory_bytes <= 0 or self.cpu_seconds <= 0:
            raise ValueError("resource limits must be positive")

    @property
    def hash(self) -> str:
        body = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":")).encode()
        return _digest(body)

    def to_dict(self) -> dict:
        return {
            "profile_id": self.profile_id, "image": self.image,
            "image_digest": self.image_digest, "lock_digest": self.lock_digest,
            "network": self.network, "rootfs": self.rootfs,
            "command": list(self.command), "timeout_seconds": self.timeout_seconds,
            "memory_bytes": self.memory_bytes, "cpu_seconds": self.cpu_seconds,
        }


@dataclass(frozen=True)
class ExecutionAttempt:
    attempt_id: str
    source_revision: str
    source_tree: str
    contract_hash: str
    plan_hash: str
    environment_hash: str
    argv: tuple[str, ...]
    stdout: bytes
    stderr: bytes
    exit_code: int
    junit: bytes
    artifact_hash: str


@dataclass(frozen=True)
class RunnerResult:
    status: RunnerStatus
    reason_codes: tuple[str, ...]
    profile_hash: str
    attempt_ids: tuple[str, ...]
    artifact_hashes: tuple[str, ...]
    attempts: tuple[ExecutionAttempt, ...]


class PythonOCIRunner:
    """Validate two fresh injected OCI executions and protect exact replay."""

    def __init__(self, profile: Optional[PythonOCIProfile] = None):
        self.profile = profile or PythonOCIProfile()
        self._replay: dict[str, RunnerResult] = {}

    def run(self, request: Mapping[str, object], executor: Callable[..., Mapping[str, object]]) -> RunnerResult:
        required = ("source_revision", "source_tree", "contract_hash", "plan_hash", "environment_hash", "attempt_id")
        if any(key not in request for key in required):
            return self._unknown(("MISSING_BINDING",))
        try:
            for key in required[:-1]:
                _text(str(request[key]), key)
            for key in ("contract_hash", "plan_hash", "environment_hash"):
                _hash(str(request[key]), key)
            _text(str(request["attempt_id"]), "attempt_id")
            key = self._request_key(request)
        except (TypeError, ValueError):
            return self._unknown(("MALFORMED_REQUEST",))
        if key in self._replay:
            return self._replay[key]
        attempts = []
        for index in (1, 2):
            try:
                raw = executor(self.profile, request, index)
                attempt = self._attempt(raw, request, index)
            except (TypeError, ValueError, KeyError, ET.ParseError):
                result = self._unknown(("MALFORMED_OR_UNAVAILABLE",))
                self._replay[key] = result
                return result
            attempts.append(attempt)
        if attempts[0].artifact_hash != attempts[1].artifact_hash:
            result = self._result(RunnerStatus.UNVERIFIABLE, ("NONDETERMINISTIC",), attempts)
        elif attempts[0].exit_code == 0:
            result = self._result(RunnerStatus.VERIFIED, (), attempts)
        else:
            result = self._result(RunnerStatus.FAILED_VERIFICATION, ("TEST_FAILURE",), attempts)
        self._replay[key] = result
        return result

    def _attempt(self, raw: Mapping[str, object], request: Mapping[str, object], index: int) -> ExecutionAttempt:
        stdout = raw.get("stdout", b"")
        stderr = raw.get("stderr", b"")
        junit = raw.get("junit", b"")
        if not all(isinstance(value, bytes) for value in (stdout, stderr, junit)):
            raise ValueError("execution streams must be bytes")
        argv = tuple(raw.get("argv", self.profile.command))
        if argv != self.profile.command:
            raise ValueError("unexpected argv")
        exit_code = raw.get("exit_code")
        if type(exit_code) is not int:
            raise ValueError("missing exit code")
        self._check_junit(junit, exit_code)
        attempt_id = str(request["attempt_id"]) + f"-{index}"
        artifact = _digest(b"\0".join((stdout, stderr, junit)))
        return ExecutionAttempt(attempt_id, str(request["source_revision"]), str(request["source_tree"]), str(request["contract_hash"]), str(request["plan_hash"]), str(request["environment_hash"]), argv, stdout, stderr, exit_code, junit, artifact)

    @staticmethod
    def _check_junit(data: bytes, exit_code: int) -> None:
        if not data:
            raise ValueError("missing junit oracle")
        root = ET.fromstring(data)
        tests = int(root.attrib.get("tests", "0"))
        failures = int(root.attrib.get("failures", "0")) + int(root.attrib.get("errors", "0"))
        if tests <= 0 or (exit_code == 0 and failures):
            raise ValueError("inadequate junit oracle")

    def _request_key(self, request: Mapping[str, object]) -> str:
        body = {key: str(request[key]) for key in ("source_revision", "source_tree", "contract_hash", "plan_hash", "environment_hash", "attempt_id")}
        return _digest(json.dumps(body, sort_keys=True, separators=(",", ":")).encode())

    def _unknown(self, reasons: tuple[str, ...]) -> RunnerResult:
        return RunnerResult(RunnerStatus.UNVERIFIABLE, tuple(sorted(reasons)), self.profile.hash, (), (), ())

    def _result(self, status, reasons, attempts):
        return RunnerResult(status, tuple(sorted(reasons)), self.profile.hash, tuple(a.attempt_id for a in attempts), tuple(a.artifact_hash for a in attempts), tuple(attempts))
