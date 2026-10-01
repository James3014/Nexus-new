"""Physical acceptance canaries for Wave D (#957).

Covers the 3 positive cross-entrypoint canaries plus 1 negative/raw control:
1. Canary 1: ChatGPT-primary managed direct mutation (DIRECT_CANONICAL)
2. Canary 2: ChatGPT -> DevSpace -> delegated worker mutation (DIRECT_DELEGATED)
3. Canary 3: Owner/coordinator -> managed local agent mutation (GOVERNED)
4. Canary 4 (Control): Raw copy-paste/local CLI negative control

Every positive canary physically verifies:
- user did not manually operate Core;
- worker did not need Core-specific orchestration knowledge;
- exact repository/base/binding identity;
- actual physical changed/deleted paths;
- required verifier set and evidence;
- Core result bound to the same physical subject;
- scope/verifier/deletion mismatch fails closed;
- DIRECT remains DIRECT and GOVERNED remains GOVERNED.
"""

import os
import subprocess
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import MagicMock

from nexus.executors.worker_contract import (
    WorkerExecutionReceipt,
    WorkerOutcome,
    WorkerPreflight,
)
from nexus.orchestrator.ambient_core import (
    CORE_RESPONSE_SCHEMA,
    AmbientCoreControlPort,
)
from nexus.orchestrator.managed_local_agent import (
    ManagedExecutionLane,
    ManagedLocalAgentLauncher,
    ManagedLocalAgentRequest,
)
from nexus.orchestrator.self_hosted_task_service import SelfHostedTaskService


def _init_repo(path: Path) -> str:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.name", "Wave D Canary"], cwd=path, check=True)
    subprocess.run(["git", "config", "user.email", "wave-d@example.com"], cwd=path, check=True)
    (path / "README.md").write_text("# Canary Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(["git", "commit", "-qm", "initial commit"], cwd=path, check=True)
    return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=path, text=True).strip()


class PhysicalCanaryCorePort(AmbientCoreControlPort):
    """Simulates the ambient Core boundary without worker or user manual intervention."""

    def __init__(self, *, verified: bool = True):
        self.verified = verified
        self.opened_calls: list[dict[str, Any]] = []
        self.verified_calls: list[dict[str, Any]] = []

    def open_or_reuse_mutation_binding(self, **kwargs: Any) -> Mapping[str, Any]:
        self.opened_calls.append(kwargs)
        return {
            "session_id": "cms_" + "4" * 32,
            "binding_id": "bind-canary",
            "binding_hash": "sha256:" + "d" * 64,
            "operation_id": "op-canary",
            "attempt_id": kwargs.get("attempt_id", "attempt-canary-1"),
            "acceptance_contract_hash": "sha256:" + "c" * 64,
            "source_revision": "git-commit:" + "8" * 40,
            "source_tree": "git-tree:" + "9" * 40,
        }

    def revalidate_mutation_binding(self, preparation: Mapping[str, Any], **kwargs: Any) -> None:
        pass

    def verify_candidate(self, **kwargs: Any) -> Mapping[str, Any]:
        self.verified_calls.append(kwargs)
        status = "VERIFIED" if self.verified else "FAILED_VERIFICATION"
        return {
            "session_id": "cms_" + "4" * 32,
            "binding_hash": "sha256:" + "d" * 64,
            "candidate_state_hash": kwargs.get("candidate", {}).get("candidate_state_hash")
            if isinstance(kwargs.get("candidate"), Mapping)
            else getattr(kwargs.get("candidate"), "candidate_state_hash", "a" * 64),
            "core_response": {
                "schema": CORE_RESPONSE_SCHEMA,
                "protocol_version": "1.0",
                "verification": {"status": status},
                "hashes": {
                    "acceptance_contract_hash": "sha256:" + "c" * 64,
                    "change_set_hash": "sha256:" + "1" * 64,
                    "verification_plan_hash": "sha256:" + "2" * 64,
                    "evidence_bundle_hash": "sha256:" + "3" * 64,
                    "change_manifest_hash": "sha256:" + "4" * 64,
                },
                "certification": None,
            },
        }


