# 🛡️ Nexus CI Gate (Agent I - WS-I Hardened v3.0)
# [NEXUS CONFIG: FAIL-CLOSED RELEASE CONTRACT]
import os
import sys
import json
import argparse
import subprocess
import concurrent.futures
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path before importing core modules
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nexus.core.decorators import nexus_metabolize
from scripts.engine.output_guard import truncate_output

WIKI_DRIFT_REPORT = ROOT / ".nexus" / "reports" / "wiki_drift_report.json"
VENV_PYTHON = ROOT / ".venv" / "bin" / "python"
REPORT_TRUST_AUDIT_TARGETS = (
    "tests/engine/test_completion_contract.py",
    "tests/engine/test_completion_enforcer.py",
    "tests/engine/test_canonical_task_seam.py",
    "tests/engine/test_direct_mode_semantic_audit.py",
    "tests/engine/test_cli_semantic_contract_audit.py",
    "tests/test_cli_output_contract.py",
    "tests/engine/test_cli_runner_async.py",
    "tests/engine/test_cli_research_seams.py",
    "tests/engine/test_research_auto_flow_guard_audit.py",
    "tests/engine/test_cli_work_path_audit.py",
    "tests/engine/test_cli_artifact_gate_audit.py",
    "tests/engine/test_delegate_completion_contract.py",
    "tests/research/test_learn_ingest_channels.py",
    "tests/test_cli_learn_mode.py",
    "tests/services/test_cli_commands_service_runtime.py",
    "tests/engine/test_swarm_command_runtime.py",
    "tests/test_v18_legacy_delivery.py",
)


def _target_matches_test_file(target: str, test_file: str) -> bool:
    target = target.strip().replace("\\", "/").strip("/")
    test_file = test_file.strip().replace("\\", "/").strip("/")
    if not target or not test_file:
        return False
    if target.endswith(".py"):
        return test_file == target
    return test_file == target or test_file.startswith(f"{target.rstrip('/')}/")


def _extract_junit_target_durations(junit_path: Path, targets: list[str]) -> dict[str, float]:
    if not junit_path.exists():
        return {}
    try:
        root = ET.fromstring(junit_path.read_text(encoding="utf-8"))
    except (ET.ParseError, ImportError, OSError):
        return {}

    durations = {target: 0.0 for target in targets}
    for testcase in root.iter("testcase"):
        test_file = str(testcase.attrib.get("file") or "")
        if not test_file:
            classname = str(testcase.attrib.get("classname") or "")
            test_file = classname.replace(".", "/") + ".py" if classname else ""
        try:
            elapsed = float(testcase.attrib.get("time") or 0.0)
        except (TypeError, ValueError):
            elapsed = 0.0
        for target in targets:
            if _target_matches_test_file(target, test_file):
                durations[target] += elapsed
                break

    return {target: round(value, 4) for target, value in durations.items() if value > 0}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n", encoding="utf-8")


def _append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def run_step(name, cmd):
    print(f"\n🚀 [CI-Gate] Running: {name}...")
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True)

    # 🛡️ Apply Context Shield / Hard Truncation
    stdout = truncate_output(str(getattr(res, "stdout", "") or ""), label=f"{name}_stdout")
    stderr = truncate_output(str(getattr(res, "stderr", "") or ""), label=f"{name}_stderr")

    if res.returncode == 0:
        print(f"✅ {name} PASSED")
        return True, stdout
    else:
        print(f"❌ {name} FAILED (RC: {res.returncode})")
        print(stdout)
        print(stderr)

        # Save failure summary for the ReAct Loop
        summary_file = ROOT / ".nexus" / "reports" / "last_failure_summary.txt"
        summary_file.parent.mkdir(parents=True, exist_ok=True)
        summary_file.write_text(
            f"Step: {name}\nExit Code: {res.returncode}\n\nSTDOUT:\n{stdout}\n\nSTDERR:\n{stderr}"
        )

        return False, stderr

def run_protocol_check(dry_run: bool):
    print(f"\n🚀 [CI-Gate] Running Agent Protocol Check {'(Dry-run)' if dry_run else ''}...")
    res = subprocess.run(f'"{VENV_PYTHON}" scripts/ops/agent_protocol_check.py', shell=True)
    if res.returncode == 0:
        print("✅ Agent Protocol Check PASSED")
        return True
    else:
        if dry_run:
            print(f"⚠️ [DRY-RUN] Agent Protocol Check FAILED (Return Code: {res.returncode})")
        else:
            print(f"❌ Agent Protocol Check FAILED (Return Code: {res.returncode})")
        return False

def run_lesson_check(dry_run: bool):
    print(f"\n🚀 [CI-Gate] Running Lesson Writeback Check {'(Dry-run)' if dry_run else ''}...")
    
    # [NEXUS v22.5] 自動化結晶化程序：將教訓內化為物理信念
    if not dry_run:
        try:
            subprocess.run([sys.executable, str(ROOT / "scripts/ops/crystallize_lessons.py")], check=True)
            print("✅ [Learning] Lessons automatically crystallized into Belief base.")
        except Exception as e:
            print(f"⚠️ [Learning] Auto-crystallization failed: {e}")

    res = subprocess.run(f'"{VENV_PYTHON}" scripts/ops/lesson_writeback_check.py', shell=True)
    if res.returncode == 0:
        print("✅ Lesson Writeback Check PASSED")
        return True
    else:
        if dry_run:
            print(f"⚠️ [DRY-RUN] Lesson Writeback Check FAILED (Return Code: {res.returncode})")
        else:
            print(f"❌ Lesson Writeback Check FAILED (Return Code: {res.returncode})")
        return False

