"""Deterministic tests for multi-account parallel dispatch and failover.

The suite covers exclusive cross-process leasing, bounded pool-busy behavior,
failure-aware rotation, durable quarantine, permission restoration, privacy, and
CLI timeout handling.
"""

from __future__ import annotations

import fcntl
import json
import os
import shutil
import tempfile
import threading
import time
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path

from nexus.services.agy_account_pool import (
    AgyAccount,
    AgyAccountPoolBusyError,
    AgyAccountPoolExhaustedError,
    AgyAccountPoolManager,
    AgyAccountPoolManagerError,
    CrossProcessLeaseCoordinator,
)
from nexus.services.external_account_pool import (
    AccountFailureKind,
    is_rotation_eligible,
)

_SNAPSHOT = Path(__file__).resolve().parent.parent.parent

# Load helper functions only from the canonical tracked dispatch source.
CANONICAL_DISPATCH_PATH = _SNAPSHOT / "scripts" / "ops" / "nexus-agy-dispatch"
os.environ["NEXUS_AGY_SNAPSHOT"] = str(_SNAPSHOT)
dispatch_module = (
    SourceFileLoader("nexus_agy_dispatch", str(CANONICAL_DISPATCH_PATH)).load_module()
    if CANONICAL_DISPATCH_PATH.is_file()
    else None
)