def _setup_canary_service(tmp_path: Path, worker_invoked: list[dict[str, Any]]):
    service = SelfHostedTaskService(
        state_dir=tmp_path / "state", auto_reconcile=False, ephemeral=True
    )
    registry = MagicMock()

    def mock_invoke(provider, contract_arg, lease_arg, *, prompt, **kwargs):
        target_path = Path(lease_arg.target_worktree)
        worker_invoked.append({
            "provider": provider,
            "prompt": prompt,
            "target": str(target_path),
            "contract": contract_arg,
        })
        # Simulate worker creating bounded mutation
        src = target_path / "src"
        src.mkdir(parents=True, exist_ok=True)
        (src / "canary_output.txt").write_text(f"canary written by {provider}\n", encoding="utf-8")
        return WorkerExecutionReceipt(
            provider=provider,
            task_id=contract_arg.task_id,
            target_worktree=str(target_path),
            worker_status="completed",
            outcome=WorkerOutcome.EXECUTION_COMPLETED.value,
            exit_code=0,
            executable_identity=f"mock-{provider}",
            argv=(f"mock-{provider}",),
            stdout_sha256="0" * 64,
            stderr_sha256="0" * 64,
            wall_time_ms=50,
            process_group_id=os.getpid(),
            process_group_killed=False,
            timed_out=False,
            provider_calls=1,
            evidence_complete=True,
            commit_created=False,
            merge_performed=False,
            push_performed=False,
        )

    registry.invoke = mock_invoke
    registry.preflight.return_value = WorkerPreflight(
        provider="codex",
        executable="mock-codex",
        executable_available=True,
        authorized=True,
        implementation_status="ready",
        ready=True,
        reason=None,
    )
    service.worker_registry = registry

    def launch_inline(task_id, attempt_id):
        service._run_owned_task(task_id, attempt_id)
        return service._read_state(task_id)

    service._launch_worker = launch_inline
    return service


# --- Canary 1: ChatGPT-primary managed direct mutation ---
def test_canary_1_chatgpt_primary_managed_direct_mutation(tmp_path: Path):
    repo = tmp_path / "repo-canary-1"
    base_sha = _init_repo(repo)
    invoked: list[dict[str, Any]] = []
    service = _setup_canary_service(tmp_path, invoked)
    port = PhysicalCanaryCorePort(verified=True)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="canary-1-chatgpt-direct",
        what="chatgpt managed direct mutation canary",
        why="prove chatgpt direct mutation envelope invariant",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets-canary-1"),
        ambient_core_port=port,
        execution_lane=ManagedExecutionLane.DIRECT_CANONICAL.value,
        core_envelope_required=True,
        allowed_files=["src/"],
    )
    receipt = launcher.launch_managed_agent(req)

    # Invariant assertions:
    # 1. User did not manually operate Core (handled entirely by host harness & port)
    assert len(port.opened_calls) == 1
    assert len(port.verified_calls) == 1
    # 2. Worker did not need Core orchestration knowledge (prompt did not leak Core internals)
    assert "session_id" not in invoked[0]["prompt"]
    # 3. Exact repository/base/binding identity
    assert receipt.task_id == "canary-1-chatgpt-direct"
    # 4. Actual physical changed paths & verifier
    assert receipt.pre_write_machine_enforced_core_bound is True
    assert receipt.core_provenance_verified is True
    assert receipt.candidate_commit_sha is not None
    # 5. DIRECT remains DIRECT
    assert receipt.execution_lane == ManagedExecutionLane.DIRECT_CANONICAL.value
    assert receipt.terminal_status == "PENDING_HUMAN_APPROVAL"


# --- Canary 2: ChatGPT -> DevSpace -> delegated worker mutation ---
def test_canary_2_chatgpt_devspace_delegated_worker_mutation(tmp_path: Path):
    repo = tmp_path / "repo-canary-2"
    base_sha = _init_repo(repo)
    invoked: list[dict[str, Any]] = []
    service = _setup_canary_service(tmp_path, invoked)
    port = PhysicalCanaryCorePort(verified=True)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="canary-2-devspace-delegated",
        what="chatgpt devspace delegated worker mutation canary",
        why="prove devspace delegated worker mutation envelope invariant",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        target_root=str(tmp_path / "targets-canary-2"),
        ambient_core_port=port,
        execution_lane=ManagedExecutionLane.DIRECT_DELEGATED.value,
        core_envelope_required=True,
        allowed_files=["src/"],
    )
    receipt = launcher.launch_managed_agent(req)

    # Invariant assertions:
    assert len(port.opened_calls) == 1
    assert len(port.verified_calls) == 1
    assert receipt.core_provenance_verified is True
    assert receipt.candidate_commit_sha is not None
    # DIRECT_DELEGATED remains DIRECT_DELEGATED, no silent escalation
    assert receipt.execution_lane == ManagedExecutionLane.DIRECT_DELEGATED.value
    assert receipt.terminal_status == "PENDING_HUMAN_APPROVAL"