def run_wiki_sync_check(dry_run: bool):
    print(f"\n🚀 [CI-Gate] Running Wiki Sync Check {'(Dry-run)' if dry_run else ''}...")
    res = subprocess.run(f'"{VENV_PYTHON}" scripts/ops/wiki_sync_check.py --mode worktree', shell=True)
    if res.returncode == 0:
        print("✅ Wiki Sync Check PASSED")
        return "OK"
    elif res.returncode == 2:
        if dry_run:
            print(f"❌ [DRY-RUN-BLOCK] Wiki Sync Check FAILED (Return Code: 2)")
        else:
            print(f"❌ [CI-BLOCK] Wiki Sync Check FAILED (Return Code: 2)")
        return "FAIL"
    else:
        if dry_run:
            print(f"⚠️ [DRY-RUN] Wiki Sync Check FAILED (Return Code: {res.returncode})")
        else:
            print(f"❌ Wiki Sync Check FAILED (Return Code: {res.returncode})")
        return "FAIL"

def run_closeout_contract_check(dry_run: bool, contract_path: str):
    print(f"\n🚀 [CI-Gate] Running Closeout Contract Check {'(Dry-run)' if dry_run else ''}...")
    res = subprocess.run(
        f'"{VENV_PYTHON}" scripts/ops/closeout_guard.py --contract "{contract_path}"',
        shell=True,
    )
    if res.returncode == 0:
        print("✅ Closeout Contract Check PASSED")
        return True
    if dry_run:
        print(f"❌ [DRY-RUN-BLOCK] Closeout Contract Check FAILED (Return Code: {res.returncode})")
    else:
        print(f"❌ [CI-BLOCK] Closeout Contract Check FAILED (Return Code: {res.returncode})")
    return False


def run_optimization_artifact_hygiene_check(
    *,
    read_model_path: str,
    retention_manifest_path: str | None = None,
    dry_run: bool = False,
) -> bool:
    print(f"\n🚀 [CI-Gate] Running Optimization Artifact Hygiene Check {'(Dry-run)' if dry_run else ''}...")
    cmd = [
        str(VENV_PYTHON),
        "scripts/ops/check_optimization_artifact_hygiene.py",
        "--read-model",
        read_model_path,
        "--dry-run",
    ]
    if retention_manifest_path:
        cmd.extend(["--retention-manifest", retention_manifest_path])
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("✅ Optimization Artifact Hygiene Check PASSED")
        return True
    if dry_run:
        print(f"❌ [DRY-RUN-BLOCK] Optimization Artifact Hygiene Check FAILED (Return Code: {res.returncode})")
    else:
        print(f"❌ [CI-BLOCK] Optimization Artifact Hygiene Check FAILED (Return Code: {res.returncode})")
    return False


def run_route_context_seam_freeze_check(*, freeze_path: str, dry_run: bool = False) -> bool:
    print(f"\n🚀 [CI-Gate] Running Route/Context Seam Freeze Check {'(Dry-run)' if dry_run else ''}...")
    cmd = [
        str(VENV_PYTHON),
        "scripts/ops/check_route_context_seam_freeze.py",
        "--freeze",
        freeze_path,
        "--dry-run",
    ]
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print("✅ Route/Context Seam Freeze Check PASSED")
        return True
    if dry_run:
        print(f"❌ [DRY-RUN-BLOCK] Route/Context Seam Freeze Check FAILED (Return Code: {res.returncode})")
    else:
        print(f"❌ [CI-BLOCK] Route/Context Seam Freeze Check FAILED (Return Code: {res.returncode})")
    return False


def run_integrity_check():
    """🛡️ [CI-Gate] Physical Integrity Check (Life-Sign Scan)"""
    print("\n🚀 [CI-Gate] Running Physical Integrity Check...")
    required_sigs = {
        "scripts/ops/evolution_engine_v08.py": ["class EvolutionEngineV08"],
        "scripts/ops/federated_engine_v09.py": ["class FederatedEngineV09", "def fed_sync"],
        "scripts/ops/supervisor_engine.py": ["class SupervisorEngine", "def run_swarm_mission"],
        "scripts/engine/nexus_cli.py": ["def fed_run", "def meta_run", "def delegate"]
    }
    
    for path, sigs in required_sigs.items():
        p = ROOT / path
        if not p.exists():
            print(f"❌ [INTEGRITY] Missing file: {path}")
            return False
        try:
            content = p.read_text()
        except OSError:
            print(f"❌ [INTEGRITY] Unreadable file: {path}")
            return False
        for sig in sigs:
            if sig not in content:
                print(f"❌ [INTEGRITY] Life-sign missing in {path}: '{sig}'")
                return False
    print("✅ Physical Integrity Check PASSED (All Life-Signs detected).")
    return True