class TestAccountConcurrencyModel(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp(prefix="test_agy_concurrency_")
        self.allocator_lock_path = Path(self.test_dir) / "allocator.lock"
        self.leases_dir = Path(self.test_dir) / "leases"

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_manager(self, accounts: list[AgyAccount]) -> AgyAccountPoolManager:
        return AgyAccountPoolManager(accounts=accounts, use_real_manager=False)

    def _create_coordinator(
        self, manager: AgyAccountPoolManager, poll_interval: float = 0.05, timeout: float = 2.0
    ) -> CrossProcessLeaseCoordinator:
        return CrossProcessLeaseCoordinator(
            manager=manager,
            allocator_lock_path=self.allocator_lock_path,
            leases_dir=self.leases_dir,
            poll_interval=poll_interval,
            default_wait_timeout=timeout,
        )

    def test_a_two_healthy_accounts_simultaneous_different_hashes(self):
        """A. two healthy accounts -> two simultaneous dispatch claims -> different account_alias_hash"""
        acc1 = AgyAccount(alias="acc_alpha", home_dir=f"{self.test_dir}/home_alpha")
        acc2 = AgyAccount(alias="acc_beta", home_dir=f"{self.test_dir}/home_beta")

        mgr1 = self._create_manager([acc1, acc2])
        mgr2 = self._create_manager([acc1, acc2])
        coord1 = self._create_coordinator(mgr1)
        coord2 = self._create_coordinator(mgr2)

        claim1 = coord1.acquire_claim("worker-1")
        claim2 = coord2.acquire_claim("worker-2")

        try:
            self.assertIsNotNone(claim1)
            self.assertIsNotNone(claim2)
            self.assertNotEqual(claim1.account_alias_hash, claim2.account_alias_hash)
            # Both per-account lock files exist and are locked
            self.assertTrue(claim1.lock_path.exists())
            self.assertTrue(claim2.lock_path.exists())
            self.assertTrue(claim1.receipt_path.exists())
            self.assertTrue(claim2.receipt_path.exists())

            # Attempting non-blocking lock from outside on either must fail with BlockingIOError
            with open(claim1.lock_path, "a+") as f:
                with self.assertRaises((BlockingIOError, OSError)):
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            with open(claim2.lock_path, "a+") as f:
                with self.assertRaises((BlockingIOError, OSError)):
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            claim1.release()
            claim2.release()

    def test_b_one_healthy_account_second_cannot_claim_same_account(self):
        """B. one healthy account -> second concurrent dispatch cannot claim same account"""
        acc1 = AgyAccount(alias="acc_solo", home_dir=f"{self.test_dir}/home_solo")

        mgr1 = self._create_manager([acc1])
        mgr2 = self._create_manager([acc1])
        coord1 = self._create_coordinator(mgr1)
        coord2 = self._create_coordinator(mgr2)

        claim1 = coord1.acquire_claim("worker-1")
        self.assertIsNotNone(claim1)

        try:
            with self.assertRaises(AgyAccountPoolBusyError):
                coord2.acquire_claim("worker-2", wait_timeout=0.1)
        finally:
            claim1.release()

    def test_c_worker_a_release_waiting_worker_b_claims(self):
        """C. worker A release -> waiting worker B can claim released account"""
        acc1 = AgyAccount(alias="acc_shared", home_dir=f"{self.test_dir}/home_shared")

        mgr1 = self._create_manager([acc1])
        mgr2 = self._create_manager([acc1])
        coord1 = self._create_coordinator(mgr1)
        coord2 = self._create_coordinator(mgr2)

        claim1 = coord1.acquire_claim("worker-1")

        worker_b_claim = []
        worker_b_err = []

        def worker_b_target():
            try:
                c2 = coord2.acquire_claim("worker-2", wait_timeout=2.0)
                worker_b_claim.append(c2)
            except Exception as e:
                worker_b_err.append(e)

        t = threading.Thread(target=worker_b_target)
        t.start()

        # Give worker B a moment to enter wait loop
        time.sleep(0.1)
        self.assertEqual(len(worker_b_claim), 0)

        # Release worker A's claim
        claim1.release()

        # Worker B should acquire the freed account
        t.join(timeout=3.0)
        self.assertEqual(len(worker_b_err), 0)
        self.assertEqual(len(worker_b_claim), 1)

        c2 = worker_b_claim[0]
        try:
            self.assertEqual(c2.account_alias_hash, acc1.alias_hash)
        finally:
            c2.release()

    def test_d_temporary_permission_lifecycle_restored_before_release(self):
        """D. temporary permission lifecycle -> permissions restored before account lease release"""
        if not dispatch_module:
            self.skipTest("dispatch_module not loaded")

        home_dir = Path(self.test_dir) / "home_perms"
        home_dir.mkdir(parents=True, exist_ok=True)
        acc = AgyAccount(alias="acc_perms", home_dir=str(home_dir))

        mgr = self._create_manager([acc])
        coord = self._create_coordinator(mgr)

        claim = coord.acquire_claim("worker-perms")
        env = dict(claim.lease.execution_env)

        settings_path = home_dir / ".gemini" / "antigravity-cli" / "settings.json"
        self.assertFalse(settings_path.exists())

        # Step 1: Install temp permissions while holding lease
        token = dispatch_module.install_temp_permissions(
            env,
            allow_rules=["command(*)"],
            deny_rules=dispatch_module.TEMP_COMMAND_DENY,
            allow_unsafe_legacy=True,
        )
        self.assertTrue(settings_path.exists())
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        self.assertIn("command(*)", data["permissions"]["allow"])
        self.assertIn("command(git push)", data["permissions"]["deny"])

        # Step 2: Restore temp permissions BEFORE releasing account lock
        dispatch_module.restore_temp_permissions(token)
        self.assertFalse(settings_path.exists())

        # Step 3: Release account claim
        claim.release()
        self.assertTrue(claim.released)

    def test_e_exception_account_lock_released(self):
        """E. exception -> account lock released"""
        acc = AgyAccount(alias="acc_exc", home_dir=f"{self.test_dir}/home_exc")
        mgr1 = self._create_manager([acc])
        mgr2 = self._create_manager([acc])
        coord1 = self._create_coordinator(mgr1)
        coord2 = self._create_coordinator(mgr2)

        try:
            claim1 = coord1.acquire_claim("worker-1")
            try:
                # Simulate work that crashes with an exception
                raise RuntimeError("WORKER_UNEXPECTED_CRASH")
            finally:
                claim1.release()
        except RuntimeError:
            pass

        # Another worker should be able to acquire the account immediately
        claim2 = coord2.acquire_claim("worker-2", wait_timeout=0.1)
        self.assertIsNotNone(claim2)
        claim2.release()

    def test_f_timeout_account_lock_released(self):
        """F. timeout -> account lock released"""
        acc = AgyAccount(alias="acc_timeout", home_dir=f"{self.test_dir}/home_timeout")
        mgr1 = self._create_manager([acc])
        mgr2 = self._create_manager([acc])
        coord1 = self._create_coordinator(mgr1)
        coord2 = self._create_coordinator(mgr2)

        claim1 = coord1.acquire_claim("worker-1")
        try:
            # Simulate timeout failure classification
            failure_kind = AccountFailureKind.TIMEOUT
            self.assertFalse(is_rotation_eligible(failure_kind))
        finally:
            claim1.release()

        # Account lock is released; worker 2 can acquire it immediately
        claim2 = coord2.acquire_claim("worker-2", wait_timeout=0.1)
        self.assertIsNotNone(claim2)
        claim2.release()

    def test_g_eligible_failover_old_released_new_claimed(self):
        """G. eligible failover -> old account released -> new distinct account claimed"""
        acc1 = AgyAccount(alias="acc_fail", home_dir=f"{self.test_dir}/home_fail")
        acc2 = AgyAccount(alias="acc_backup", home_dir=f"{self.test_dir}/home_backup")

        mgr = self._create_manager([acc1, acc2])
        coord = self._create_coordinator(mgr)

        claim1 = coord.acquire_claim("worker-1")
        old_hash = claim1.account_alias_hash
        old_lock_path = claim1.lock_path

        failure_kind = AccountFailureKind.QUOTA_EXHAUSTED
        self.assertTrue(is_rotation_eligible(failure_kind))

        exclude_hashes = set()
        claim2 = coord.rotate_claim(
            current_claim=claim1,
            failure_kind=failure_kind,
            exclude_hashes=exclude_hashes,
        )

        try:
            # Old claim must be released
            self.assertTrue(claim1.released)
            # Old lock must be unlocked
            with open(old_lock_path, "a+") as f:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            # New claim has distinct account hash
            self.assertNotEqual(claim2.account_alias_hash, old_hash)
            self.assertIn(old_hash, exclude_hashes)
        finally:
            claim2.release()

    def test_h_non_rotation_error_no_account_switch(self):
        """H. non-rotation error -> no account switch"""
        non_rotation_kinds = [
            AccountFailureKind.MODEL_OR_TASK_ERROR,
            AccountFailureKind.SYNTAX_OR_IMPLEMENTATION_ERROR,
            AccountFailureKind.VERIFIER_FAILED,
            AccountFailureKind.CANCELLED,
            AccountFailureKind.TIMEOUT,
            AccountFailureKind.PERMISSION_OR_SCOPE_ERROR,
            AccountFailureKind.UNKNOWN,
        ]
        for kind in non_rotation_kinds:
            self.assertFalse(
                is_rotation_eligible(kind),
                f"{kind} must not be eligible for rotation",
            )

    def test_i_no_raw_alias_leaks_into_lock_filenames_or_receipts(self):
        """I. no raw alias leaks into lock filenames / receipts"""
        secret_alias = "confidential_engineer_alpha@secretcorp.internal"
        acc = AgyAccount(alias=secret_alias, home_dir=f"{self.test_dir}/home_secret")

        mgr = self._create_manager([acc])
        coord = self._create_coordinator(mgr)

        claim = coord.acquire_claim("worker-audit")
        try:
            # 1. Inspect all files in leases_dir
            lease_files = list(self.leases_dir.iterdir())
            self.assertGreater(len(lease_files), 0)

            for p in lease_files:
                filename = p.name
                self.assertNotIn("confidential", filename)
                self.assertNotIn("engineer", filename)
                self.assertNotIn("secretcorp", filename)
                self.assertNotIn("@", filename)

                if p.suffix == ".json":
                    content = p.read_text(encoding="utf-8")
                    self.assertNotIn("confidential", content)
                    self.assertNotIn("engineer", content)
                    self.assertNotIn("secretcorp", content)
                    self.assertNotIn("@", content)

                    data = json.loads(content)
                    self.assertEqual(data["account_alias_hash"], acc.alias_hash)
                    self.assertIn("lease_id_hash", data)
                    self.assertIn("consumer_id", data)
                    self.assertIn("pid", data)
        finally:
            claim.release()

    def test_j_three_accounts_three_concurrent_workers(self):
        """J. 3 accounts + 3 concurrent workers -> all 3 can run concurrently"""
        accounts = [
            AgyAccount(alias=f"acc_tri_{i}", home_dir=f"{self.test_dir}/home_tri_{i}")
            for i in range(3)
        ]

        claims = []
        errors = []
        barrier = threading.Barrier(3)

        def worker_target(worker_id):
            try:
                mgr = self._create_manager(accounts)
                coord = self._create_coordinator(mgr)
                claim = coord.acquire_claim(f"worker-{worker_id}", wait_timeout=2.0)
                claims.append(claim)
                # Wait for all 3 workers to hold their claims simultaneously
                barrier.wait(timeout=3.0)
                # Hold claim briefly to prove concurrency
                time.sleep(0.1)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker_target, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5.0)

        self.assertEqual(len(errors), 0)
        self.assertEqual(len(claims), 3)

        hashes = {c.account_alias_hash for c in claims}
        self.assertEqual(len(hashes), 3, "All 3 claims must have distinct account alias hashes")

        for c in claims:
            c.release()

    def test_k_fourth_worker_bounded_wait_pool_busy(self):
        """K. 4th worker -> bounded wait / pool busy behavior"""
        accounts = [
            AgyAccount(alias=f"acc_quad_{i}", home_dir=f"{self.test_dir}/home_quad_{i}")
            for i in range(3)
        ]

        # 3 workers claim all 3 accounts
        mgrs = [self._create_manager(accounts) for _ in range(3)]
        coords = [self._create_coordinator(m) for m in mgrs]
        claims = [coords[i].acquire_claim(f"worker-{i}") for i in range(3)]

        try:
            # 4th worker tries to acquire
            mgr4 = self._create_manager(accounts)
            coord4 = self._create_coordinator(mgr4, poll_interval=0.02)

            started = time.monotonic()
            with self.assertRaises(AgyAccountPoolBusyError):
                coord4.acquire_claim("worker-4", wait_timeout=0.1)
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 0.08, "Must wait bounded timeout before failing busy")

            # Release worker 0
            claims[0].release()

            # Now 4th worker can successfully claim the released account
            claim4 = coord4.acquire_claim("worker-4", wait_timeout=1.0)
            self.assertIsNotNone(claim4)
            self.assertEqual(claim4.account_alias_hash, claims[0].account_alias_hash)
            claim4.release()
        finally:
            for c in claims[1:]:
                c.release()

    def test_l_competing_coordinator_cannot_claim_during_retirement(self):
        """L. Before quarantine is written, the failed account flock still blocks a competing process."""
        # Distinct Python objects model two independent processes observing the same account.
        acc1 = AgyAccount(alias="acc_race_l", home_dir=f"{self.test_dir}/home_l")
        acc2 = AgyAccount(alias="acc_race_l", home_dir=f"{self.test_dir}/home_l")
        self.assertEqual(acc1.alias_hash, acc2.alias_hash)

        mgr1 = self._create_manager([acc1])
        mgr2 = self._create_manager([acc2])
        coord1 = self._create_coordinator(mgr1)
        coord2 = self._create_coordinator(mgr2)
        claim1 = coord1.acquire_claim("worker-1")

        quarantine_entered = threading.Event()
        worker2_done = threading.Event()
        worker2_result: list[Exception] = []
        orig_quarantine = coord1.quarantine_account

        def sync_quarantine(account_alias_hash, reason, claim=None):
            # Pause BEFORE durable quarantine exists. The per-account flock must still protect the account.
            self.assertFalse(coord1.is_quarantined(account_alias_hash))
            quarantine_entered.set()
            worker2_done.wait(timeout=2.0)
            return orig_quarantine(account_alias_hash, reason, claim)

        coord1.quarantine_account = sync_quarantine

        def worker_2_task():
            quarantine_entered.wait(timeout=2.0)
            try:
                coord2.acquire_claim("worker-2", wait_timeout=0.05)
            except Exception as exc:
                worker2_result.append(exc)
            finally:
                worker2_done.set()

        t = threading.Thread(target=worker_2_task)
        t.start()
        coord1.retire_failed_claim(claim1, AccountFailureKind.QUOTA_EXHAUSTED)
        t.join(timeout=3.0)

        # Before quarantine existed, the still-held per-account flock must cause bounded Busy, not a second claim.
        self.assertEqual(len(worker2_result), 1)
        self.assertIsInstance(worker2_result[0], AgyAccountPoolBusyError)

        # After retirement, durable quarantine must make the same account unavailable across processes.
        with self.assertRaises(AgyAccountPoolExhaustedError):
            coord2.acquire_claim("worker-2", wait_timeout=0.05)
        self.assertTrue(coord2.is_quarantined(acc1.alias_hash))

    def test_m_manager_mark_bad_failure_durable_local_quarantine_blocks_acquire(self):
        """M. If manager mark-bad persistence throws/fails, a durable local quarantine blocks subsequent cross-process acquire of that account; no raw alias leaks in quarantine filename/content."""
        secret_alias = "confidential_dev_99@secure.domain.internal"
        acc = AgyAccount(alias=secret_alias, home_dir=f"{self.test_dir}/home_m")

        mgr1 = self._create_manager([acc])
        coord1 = self._create_coordinator(mgr1)

        claim1 = coord1.acquire_claim("worker-1")
        self.assertIsNotNone(claim1)

        # Configure manager mark-bad to throw
        def failing_mark_bad(*args, **kwargs):
            raise AgyAccountPoolManagerError("PERSISTENCE_FAILED_SIMULATED")

        mgr1.mark_account_bad = failing_mark_bad

        # Manager persistence fails, but host-local durable quarantine is an allowed
        # fail-closed fallback; retirement therefore completes safely.
        coord1.retire_failed_claim(claim1, AccountFailureKind.QUOTA_EXHAUSTED)
        self.assertTrue(claim1.released)

        # Separate coordinator/process has an independent in-memory record for the same account.
        acc_other_process = AgyAccount(alias=secret_alias, home_dir=f"{self.test_dir}/home_m")
        self.assertEqual(acc.alias_hash, acc_other_process.alias_hash)
        mgr2 = self._create_manager([acc_other_process])
        coord2 = self._create_coordinator(mgr2)
        with self.assertRaises(AgyAccountPoolExhaustedError):
            coord2.acquire_claim("worker-2", wait_timeout=0.05)

        self.assertTrue(coord2.is_quarantined(acc.alias_hash))

        # Inspect all files in leases_dir for confidentiality
        q_path = self.leases_dir / f"{acc.alias_hash}.quarantine.json"
        self.assertTrue(q_path.exists())

        forbidden_tokens = ("confidential", "dev_99", "secure", "domain", "internal", "@")
        for p in self.leases_dir.iterdir():
            for tok in forbidden_tokens:
                self.assertNotIn(tok, p.name)
            if p.suffix == ".json":
                content = p.read_text(encoding="utf-8")
                for tok in forbidden_tokens:
                    self.assertNotIn(tok, content)
                data = json.loads(content)
                self.assertEqual(data["account_alias_hash"], acc.alias_hash)
                if "quarantine" in p.name:
                    self.assertEqual(data["reason"], AccountFailureKind.QUOTA_EXHAUSTED.value)

    def test_model_family_candidate_tiers_precede_unknown_and_blocked(self):
        accounts = [
            AgyAccount(alias="preferred", home_dir=f"{self.test_dir}/home_pref"),
            AgyAccount(alias="reserve", home_dir=f"{self.test_dir}/home_res"),
            AgyAccount(alias="fallback", home_dir=f"{self.test_dir}/home_fb"),
            AgyAccount(alias="unknown", home_dir=f"{self.test_dir}/home_unknown"),
            AgyAccount(alias="blocked", home_dir=f"{self.test_dir}/home_blocked"),
        ]
        mgr = self._create_manager(accounts)
        coord = self._create_coordinator(mgr)
        keys = {
            "NEXUS_AGY_PREFERRED_ACCOUNTS": "preferred",
            "NEXUS_AGY_RESERVE_ACCOUNTS": "reserve",
            "NEXUS_AGY_FALLBACK_ACCOUNTS": "fallback",
            "NEXUS_AGY_BLOCKED_ACCOUNTS": "blocked",
        }
        old = {key: os.environ.get(key) for key in keys}
        claims = []
        try:
            os.environ.update(keys)
            for index in range(4):
                claims.append(
                    coord.acquire_claim(
                        f"worker-tier-{index}",
                        model_family="gemini",
                    )
                )
            by_hash = {account.alias_hash: account.alias for account in accounts}
            selected = [by_hash[claim.account_alias_hash] for claim in claims]
            self.assertEqual(
                selected,
                ["preferred", "reserve", "fallback", "unknown"],
            )
            self.assertNotIn("blocked", selected)
        finally:
            for claim in reversed(claims):
                claim.release()
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_same_tier_order_precedes_session_spread(self):
        accounts = [
            AgyAccount(alias="urgent", home_dir=f"{self.test_dir}/home_urgent"),
            AgyAccount(alias="later", home_dir=f"{self.test_dir}/home_later"),
        ]
        mgr = self._create_manager(accounts)
        coord = self._create_coordinator(mgr)
        keys = {
            "NEXUS_AGY_PREFERRED_ACCOUNTS": "urgent,later",
            "NEXUS_AGY_RESERVE_ACCOUNTS": "",
            "NEXUS_AGY_FALLBACK_ACCOUNTS": "",
            "NEXUS_AGY_BLOCKED_ACCOUNTS": "",
        }
        old = {key: os.environ.get(key) for key in keys}
        first = None
        second = None
        try:
            os.environ.update(keys)
            first = coord.acquire_claim(
                "worker-expiry-priority-1",
                model_family="gemini",
            )
            second = coord.acquire_claim(
                "worker-expiry-priority-2",
                model_family="gemini",
            )
            by_hash = {account.alias_hash: account.alias for account in accounts}
            self.assertEqual(by_hash[first.account_alias_hash], "urgent")
            self.assertEqual(by_hash[second.account_alias_hash], "later")
        finally:
            if second is not None:
                second.release()
            if first is not None:
                first.release()
            for key, value in old.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_model_family_quota_retirement_blocks_only_failed_family(self):
        """Quota exhaustion must not disable a dual-purpose account for another family."""
        alias = "dual_family_account"
        acc1 = AgyAccount(alias=alias, home_dir=f"{self.test_dir}/home_family")
        acc2 = AgyAccount(alias=alias, home_dir=f"{self.test_dir}/home_family")
        mgr1 = self._create_manager([acc1])
        mgr2 = self._create_manager([acc2])
        coord1 = self._create_coordinator(mgr1)
        coord2 = self._create_coordinator(mgr2)

        claim = coord1.acquire_claim("worker-gemini", model_family="gemini")

        def account_global_mark_bad_must_not_run(*args, **kwargs):
            raise AssertionError("family-scoped quota failure must not mark account globally bad")

        mgr1.mark_account_bad = account_global_mark_bad_must_not_run
        coord1.retire_failed_claim(
            claim,
            AccountFailureKind.QUOTA_EXHAUSTED,
            model_family="gemini",
            unavailable_until=time.time() + 60,
        )

        self.assertTrue(claim.released)
        self.assertFalse(coord1.is_quarantined(acc1.alias_hash))
        self.assertTrue(coord1.is_family_unavailable(acc1.alias_hash, "gemini"))
        self.assertFalse(coord1.is_family_unavailable(acc1.alias_hash, "claude_gpt"))

        with self.assertRaises(AgyAccountPoolExhaustedError):
            coord2.acquire_claim(
                "worker-gemini-2",
                wait_timeout=0.05,
                model_family="gemini",
            )

        claude_claim = coord2.acquire_claim(
            "worker-claude",
            wait_timeout=0.1,
            model_family="claude_gpt",
        )
        self.assertEqual(claude_claim.account_alias_hash, acc1.alias_hash)
        claude_claim.release()

    def test_unscoped_rate_limit_remains_account_global(self):
        acc = AgyAccount(alias="global_rate_limit", home_dir=f"{self.test_dir}/home_rate")
        mgr = self._create_manager([acc])
        coord = self._create_coordinator(mgr)
        claim = coord.acquire_claim("worker-rate", model_family="gemini")

        coord.retire_failed_claim(
            claim,
            AccountFailureKind.RATE_LIMITED,
            model_family="gemini",
            unavailable_until=time.time() + 60,
        )

        self.assertTrue(claim.released)
        self.assertTrue(coord.is_quarantined(acc.alias_hash))
        self.assertFalse(coord.is_family_unavailable(acc.alias_hash, "gemini"))

    def test_expired_model_family_block_is_pruned(self):
        acc = AgyAccount(alias="expiring_family", home_dir=f"{self.test_dir}/home_expire")
        mgr = self._create_manager([acc])
        coord = self._create_coordinator(mgr)

        path = coord.mark_family_unavailable(
            acc.alias_hash,
            model_family="gemini",
            reason=AccountFailureKind.QUOTA_EXHAUSTED.value,
            unavailable_until=time.time() + 1,
        )
        self.assertTrue(path.exists())
        self.assertTrue(coord.is_family_unavailable(acc.alias_hash, "gemini"))

        blocked = coord.get_family_unavailable_hashes(
            "gemini",
            now_ts=time.time() + 2,
        )
        self.assertNotIn(acc.alias_hash, blocked)
        self.assertFalse(path.exists())

    def test_n_final_attempt_rotation_eligible_retires_without_replacement(self):
        """N. Non-quota rotation-eligible failure still consumes max_calls and retires without replacement."""
        if not dispatch_module:
            self.skipTest("dispatch_module not loaded")

        acc1 = AgyAccount(alias="acc_n_1", home_dir=f"{self.test_dir}/home_n_1")
        acc2 = AgyAccount(alias="acc_n_2", home_dir=f"{self.test_dir}/home_n_2")

        mgr = self._create_manager([acc1, acc2])
        coord = self._create_coordinator(mgr)

        calls: list[dict[str, str]] = []

        def mock_run_agy(*, env, prompt, cwd, mode, model, effort, timeout):
            calls.append(dict(env))
            return 1, "", "429 rate limit", False, 50

        code = dispatch_module.dispatch_run(
            prompt="test prompt final attempt",
            cwd=self.test_dir,
            max_calls=1,
            coordinator=coord,
            run_agy_fn=mock_run_agy,
        )
        self.assertEqual(code, 1)
        self.assertEqual(len(calls), 1)

        # Bind assertions to the account actually selected by the coordinator.
        selected_home = calls[0]["HOME"]
        by_home = {acc1.home_dir: acc1, acc2.home_dir: acc2}
        selected = by_home[selected_home]
        other = acc2 if selected is acc1 else acc1
        self.assertTrue(coord.is_quarantined(selected.alias_hash))
        self.assertFalse(coord.is_quarantined(other.alias_hash))
        self.assertFalse((self.leases_dir / f"{other.alias_hash}.receipt.json").exists())

        # No replacement was acquired by the failed run; the other account remains available.
        claim_next = coord.acquire_claim("worker-next", wait_timeout=0.1)
        self.assertEqual(claim_next.account_alias_hash, other.alias_hash)
        claim_next.release()

    def test_o_non_rotation_failure_releases_normally_without_quarantine(self):
        """O. Non-rotation failure still only releases normally and does NOT quarantine or switch accounts."""
        if not dispatch_module:
            self.skipTest("dispatch_module not loaded")

        acc1 = AgyAccount(alias="acc_o_1", home_dir=f"{self.test_dir}/home_o_1")
        acc2 = AgyAccount(alias="acc_o_2", home_dir=f"{self.test_dir}/home_o_2")

        mgr = self._create_manager([acc1, acc2])
        coord = self._create_coordinator(mgr)

        # A semantic/implementation failure remains ineligible for Agy rotation.
        claim = coord.acquire_claim("worker-o")
        self.assertFalse(is_rotation_eligible(AccountFailureKind.TIMEOUT))
        coord.retire_failed_claim(claim, AccountFailureKind.SYNTAX_OR_IMPLEMENTATION_ERROR)
        self.assertFalse(coord.is_quarantined(acc1.alias_hash))
        claim.release()

        # 2. Dispatch run test with non-rotation failure
        calls: list[dict[str, str]] = []

        def mock_run_agy_error(*, env, prompt, cwd, mode, model, effort, timeout):
            calls.append(dict(env))
            return 2, "", "invalid command", False, 50

        code = dispatch_module.dispatch_run(
            prompt="test prompt invalid command",
            cwd=self.test_dir,
            max_calls=3,
            coordinator=coord,
            run_agy_fn=mock_run_agy_error,
        )
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 1, "Non-rotation failure must not retry or switch accounts")

        # Neither account is quarantined
        self.assertFalse(coord.is_quarantined(acc1.alias_hash))
        self.assertFalse(coord.is_quarantined(acc2.alias_hash))

        # Acc1 was cleanly released and can be acquired again
        claim_next = coord.acquire_claim("worker-next", wait_timeout=0.1)
        self.assertEqual(claim_next.account_alias_hash, acc1.alias_hash)
        claim_next.release()

    def test_p_successful_retirement_and_rotation_preserves_permission_restore_before_release(self):
        """P. Successful retirement + rotation selects a distinct account and restores permissions before retirement."""
        if not dispatch_module:
            self.skipTest("dispatch_module not loaded")

        home1 = Path(self.test_dir) / "home_p_1"
        home2 = Path(self.test_dir) / "home_p_2"
        acc1 = AgyAccount(alias="acc_p_1", home_dir=str(home1))
        acc2 = AgyAccount(alias="acc_p_2", home_dir=str(home2))
        mgr = self._create_manager([acc1, acc2])
        coord = self._create_coordinator(mgr)

        first_home: list[str] = []
        retired_hashes: list[str] = []
        perms_restored_before_retire: list[bool] = []
        orig_retire = coord.retire_failed_claim

        def spy_retire(claim, failure_kind, **kwargs):
            actual_home = str(claim.lease.execution_env["HOME"])
            settings_path = Path(actual_home) / ".gemini" / "antigravity-cli" / "settings.json"
            perms_restored_before_retire.append(not settings_path.exists())
            retired_hashes.append(claim.account_alias_hash)
            return orig_retire(claim, failure_kind, **kwargs)

        coord.retire_failed_claim = spy_retire
        calls: list[str] = []

        def mock_run_agy(*, env, prompt, cwd, mode, model, effort, timeout):
            actual_home = str(env["HOME"])
            settings_path = Path(actual_home) / ".gemini" / "antigravity-cli" / "settings.json"
            if not calls:
                first_home.append(actual_home)
                calls.append("call_1")
                self.assertTrue(settings_path.exists(), "settings.json must exist during execution")
                return 1, "", "quota exhausted 429", False, 50
            calls.append("call_2")
            return 0, "SUCCESS", "", False, 50

        code = dispatch_module.dispatch_run(
            prompt="test prompt permission lifecycle",
            cwd=self.test_dir,
            max_calls=2,
            temp_command_permissions=True,
            coordinator=coord,
            run_agy_fn=mock_run_agy,
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(perms_restored_before_retire, [True])

        by_home = {str(home1): acc1, str(home2): acc2}
        selected = by_home[first_home[0]]
        other = acc2 if selected is acc1 else acc1
        self.assertEqual(retired_hashes, [selected.alias_hash])
        self.assertTrue(coord.is_quarantined(selected.alias_hash))
        self.assertFalse(coord.is_quarantined(other.alias_hash))

    def test_q_durable_manager_success_does_not_create_permanent_local_quarantine(self):
        """Q. A durable provider-manager cooldown is sufficient and must not become a permanent local quarantine."""
        acc = AgyAccount(alias="acc_q", home_dir=f"{self.test_dir}/home_q")
        mgr = self._create_manager([acc])
        coord = self._create_coordinator(mgr)
        claim = coord.acquire_claim("worker-q")

        def durable_mark_bad(lease, failure_kind):
            self.assertEqual(failure_kind, AccountFailureKind.QUOTA_EXHAUSTED)
            for record in mgr._pool._accounts.values():
                if record.alias_hash == lease.account_alias_hash:
                    record.is_available = False
            return True

        mgr.mark_account_bad = durable_mark_bad

        def quarantine_must_not_run(*args, **kwargs):
            raise AssertionError(
                "local quarantine must not be written after durable manager persistence"
            )

        coord.quarantine_account = quarantine_must_not_run
        coord.retire_failed_claim(claim, AccountFailureKind.QUOTA_EXHAUSTED)

        self.assertTrue(claim.released)
        self.assertFalse(coord.is_quarantined(acc.alias_hash))

    def test_r_dual_retirement_persistence_failure_keeps_claim_locked_and_raises(self):
        """R. If neither manager nor local quarantine can persist, retirement fails before explicit lock release."""
        acc = AgyAccount(alias="acc_r", home_dir=f"{self.test_dir}/home_r")
        mgr1 = self._create_manager([acc])
        coord1 = self._create_coordinator(mgr1)
        claim = coord1.acquire_claim("worker-r1")

        def manager_failure(*args, **kwargs):
            raise AgyAccountPoolManagerError("manager persistence unavailable")

        def quarantine_failure(*args, **kwargs):
            raise OSError("local quarantine storage unavailable")

        mgr1.mark_account_bad = manager_failure
        coord1.quarantine_account = quarantine_failure

        try:
            with self.assertRaisesRegex(
                AgyAccountPoolManagerError, "AGY_ACCOUNT_RETIREMENT_UNSAFE"
            ):
                coord1.retire_failed_claim(claim, AccountFailureKind.QUOTA_EXHAUSTED)
            self.assertFalse(claim.released)

            # While the failed dispatcher is still alive, another process cannot
            # claim the same account because the per-account flock is still held.
            acc2 = AgyAccount(alias="acc_r", home_dir=f"{self.test_dir}/home_r")
            mgr2 = self._create_manager([acc2])
            coord2 = self._create_coordinator(mgr2, timeout=0.05)
            with self.assertRaises(AgyAccountPoolBusyError):
                coord2.acquire_claim("worker-r2", wait_timeout=0.05)
        finally:
            claim.release()

    def test_s_agy_cli_print_timeout_cannot_report_completed(self):
        """S. Agy CLI print-timeout with exit 0 is transport TIMEOUT, never completed."""
        if not dispatch_module:
            self.skipTest("dispatch_module not loaded")

        from types import SimpleNamespace

        original_which = dispatch_module.shutil.which
        original_run = dispatch_module.subprocess.run
        try:
            dispatch_module.shutil.which = lambda name: "/tmp/fake-agy"
            dispatch_module.subprocess.run = lambda *args, **kwargs: SimpleNamespace(
                returncode=0,
                stdout="",
                stderr="[agy] print timeout after 2m0s with turn in progress; returning partial output\n",
            )
            code, out, err, timed_out, wall_ms = dispatch_module.run_agy(
                env={"HOME": self.test_dir},
                prompt="timeout probe",
                cwd=self.test_dir,
                mode="plan",
                model="gemini-3.8-flash",
                effort="medium",
                timeout=120,
            )
        finally:
            dispatch_module.shutil.which = original_which
            dispatch_module.subprocess.run = original_run

        self.assertEqual(code, 0)
        self.assertEqual(out, "")
        self.assertIn("print timeout after", err)
        self.assertTrue(timed_out)
        self.assertEqual(
            dispatch_module.classify_failure(code, out, err, timed_out),
            AccountFailureKind.TIMEOUT,
        )

        acc = AgyAccount(alias="acc_q", home_dir=f"{self.test_dir}/home_q")
        mgr = self._create_manager([acc])
        coord = self._create_coordinator(mgr)

        def cli_timeout_runner(*, env, prompt, cwd, mode, model, effort, timeout):
            return code, out, err, timed_out, wall_ms

        dispatch_rc = dispatch_module.dispatch_run(
            prompt="timeout probe",
            cwd=self.test_dir,
            max_calls=2,
            coordinator=coord,
            run_agy_fn=cli_timeout_runner,
        )
        self.assertEqual(dispatch_rc, 75)
        self.assertTrue(coord.is_quarantined(acc.alias_hash))
        with self.assertRaises(AgyAccountPoolExhaustedError):
            coord.acquire_claim("worker-after-timeout", wait_timeout=0.1)

    def test_t_timeout_retires_exact_claim_before_release_and_retries_other_account(self):
        acc1 = AgyAccount(alias="timeout_a", home_dir=f"{self.test_dir}/timeout_a")
        acc2 = AgyAccount(alias="timeout_b", home_dir=f"{self.test_dir}/timeout_b")
        mgr = self._create_manager([acc1, acc2])
        coord = self._create_coordinator(mgr)
        events = []
        original_mark = mgr.mark_account_bad

        def mark_bad(lease, kind):
            events.append(("mark", lease.account_alias_hash, kind))
            return original_mark(lease, kind)

        mgr.mark_account_bad = mark_bad
        original_release = mgr.release

        def release(lease):
            events.append(("release", lease.account_alias_hash, None))
            original_release(lease)

        mgr.release = release
        homes = []

        def runner(*, env, **kwargs):
            homes.append(env["HOME"])
            return (
                (0, "", "print timeout after 2m", True, 120000)
                if len(homes) == 1
                else (0, "ok", "", False, 1)
            )

        self.assertEqual(
            dispatch_module.dispatch_run(
                prompt="timeout probe",
                cwd=self.test_dir,
                max_calls=2,
                coordinator=coord,
                run_agy_fn=runner,
            ),
            0,
        )
        self.assertEqual(set(homes), {acc1.home_dir, acc2.home_dir})
        self.assertNotEqual(homes[0], homes[1])
        selected = next(acc for acc in (acc1, acc2) if acc.home_dir == homes[0])
        other = acc2 if selected is acc1 else acc1
        self.assertEqual(events[0], ("mark", selected.alias_hash, AccountFailureKind.TIMEOUT))
        self.assertEqual(events[1], ("release", selected.alias_hash, None))
        self.assertTrue(coord.is_quarantined(selected.alias_hash))
        self.assertFalse(coord.is_quarantined(other.alias_hash))

    def test_u_timeout_max_calls_one_retires_without_replacement(self):
        accounts = [
            AgyAccount(alias=f"timeout_{i}", home_dir=f"{self.test_dir}/timeout_{i}")
            for i in range(2)
        ]
        coord = self._create_coordinator(self._create_manager(accounts))
        acquired = []
        original_acquire = coord.acquire_claim

        def acquire(*args, **kwargs):
            claim = original_acquire(*args, **kwargs)
            acquired.append(claim.account_alias_hash)
            return claim

        coord.acquire_claim = acquire
        self.assertEqual(
            dispatch_module.dispatch_run(
                prompt="timeout probe",
                cwd=self.test_dir,
                max_calls=1,
                coordinator=coord,
                run_agy_fn=lambda **kwargs: (0, "", "print timeout", True, 120000),
            ),
            1,
        )
        self.assertEqual(len(acquired), 1)
        self.assertIn(acquired[0], {acc.alias_hash for acc in accounts})
        self.assertTrue(coord.is_quarantined(acquired[0]))
        other_hash = next(acc.alias_hash for acc in accounts if acc.alias_hash != acquired[0])
        self.assertFalse(coord.is_quarantined(other_hash))

    def test_v_timeout_manager_cooldown_does_not_leave_permanent_quarantine(self):
        acc = AgyAccount(alias="timeout_cooldown", home_dir=f"{self.test_dir}/timeout_cooldown")
        mgr = self._create_manager([acc])
        coord = self._create_coordinator(mgr)
        claim = coord.acquire_claim("worker-timeout")

        def durable_mark_bad(lease, kind):
            self.assertEqual(kind, AccountFailureKind.TIMEOUT)
            self.assertEqual(lease.account_alias_hash, claim.account_alias_hash)
            self.assertFalse(claim.released)
            return True

        mgr.mark_account_bad = durable_mark_bad
        coord.retire_failed_claim(claim, AccountFailureKind.TIMEOUT)
        self.assertTrue(claim.released)
        self.assertFalse(coord.is_quarantined(acc.alias_hash))


if __name__ == "__main__":
    unittest.main()