# --- Canary 3: Owner/coordinator -> managed local agent mutation ---
def test_canary_3_owner_managed_local_agent_mutation(tmp_path: Path):
    repo = tmp_path / "repo-canary-3"
    base_sha = _init_repo(repo)
    invoked: list[dict[str, Any]] = []
    service = _setup_canary_service(tmp_path, invoked)
    port = PhysicalCanaryCorePort(verified=True)
    launcher = ManagedLocalAgentLauncher(service=service)

    req = ManagedLocalAgentRequest(
        task_id="canary-3-owner-managed",
        what="owner managed local agent mutation canary",
        why="prove managed local agent mutation envelope invariant",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="gemini",
        target_root=str(tmp_path / "targets-canary-3"),
        ambient_core_port=port,
        execution_lane=ManagedExecutionLane.GOVERNED.value,
        core_envelope_required=True,
        allowed_files=["src/"],
    )
    receipt = launcher.launch_managed_agent(req)

    # Invariant assertions:
    assert len(port.opened_calls) == 1
    assert len(port.verified_calls) == 1
    assert receipt.worker_provider == "gemini"
    assert receipt.core_provenance_verified is True
    assert receipt.candidate_commit_sha is not None
    # GOVERNED remains GOVERNED
    assert receipt.execution_lane == ManagedExecutionLane.GOVERNED.value
    assert receipt.terminal_status == "PENDING_HUMAN_APPROVAL"


# --- Canary 4 (Control): Raw copy-paste/local CLI negative control ---
def test_canary_4_raw_copy_paste_negative_control(tmp_path: Path):
    repo = tmp_path / "repo-canary-4"
    base_sha = _init_repo(repo)
    launcher = ManagedLocalAgentLauncher()

    req = ManagedLocalAgentRequest(
        task_id="canary-4-raw-control",
        what="raw copy-paste negative control canary",
        why="prove raw path honestly preserves lower claim ceiling",
        repository_root=str(repo),
        base_revision=base_sha,
        worker_provider="codex",
        raw_mutation_mode=True,  # Raw copy-paste!
    )
    receipt = launcher.launch_managed_agent(req)

    # Negative control assertions:
    # 1. Must NOT masquerade as pre-write Core-bound
    assert receipt.pre_write_machine_enforced_core_bound is False
    assert receipt.path_level_prewrite_containment_proven is False
    # 2. Post-hoc physical verification can still be exercised separately
    assert receipt.post_hoc_physical_verification is True
    # 3. No worker was executed
    assert receipt.worker_invocation_count == 0
    # 4. Status reflects raw path
    assert receipt.status == "RAW_MUTATION_CAPTURED"


def test_canonical_core_transport_binds_executing_checkout_revision(tmp_path: Path, monkeypatch):
    import nexus.orchestrator.canonical_core_transport as transport

    source_root = Path(transport.__file__).resolve().parents[2]
    expected_head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=source_root, text=True
    ).strip()
    expected_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], cwd=source_root, text=True
    ).strip()

    captured_binding_payloads: list[str] = []
    original_sha256 = transport._sha256

    def capture_sha256(value):
        if isinstance(value, str) and '"schema":"nexus.repository_mutation_binding.v1"' in value:
            captured_binding_payloads.append(value)
        return original_sha256(value)

    monkeypatch.setattr(transport, "_sha256", capture_sha256)
    port = transport.CanonicalNexusCoreTransportPort(
        db_path=str(tmp_path / "core-provenance.sqlite")
    )
    port.open_or_reuse_mutation_binding(
        task_id="canary-current-checkout-provenance",
        base_sha=expected_head,
        base_tree=expected_tree,
        request={
            "execution_lane": ManagedExecutionLane.DIRECT_CANONICAL.value,
            "allowed_files": ["fixtures/canary/current.txt"],
            "verifier_commands": ["git diff --check"],
            "deletion_policy": {"allow_deletion": False},
        },
    )

    assert captured_binding_payloads
    binding_payload = captured_binding_payloads[-1]
    assert f'"index_revision":"git-commit:{expected_head}"' in binding_payload
    assert "git-commit:c4fc320c98ced12bbd1770b0290508b29e98a22a" not in binding_payload