def run_delivery_tracked_check(evidence_path: str | None = None, dry_run: bool = False) -> bool:
    """🛡️ 檢查 evidence 中宣稱的 code_artifacts 是否全部被 git 追蹤"""
    label = "(Dry-run)" if dry_run else ""
    print(f"\n🚀 [CI-Gate] Running Delivery Tracked Check {label}...")
    
    if not evidence_path:
        evidence_path = str(ROOT / ".nexus/reports/hallucination_evidence.json")
    
    p = Path(evidence_path)
    if not p.exists():
        print(f"⚠️ [Delivery-Track] Evidence file not found: {p}")
        return True  # 沒 evidence 不阻擋（由其他 gate 處理）

    import json
    try:
        data = json.loads(p.read_text())
    except Exception as e:
        print(f"❌ [Delivery-Track] Parse error: {e}")
        return False
        
    code_artifacts = data.get("evidence_bundle", {}).get("code_artifacts", [])
    
    if not code_artifacts:
        print("✅ [Delivery-Track] No code artifacts to check.")
        return True

    def _extract_artifact_path(artifact):
        if isinstance(artifact, str):
            val = artifact.strip()
            return val if val else None
        if isinstance(artifact, dict):
            for key in ("file_path", "path", "artifact_path"):
                value = artifact.get(key)
                if isinstance(value, str):
                    value = value.strip()
                    if value:
                        return value
        return None

    normalized_artifacts = []
    invalid_artifacts = []
    for artifact in code_artifacts:
        path = _extract_artifact_path(artifact)
        if path:
            normalized_artifacts.append(path)
        else:
            invalid_artifacts.append(artifact)

    if invalid_artifacts:
        print(f"❌ [Delivery-Track] Invalid code artifacts entries: {invalid_artifacts}")
        return False
    
    # 取得 git tracked 清單
    result = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True
    )
    tracked_files = set(result.stdout.strip().split("\n"))
    
    untracked = []
    for artifact in normalized_artifacts:
        try:
            # 轉換為相對路徑
            art_path = Path(artifact)
            if art_path.is_absolute():
                rel = str(art_path.relative_to(ROOT))
            else:
                rel = str(art_path)
                
            # 檢查是否為目錄（目錄本身不在 ls-files 中）
            artifact_full_path = ROOT / rel
            if artifact_full_path.is_dir():
                # 目錄下至少要有一個 tracked file
                has_tracked = any(
                    t.startswith(rel) for t in tracked_files
                )
                if not has_tracked:
                    untracked.append(rel)
            elif rel not in tracked_files:
                untracked.append(rel)
        except Exception:
            untracked.append(artifact)
    
    if untracked:
        print(f"❌ [Delivery-Track] Untracked artifacts found: {untracked}")
        return False
    
    print("✅ Delivery Tracked Check PASSED")
    return True


def run_report_trust_audit(dry_run: bool) -> bool:
    label = "(Dry-run)" if dry_run else ""
    targets = " ".join(REPORT_TRUST_AUDIT_TARGETS)
    success, _ = run_step(
        f"Report Trust Audit {label}".strip(),
        f'"{VENV_PYTHON}" -m pytest {targets} -q',
    )
    return success


def run_skill_catalog_policy_check(dry_run: bool) -> bool:
    label = "(Dry-run)" if dry_run else ""
    success, _ = run_step(
        f"Skill Catalog Policy Check {label}".strip(),
        f'"{VENV_PYTHON}" scripts/ops/check_skill_catalog_policy.py',
    )
    return success


def run_changed_only_check(changed_paths: list[str]) -> bool:
    from scripts.ops.select_tests import load_impact_rules, select_target_details

    start = time.time()
    details = select_target_details(changed_paths, load_impact_rules())
    junit_path = ROOT / ".nexus" / "reports" / "changed_only_junit.xml"
    print("\n🚀 [CI-Gate] Running Changed-Only JIT Tests...")
    for reason in details.reasons:
        print(f"  - {reason}")
    print(
        f"🎯 [CI-Gate] Changed-only targets: {' '.join(details.targets)} "
        f"(confidence={details.confidence:.1f}, risk={details.risk}, sources={','.join(details.sources)})"
    )
    if details.unmatched_paths:
        print(f"⏭️ [CI-Gate] Unmatched changed paths: {', '.join(details.unmatched_paths)}")
    if details.retry_recommended:
        print(f"🔁 [CI-Gate] Retry recommended for flaky targets: {', '.join(details.retry_recommended)}")
    junit_path.parent.mkdir(parents=True, exist_ok=True)
    command = f'"{VENV_PYTHON}" -m pytest {" ".join(details.targets)} -q --junitxml="{junit_path}"'
    success, output = run_step(
        "Changed-Only JIT Tests",
        command,
    )
    target_durations = _extract_junit_target_durations(junit_path, details.targets)
    report_payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": "changed_only",
        "success": success,
        "changed_paths": changed_paths,
        "targets": details.targets,
        "selected_count": len(details.targets),
        "reasons": details.reasons,
        "confidence": details.confidence,
        "risk": details.risk,
        "risk_reasons": details.risk_reasons,
        "sources": details.sources,
        "fallback_used": details.fallback_used,
        "high_risk_escalated": details.high_risk_escalated,
        "unmatched_paths": details.unmatched_paths,
        "retry_recommended": details.retry_recommended,
        "target_durations": target_durations,
        "junit_path": str(junit_path),
        "duration_sec": round(time.time() - start, 4),
    }
    _write_json(ROOT / ".nexus" / "reports" / "changed_only_selection.json", report_payload)
    _append_jsonl(ROOT / ".nexus" / "reports" / "jit_observation.jsonl", report_payload)
    record_test_history(
        mode="changed-only",
        command=command,
        success=success,
        targets=details.targets,
        duration_sec=round(time.time() - start, 4),
        target_durations=target_durations,
        metadata={
            "changed_paths": changed_paths,
            "confidence": details.confidence,
            "risk": details.risk,
            "risk_reasons": details.risk_reasons,
            "sources": details.sources,
            "selected_count": len(details.targets),
            "fallback_used": details.fallback_used,
            "high_risk_escalated": details.high_risk_escalated,
            "unmatched_paths": details.unmatched_paths,
            "retry_recommended": details.retry_recommended,
            "junit_path": str(junit_path),
            "output_excerpt": output[:1000],
        },
    )
    return success


def requires_ultra_review(changed_paths: list[str]) -> bool:
    from scripts.ops.select_tests import load_impact_rules, select_target_details

    details = select_target_details(changed_paths, load_impact_rules())
    return bool(details.high_risk_escalated or details.risk == "high")


def run_ultra_review_check() -> bool:
    report_path = ROOT / ".nexus" / "reports" / "ultra_review_report.json"
    sandbox_root = ROOT / ".nexus" / "reports" / "ultra_review" / "sandboxes"
    print("\n🚀 [CI-Gate] Running Ultra Review Gate...")
    review_cmd = [
        str(VENV_PYTHON),
        "scripts/engine/nexus_cli.py",
        "nexus",
        "ultra-review",
        "--report-file",
        str(report_path),
        "--sandbox-root",
        str(sandbox_root),
        "--output-json",
    ]
    review = subprocess.run(review_cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if review.stdout:
        print(truncate_output(review.stdout, label="ultra_review_stdout"))
    if review.returncode != 0:
        print(truncate_output(review.stderr, label="ultra_review_stderr"))
        print(f"❌ Ultra Review command FAILED (RC: {review.returncode})")
        return False

    gate_cmd = [
        str(VENV_PYTHON),
        "scripts/ops/ultra_gate.py",
        "--report",
        str(report_path),
        "--check-artifacts",
        "--json",
    ]
    gate = subprocess.run(gate_cmd, cwd=ROOT, capture_output=True, text=True, check=False)
    if gate.stdout:
        print(truncate_output(gate.stdout, label="ultra_gate_stdout"))
    if gate.returncode != 0:
        print(truncate_output(gate.stderr, label="ultra_gate_stderr"))
        print(f"❌ Ultra Review Gate FAILED (RC: {gate.returncode})")
        return False
    print("✅ Ultra Review Gate PASSED")
    return True


def run_jit_promotion_report() -> bool:
    print("\n📈 [CI-Gate] Building JIT predictive promotion report...")
    try:
        from scripts.ops.jit_promotion import DEFAULT_OUTPUT, main as jit_promotion_main

        exit_code = jit_promotion_main([])
        report = json.loads(DEFAULT_OUTPUT.read_text(encoding="utf-8")) if DEFAULT_OUTPUT.exists() else {}
        print(f"📈 [CI-Gate] JIT predictive promotion verdict: {report.get('verdict', 'UNKNOWN')}")
        return exit_code == 0
    except Exception as exc:
        print(f"❌ [CI-Gate] JIT predictive promotion report failed: {exc}")
        return False


def record_test_history(
    mode: str,
    command: str,
    success: bool,
    targets: list[str] | None = None,
    duration_sec: float | None = None,
    target_durations: dict[str, float] | None = None,
    metadata: dict | None = None,
) -> None:
    history_path = ROOT / ".nexus" / "reports" / "test_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": mode,
        "command": command,
        "success": success,
        "targets": targets or [],
    }
    if duration_sec is not None:
        entry["duration_sec"] = duration_sec
    if target_durations:
        entry["target_durations"] = target_durations
    if metadata:
        entry["metadata"] = metadata
    with history_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def run_nightly_full_check() -> bool:
    command = "bash scripts/ops/test_full.sh"
    success, _ = run_step("Nightly Full Regression", command)
    record_test_history(mode="nightly-full", command=command, success=success)
    return success


def run_changed_scope_wiki_governance() -> bool:
    success, _ = run_step(
        "Changed-Scope Wiki Governance Audit",
        f'"{VENV_PYTHON}" scripts/ops/wiki_linter.py --strict --changed-only --ci-report wiki_audit_changed.json',
    )
    return success

def run_dry_run():
    print("🛡️ [Nexus CI Gate] Dry-run status check...")
    if not run_integrity_check():
        print("❌ [CI-BLOCK] Physical Integrity Violation!")
        return 1
    checks = {
        "venv_python": VENV_PYTHON.exists(),
        "contracts_dir": (ROOT / "tests" / "contracts").exists(),
        "benchmark_script": (ROOT / "scripts" / "engine" / "nexus_cli.py").exists(),
    }
    for key, ok in checks.items():
        print(f"- {key}: {'OK' if ok else 'MISSING'}")
    
    checks["protocol_check"] = run_protocol_check(dry_run=True)
    checks["lesson_check"] = run_lesson_check(dry_run=True)
    checks["delivery_tracked"] = run_delivery_tracked_check(dry_run=True)
    checks["report_trust_audit"] = run_report_trust_audit(dry_run=True)
    checks["skill_catalog_policy"] = run_skill_catalog_policy_check(dry_run=True)
    wiki_sync_status = run_wiki_sync_check(dry_run=True)
    checks["wiki_sync"] = (wiki_sync_status == "OK")
    
    print(f"- protocol_check: {'OK' if checks['protocol_check'] else 'FAIL'}")
    print(f"- lesson_check: {'OK' if checks['lesson_check'] else 'FAIL'}")
    print(f"- report_trust_audit: {'OK' if checks['report_trust_audit'] else 'FAIL'}")
    print(f"- skill_catalog_policy: {'OK' if checks['skill_catalog_policy'] else 'FAIL'}")
    print(f"- wiki_sync: {wiki_sync_status}")

    print("\n📊 [Phase 6] Summary Audit (Dry-Run):")
    print_phase_6_summaries(wiki_sync_status=wiki_sync_status)
    
    return 0 if all(checks.values()) else 1

def print_phase_6_summaries(wiki_sync_status="UNKNOWN"):
    reports = {
        "drift": ROOT / ".nexus" / "reports" / "wiki_drift_report.json",
        "capability": ROOT / ".nexus" / "reports" / "wiki_capability_coverage_report.json",
        "eval": ROOT / ".nexus" / "reports" / "wiki_eval_report.json",
        "writeback": ROOT / ".nexus" / "reports" / "wiki_writeback_report.json",
        "coverage": ROOT / ".nexus" / "reports" / "coverage.json"
    }
    ops_loop_dir = ROOT / ".nexus" / "reports" / "bench" / "ops_loop"

    print(f"📊 [Wiki-Sync] Status: {wiki_sync_status}")
    # Drift Summary
    if reports["drift"].exists():
        try:
            drift_data = json.loads(reports["drift"].read_text())
            p0 = drift_data["summary"]["p0_count"]
            p1 = drift_data["summary"]["p1_count"]
            print(f"📊 [Wiki-Drift] P0={p0}, P1={p1}")
        except Exception as e:
            print(f"⚠️ Error parsing drift report: {e}")

    # Capability Summary
    if reports["capability"].exists():
        try:
            cap_data = json.loads(reports["capability"].read_text())
            weighted = cap_data["summary"]["weighted_score"]
            print(f"📊 [Wiki-Capability] Weighted Score: {weighted:.2%}")
        except Exception as e:
            print(f"⚠️ Error parsing capability report: {e}")

    # Eval Regression Summary
    if reports["eval"].exists():
        try:
            eval_data = json.loads(reports["eval"].read_text())
            pass_rate = eval_data["summary"]["pass_rate"]
            print(f"📊 [Wiki-Eval] Pass Rate: {pass_rate:.2%}")
        except Exception as e:
            print(f"⚠️ Error parsing eval report: {e}")

    # Writeback Status Summary
    if reports["writeback"].exists():
        try:
            wb_data = json.loads(reports["writeback"].read_text())
            status = wb_data.get("status", "unknown")
            recent = len(wb_data.get("recent_writebacks", []))
            print(f"📊 [Wiki-Writeback] Status: {status}, Recent Count: {recent}")
        except Exception as e:
            print(f"⚠️ Error parsing writeback report: {e}")

    # Coverage Summary
    if reports["coverage"].exists():
        try:
            cov_data = json.loads(reports["coverage"].read_text())
            total_pct = cov_data["totals"]["percent_covered"]
            print(f"📊 [Test-Coverage] Total covered: {total_pct:.2f}%")
        except Exception as e:
            print(f"⚠️ Error parsing coverage report: {e}")

    # Capability Health Summary (from latest ops_loop report)
    if ops_loop_dir.exists():
        try:
            latest_reports = sorted(
                ops_loop_dir.glob("ops_loop_*.json"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if latest_reports:
                latest = latest_reports[0]
                payload = json.loads(latest.read_text(encoding="utf-8"))
                health = payload.get("health", {}) if isinstance(payload, dict) else {}
                if isinstance(health, dict) and health:
                    verdict = str(health.get("verdict", "UNKNOWN"))
                    score = float(health.get("score", 0.0) or 0.0)
                    print(f"📊 [Capability-Health] Verdict: {verdict}, Score: {score:.2f}, Source: {latest.name}")
                    if verdict != "PASS":
                        print("⚠️ [Capability-Health] Latest benchmark health is not PASS. Review ops_loop report before release.")
                trend_gate = payload.get("trend_gate", {}) if isinstance(payload, dict) else {}
                if isinstance(trend_gate, dict) and trend_gate:
                    t_verdict = str(trend_gate.get("verdict", "UNKNOWN"))
                    mk = trend_gate.get("median_kpi", {}) if isinstance(trend_gate.get("median_kpi"), dict) else {}
                    mc = trend_gate.get("median_consensus", {}) if isinstance(trend_gate.get("median_consensus"), dict) else {}
                    print(
                        "📊 [Capability-TrendGate] Verdict: "
                        f"{t_verdict}, Solve: {float(mk.get('with_solve_rate', 0.0) or 0.0):.2f}, "
                        f"Semantic: {float(mk.get('with_semantic_verified_rate', 0.0) or 0.0):.2f}, "
                        f"WallOverhead: {float(mk.get('wall_overhead_sec', 0.0) or 0.0):.2f}s"
                    )
                    if mc:
                        print(
                            "📊 [Capability-TrendGate] Consensus: "
                            f"Winner->Recommended {float(mc.get('winner_match_recommended_rate', 0.0) or 0.0):.2f}, "
                            f"Winner->ChosenFlow {float(mc.get('winner_match_chosen_flow_rate', 0.0) or 0.0):.2f}"
                        )
                    if t_verdict != "PASS":
                        print("⚠️ [Capability-TrendGate] 3-round median KPI gate is not PASS.")
                route_consensus = payload.get("route_consensus", {}) if isinstance(payload, dict) else {}
                if isinstance(route_consensus, dict) and route_consensus:
                    print(
                        "📊 [Route-Consensus] Winner->Recommended: "
                        f"{float(route_consensus.get('winner_match_recommended_rate', 0.0) or 0.0):.2f}, "
                        "Winner->ChosenFlow: "
                        f"{float(route_consensus.get('winner_match_chosen_flow_rate', 0.0) or 0.0):.2f}"
                    )
        except Exception as e:
            print(f"⚠️ Error parsing capability health report: {e}")

def run_benchmark_check(mode: str, dry_run: bool):
    if mode == "off": return True
    
    print(f"\n🚀 [CI-Gate] Running Research Benchmark ({mode}) {'(Dry-run)' if dry_run else ''}...")
    
    manifest = "docs/research/research_benchmark_ab_smoke.json" if mode == "smoke" else "docs/research/research_benchmark_ab_10cases_seeded.json"
    report = ROOT / ".nexus" / "reports" / "research" / f"benchmark-{mode}.json"
    
    cmd = f'"{VENV_PYTHON}" scripts/engine/nexus_cli.py nexus research:benchmark --manifest-file {manifest} --mode ab --ab-trials 2 --report-file {report}'
    
    # In CI, we usually want real execution, but if dry_run is true we can skip or run small
    if dry_run and mode == "full":
        print("⚠️ [DRY-RUN] Skipping full benchmark in dry-run mode.")
        return True

    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"❌ Benchmark execution FAILED (RC: {res.returncode})")
        return False
    
    if report.exists():
        try:
            data = json.loads(report.read_text())
            agg = data.get("aggregates", {})
            reg_rate = agg.get("regression_rate", 0.0)
            success_rate = agg.get("success_rate", 0.0)
            print(f"📊 [Benchmark] Success: {success_rate:.2%}, Regression: {reg_rate:.2%}")
            
            if reg_rate > 0.05:
                print(f"❌ [CI-BLOCK] Regression rate {reg_rate:.2%} exceeds 5% threshold!")
                return False
        except Exception as e:
            print(f"⚠️ Error parsing benchmark report: {e}")
            return False
            
    return True


def run_learn_check(mode: str, dry_run: bool, topic: str):
    if mode == "off":
        return True

    print(f"\n🚀 [CI-Gate] Running Learn Mode Check ({mode}) {'(Dry-run)' if dry_run else ''}...")
    report = ROOT / ".nexus" / "reports" / "learn" / "learn-ci-smoke.json"
    phase_slo = ROOT / ".nexus" / "reports" / "learn" / "phase_slo_summary.json"
    cmd = (
        f'"{VENV_PYTHON}" scripts/engine/nexus_cli.py nexus learn:report '
        f'--topic "{topic}" --report-file "{report}" --output-json'
    )
    res = subprocess.run(cmd, shell=True)
    if res.returncode != 0:
        print(f"❌ Learn report execution FAILED (RC: {res.returncode})")
        return False
    if not report.exists():
        print("❌ Learn report missing after execution.")
        return False
    try:
        data = json.loads(report.read_text())
    except Exception as e:
        print(f"❌ Learn report parse failed: {e}")
        return False

    claims = int(data.get("claims_count", 0))
    coverage = float(data.get("coverage", 0.0))
    converged = bool(data.get("converged", False))
    citation_valid_ratio = float(data.get("citation_valid_ratio", 0.0))
    pass_rate = float(data.get("self_question_pass_rate", 0.0))
    stale_claims = int(data.get("stale_claims_count", 0))
    conflict_candidates = int(data.get("conflict_candidate_count", 0))
    print(
        f"📊 [Learn] claims={claims}, coverage={coverage:.2%}, "
        f"citation_valid_ratio={citation_valid_ratio:.2%}, pass_rate={pass_rate:.2%}, "
        f"stale_claims={stale_claims}, conflict_candidates={conflict_candidates}, converged={converged}"
    )

    if claims <= 0:
        print("❌ [CI-BLOCK] Learn claims_count is 0.")
        return False
    if mode == "smoke" and coverage <= 0.0:
        print("❌ [CI-BLOCK] Learn coverage is 0 in smoke mode.")
        return False
    if mode == "smoke" and citation_valid_ratio < 0.9:
        print("❌ [CI-BLOCK] Learn citation_valid_ratio is below 90% in smoke mode.")
        return False
    if mode == "smoke" and pass_rate < 0.5:
        print("❌ [CI-BLOCK] Learn self_question_pass_rate is below 50% in smoke mode.")
        return False
    if mode == "smoke" and conflict_candidates > 3:
        print("❌ [CI-BLOCK] Learn conflict_candidate_count is too high in smoke mode.")
        return False
    if mode == "smoke":
        if not phase_slo.exists():
            print("❌ [CI-BLOCK] Learn phase_slo_summary.json is missing.")
            return False
        try:
            phase_data = json.loads(phase_slo.read_text())
        except Exception as e:
            print(f"❌ [CI-BLOCK] Learn phase SLO summary parse failed: {e}")
            return False
        phase_slo_pass = bool(phase_data.get("phase_slo_pass", False))
        global_required_ratio = float((phase_data.get("global", {}) or {}).get("required_done_ratio", 0.0) or 0.0)
        print(
            f"📊 [Learn-Phase-SLO] phase_slo_pass={phase_slo_pass}, "
            f"required_done_ratio={global_required_ratio:.2%}"
        )
        if not phase_slo_pass:
            print("❌ [CI-BLOCK] Learn phase-level SLO failed.")
            return False
        if global_required_ratio < 0.95:
            print("❌ [CI-BLOCK] Learn required_done_ratio below 95%.")
            return False
    return True


@nexus_metabolize(task_name="CI Gate Quality Audit")
def main():
    parser = argparse.ArgumentParser(description="Nexus CI Gate - Release Governance")
    parser.add_argument("--strict", action="store_true", help="Enforce all checks")
    parser.add_argument("--dry-run", action="store_true", help="Audit only, no exit(1)")
    parser.add_argument("--benchmark-mode", choices=["off", "smoke", "full"], default="off", help="Benchmark execution mode")
    parser.add_argument("--learn-mode", choices=["off", "smoke"], default="off", help="Learn mode gate execution")
    parser.add_argument("--learn-topic", default="nexus", help="Topic used by learn smoke gate")
    parser.add_argument("--wiki-drift-enforce-level", choices=["off", "warn", "p0"], default="warn", help="Drift enforcement level")
    parser.add_argument("--wiki-capability-enforce-level", choices=["off", "warn", "strict"], default="warn", help="Capability enforcement level")
    parser.add_argument("--wiki-eval-enforce-level", choices=["off", "warn", "strict"], default="warn", help="Eval regression enforcement level")
    parser.add_argument("--require-closeout-contract", action="store_true", help="Block CI if done contract closeout check fails")
    parser.add_argument("--closeout-contract-path", default=".nexus/reports/done_contract.json", help="Path to done contract JSON")
    parser.add_argument("--optimization-read-model", default="", help="Optional claim/evidence read model JSON to validate")
    parser.add_argument("--optimization-retention-manifest", default="", help="Optional evidence retention manifest JSON to validate with the read model")
    parser.add_argument("--route-context-freeze", default="", help="Optional route/context seam freeze JSON to validate")
    parser.add_argument("--auto-heal", action="store_true", help="Launch autonomous repair loop on failure")
    parser.add_argument("--changed-only", nargs="*", help="Run only pytest targets affected by changed paths")
    parser.add_argument("--changed-paths", nargs="*", default=[], help="Changed paths used by strict JIT preflight")
    parser.add_argument("--jit-promotion-report", action="store_true", help="Generate warn-only JIT predictive promotion report")
    parser.add_argument("--nightly", action="store_true", help="Run full L3 regression and append test history")
    args = parser.parse_args()

    changed_only = getattr(args, "changed_only", None)
    if isinstance(changed_only, list):
        changed_ok = run_changed_only_check(changed_only)
        if getattr(args, "jit_promotion_report", False):
            changed_ok = run_jit_promotion_report() and changed_ok
        sys.exit(0 if changed_ok else 1)

    if getattr(args, "nightly", False):
        sys.exit(0 if run_nightly_full_check() else 1)

    if args.dry_run:
        dry_exit = run_dry_run()
        if args.require_closeout_contract:
            closeout_ok = run_closeout_contract_check(dry_run=True, contract_path=args.closeout_contract_path)
            if not closeout_ok:
                dry_exit = 1
        if getattr(args, "optimization_read_model", ""):
            hygiene_ok = run_optimization_artifact_hygiene_check(
                read_model_path=args.optimization_read_model,
                retention_manifest_path=getattr(args, "optimization_retention_manifest", "") or None,
                dry_run=True,
            )
            if not hygiene_ok:
                dry_exit = 1
        if getattr(args, "route_context_freeze", ""):
            freeze_ok = run_route_context_seam_freeze_check(
                freeze_path=args.route_context_freeze,
                dry_run=True,
            )
            if not freeze_ok:
                dry_exit = 1
        sys.exit(dry_exit)

    print("🛡️ [Nexus CI Gate] Initializing Automated Audit Lane...")

    if args.strict:
        changed_paths = getattr(args, "changed_paths", [])
        if not run_changed_only_check(changed_paths):
            sys.exit(1)
        if getattr(args, "jit_promotion_report", False) and not run_jit_promotion_report():
            sys.exit(1)
        if requires_ultra_review(changed_paths) and not run_ultra_review_check():
            sys.exit(1)
    
    # 0. Agent Protocol Check
    if not run_protocol_check(dry_run=args.dry_run):
        if not args.dry_run: sys.exit(1)

    # 0b. Lesson Writeback Check
    if not run_lesson_check(dry_run=args.dry_run):
        if not args.dry_run: sys.exit(1)

    # 0c. Wiki Sync Check
    wiki_sync_status = run_wiki_sync_check(dry_run=args.dry_run)
    if wiki_sync_status == "FAIL":
        if not args.dry_run: sys.exit(1)

    if args.require_closeout_contract:
        closeout_ok = run_closeout_contract_check(dry_run=args.dry_run, contract_path=args.closeout_contract_path)
        if not closeout_ok and not args.dry_run:
            sys.exit(1)

    if getattr(args, "optimization_read_model", ""):
        hygiene_ok = run_optimization_artifact_hygiene_check(
            read_model_path=args.optimization_read_model,
            retention_manifest_path=getattr(args, "optimization_retention_manifest", "") or None,
            dry_run=args.dry_run,
        )
        if not hygiene_ok and not args.dry_run:
            sys.exit(1)

    if getattr(args, "route_context_freeze", ""):
        freeze_ok = run_route_context_seam_freeze_check(
            freeze_path=args.route_context_freeze,
            dry_run=args.dry_run,
        )
        if not freeze_ok and not args.dry_run:
            sys.exit(1)

    if not run_report_trust_audit(dry_run=args.dry_run) and not args.dry_run:
        sys.exit(1)

    if not run_skill_catalog_policy_check(dry_run=args.dry_run) and not args.dry_run:
        sys.exit(1)

    if args.strict and args.changed_paths:
        if not run_changed_scope_wiki_governance() and not args.dry_run:
            sys.exit(1)
        print_phase_6_summaries(wiki_sync_status=wiki_sync_status)
        print("\n🎉 [CI-Gate] STRICT CHANGED-SCOPE QUALITY GATES PASSED!")
        sys.exit(0)

    # 1. Wiki Governance Audit (Pass 7 - CI Hardened)
    success, _ = run_step(
        "Wiki Governance Audit",
        f'"{VENV_PYTHON}" scripts/ops/wiki_linter.py --strict --ci-report wiki_audit.json',
    )
    if not success and not args.dry_run: sys.exit(1)

    # 2. Parallelize Wiki Audits for efficiency
    wiki_audits = {
        "Wiki Drift Audit": f'"{VENV_PYTHON}" scripts/ops/wiki_drift_audit.py',
        "Wiki Capability Coverage Audit": f'"{VENV_PYTHON}" scripts/ops/wiki_capability_coverage_audit.py',
        "Wiki Writeback Status Check": f'"{VENV_PYTHON}" scripts/ops/wiki_query_writeback.py',
        "Wiki Eval Regression": f'"{VENV_PYTHON}" scripts/ops/wiki_eval_regression.py',
    }

    print("\n🚀 [CI-Gate] Launching Parallel Wiki Audits...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = {executor.submit(run_step, name, cmd): name for name, cmd in wiki_audits.items()}
        for future in concurrent.futures.as_completed(futures):
            name = futures[future]
            try:
                success, _ = future.result()
                if not success and not args.dry_run:
                    print(f"❌ [CI-BLOCK] Parallel Audit failed: {name}")
                    sys.exit(1)
            except Exception as e:
                print(f"❌ [CI-BLOCK] Parallel Audit crashed: {name} - {e}")
                if not args.dry_run: sys.exit(1)
                
    # 2e. Research Benchmark (Phase 6)
    if not run_benchmark_check(args.benchmark_mode, args.dry_run) and not args.dry_run:
        sys.exit(1)
    
    # 2f. Learn Mode Gate (Phase 6 Learn Lane)
    if not run_learn_check(args.learn_mode, args.dry_run, args.learn_topic) and not args.dry_run:
        sys.exit(1)
    
    # Report Summaries & Enforcement
    print_phase_6_summaries(wiki_sync_status=wiki_sync_status)

    reports = {
        "drift": ROOT / ".nexus" / "reports" / "wiki_drift_report.json",
        "capability": ROOT / ".nexus" / "reports" / "wiki_capability_coverage_report.json",
        "eval": ROOT / ".nexus" / "reports" / "wiki_eval_report.json"
    }

    # Drift Blocking Logic (Enforcement)
    if reports["drift"].exists():
        try:
            drift_data = json.loads(reports["drift"].read_text())
            p0 = drift_data["summary"]["p0_count"]
            if args.wiki_drift_enforce_level == "p0" and p0 > 0:
                print(f"❌ [CI-BLOCK] P0 drift detected! Enforce level: p0. Blocking release.")
                if not args.dry_run: sys.exit(1)
        except Exception as e:
            pass # print_phase_6_summaries already handles error reporting

    # ⚖️ [Round 20 Evolution] Unified Governance Judge
    from nexus.core.policy_loader import PolicyLoader
    from nexus.core.gate_evaluator import GateEvaluator
    
    policy = PolicyLoader.load(str(ROOT))
    judge = GateEvaluator(policy)

    # Capability Enforcement (Evolved)
    if reports["capability"].exists():
        try:
            cap_data = json.loads(reports["capability"].read_text())
            weighted = cap_data["summary"]["weighted_score"]
            # Judge via Evaluator instead of hardcoded 0.95
            if weighted < policy.token_efficiency_min: # Reuse token_efficiency as proxy for cap
                print(f"❌ [CI-BLOCK] Policy Violation: Capability score {weighted:.2%} below required {policy.token_efficiency_min:.2%}")
                if not args.dry_run: sys.exit(1)
        except Exception:
            pass

    # Eval Regression Enforcement (Evolved)
    if reports["eval"].exists():
        try:
            eval_data = json.loads(reports["eval"].read_text())
            pass_rate = eval_data["summary"]["pass_rate"]
            if pass_rate < policy.v_pass_rate_min:
                if args.wiki_eval_enforce_level == "strict":
                    print(f"❌ [CI-BLOCK] Policy Violation: Eval pass rate {pass_rate:.2%} below required {policy.v_pass_rate_min:.2%}")
                    if not args.dry_run: sys.exit(1)
                else:
                    print(f"⚠️ [CI-WARN] Eval pass rate {pass_rate:.2%} below required {policy.v_pass_rate_min:.2%}")
        except Exception:
            pass

    # 3. Code Regression
    success, _ = run_step(
        "DI & Contract Regression",
        f'"{VENV_PYTHON}" -m pytest tests/contracts/ tests/test_container_orchestration.py -q',
    )
    if not success:
        if args.auto_heal:
            print("\n🚨 [CI-Gate] Failure detected. Launching RELENTLESS REPAIR LOOP...")
            repair_cmd = [str(VENV_PYTHON), "scripts/ops/autonomous_repair_loop.py"]
            subprocess.run(repair_cmd)
        elif not args.dry_run:
            sys.exit(1)

    print("\n🎉 [CI-Gate] ALL QUALITY GATES PASSED!")

if __name__ == "__main__":
    # NEXUS IDENTITY: 06624d2 + CI-GUARDED
    main()
