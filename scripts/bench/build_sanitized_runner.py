from __future__ import annotations

import argparse
import hashlib
import json
import shlex
import tempfile
import time
from pathlib import Path

from scripts.bench.sanitize_public_benchmark import sanitize_execution_manifest, sanitize_manifest


LEARN_METADATA_PATHS = (
    ".nexus/reports/learn/learning_closure.jsonl",
    ".nexus/reports/learn/phase_slo_summary.json",
    ".nexus/reports/learn/phase_writeback.jsonl",
    ".nexus/reports/learn/x1_readiness_history.json",
)


def _quote(value: object) -> str:
    return shlex.quote(str(value))


def _session_safe_slug(value: str) -> str:
    slug = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in str(value or "")).strip("_")
    return slug or "model"


def _learn_metadata_commit_hook(*, runner_root: Path) -> str:
    allowed_patterns = "|".join(path.replace(".", r"\.") for path in LEARN_METADATA_PATHS)
    return f"""#!/bin/sh
set -eu
RUNNER_ROOT={_quote(runner_root)}
case "$RUNNER_ROOT" in
  /private/tmp/nexus-live-clean-runner-*) ;;
  *) echo "metadata hook skipped: runner root is not a sanctioned temp runner: $RUNNER_ROOT" >&2; exit 0 ;;
esac
if ! git -C "$RUNNER_ROOT" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  exit 0
fi
dirty="$(git -C "$RUNNER_ROOT" status --porcelain --untracked-files=all)"
if [ -z "$dirty" ]; then
  exit 0
fi
other="$(printf '%s\\n' "$dirty" | grep -Ev '^[ MARCUD?!]{{2}} ({allowed_patterns})$' || true)"
if [ -n "$other" ]; then
  echo "metadata hook skipped: non-learn dirty entries remain" >&2
  printf '%s\\n' "$other" >&2
  exit 0
fi
for path in {" ".join(_quote(path) for path in LEARN_METADATA_PATHS)}; do
  if [ -e "$RUNNER_ROOT/$path" ]; then
    git -C "$RUNNER_ROOT" add -f -- "$path"
  fi
done
if git -C "$RUNNER_ROOT" diff --cached --quiet; then
  exit 0
fi
git -C "$RUNNER_ROOT" commit -m "temp-runner-learn-metadata" >/dev/null
echo "metadata hook committed learn run metadata in temp runner" >&2
"""


def _session_marker_paths(*, session_id: str) -> tuple[Path, Path]:
    safe_id = hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:24]
    tmp_dir = Path(tempfile.gettempdir())
    return (
        tmp_dir / f"nexus-bench-gemini-session-{safe_id}.started",
        tmp_dir / f"nexus-bench-codex-session-{safe_id}.started",
    )


def _session_marker_reset_hook(*, session_id: str) -> str:
    gemini_marker, codex_marker = _session_marker_paths(session_id=session_id)
    return f"""#!/bin/sh
set -eu
rm -f -- {_quote(gemini_marker)} {_quote(codex_marker)}
"""


def build_sanitized_runner(
    *,
    source_manifest: Path,
    output_dir: Path,
    runner_path: Path,
    model_name: str,
    provider: str,
    max_tasks: int,
    baseline_only: bool = False,
) -> dict[str, str]:
    provider = provider.strip().lower()
    if provider not in {"gemini", "codex"}:
        raise ValueError(f"unsupported provider: {provider}")
    payload = json.loads(source_manifest.read_text(encoding="utf-8"))
    output_dir.mkdir(parents=True, exist_ok=True)
    execution_manifest = output_dir / "tasks.execution_safe.json"
    disclosure_manifest = output_dir / "tasks.disclosure.json"
    execution_manifest.write_text(
        json.dumps(sanitize_execution_manifest(payload), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    disclosure_manifest.write_text(
        json.dumps(sanitize_manifest(payload), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    reports_dir = output_dir / "reports"
    provider_cwd = output_dir / f"{provider}_cwd"
    outbound_prompt_ledger = output_dir / "outbound_prompt_ledger.jsonl"
    metadata_hook = output_dir / "commit_learn_metadata.sh"
    session_marker_hook = output_dir / "clear_session_markers.sh"
    runner_root = runner_path.resolve().parents[2]
    session_worker_id = f"sanitized-{_session_safe_slug(model_name)}-{int(time.time())}"
    reports_dir.mkdir(exist_ok=True)
    provider_cwd.mkdir(exist_ok=True)
    metadata_hook.write_text(_learn_metadata_commit_hook(runner_root=runner_root), encoding="utf-8")
    session_marker_hook.write_text(_session_marker_reset_hook(session_id=session_worker_id), encoding="utf-8")
    baseline_flag = "--without-only " if baseline_only else ""
    if provider == "gemini":
        provider_env = (
            f"NEXUS_GEMINI_MODEL_NAME={_quote(model_name)} "
            f"NEXUS_DIRECT_GEMINI_MODEL={_quote(model_name)} "
            "NEXUS_DIRECT_GEMINI_TIMEOUT_SEC=240 "
            "NEXUS_GEMINI_SKIP_TRUST=0 "
            f"NEXUS_GEMINI_CLI_CWD={_quote(provider_cwd)} "
        )
    else:
        provider_env = (
            f"NEXUS_CODEX_MODEL_NAME={_quote(model_name)} "
            f"NEXUS_DIRECT_CODEX_MODEL={_quote(model_name)} "
            f"NEXUS_CODEX_EXEC_CWD={_quote(provider_cwd)} "
        )
    command = (
        "NEXUS_VALUE_HIDDEN_VERIFIER=1 "
        f"{provider_env}"
        f"uv run python {_quote(runner_path)} "
        "--session-worker "
        f"{baseline_flag}"
        "--external-model-export-policy sanitized "
        f"--outbound-prompt-ledger {_quote(outbound_prompt_ledger)} "
        f"--session-worker-id {_quote(session_worker_id)} "
        f"--tasks-file {_quote(execution_manifest)} "
        f"--public-disclosure-manifest {_quote(disclosure_manifest)} "
        f"--output-dir {_quote(reports_dir)} "
        f"--max-tasks {max_tasks} "
        "--repeat-trials 1 "
        "--timeout-sec 240 "
        "--total-timeout-sec 1200 "
        "--stop-loss-sec 1200 "
        "--per-task-stop-loss-sec 600 "
        "--require-clean-worktree "
        "--with-nexus-runner subprocess "
        "--with-llm-mode hard "
        f"--without-mode {provider} "
        f"--with-model-provider {provider} "
        "--enable-autoreason-executor "
        "--enable-ddtree-executor "
        "--enable-ultra-review-dry-gate "
        "--llm-candidate-cap 3 "
        "--evidence-bundle "
        "--markdown-report auto"
    )
    preflight_command = command.replace(" --session-worker ", " --preflight-only --session-worker ", 1)
    hook_call = f"sh {_quote(metadata_hook)}"
    session_hook_call = f"sh {_quote(session_marker_hook)}"
    safe_model = "".join(ch if ch.isalnum() else "_" for ch in model_name).strip("_").lower() or provider
    script_suffix = "direct_baseline" if baseline_only else "smoke"
    run_script = output_dir / f"run_{provider}_{safe_model}_{script_suffix}.sh"
    run_script.write_text(
        "#!/bin/sh\nset -eu\n"
        f"{session_hook_call}\n"
        f"{hook_call}\n"
        f"trap '{hook_call}' EXIT\n"
        + command
        + "\n",
        encoding="utf-8",
    )
    if provider == "gemini" and "flash" in model_name:
        (output_dir / "run_flash_smoke.sh").write_text(run_script.read_text(encoding="utf-8"), encoding="utf-8")
    (output_dir / "preflight.sh").write_text(
        "#!/bin/sh\nset -eu\n" + session_hook_call + "\n" + hook_call + "\n" + preflight_command + "\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "nexus_sanitized_runner_package_v1",
        "source_manifest": str(source_manifest),
        "execution_manifest": str(execution_manifest),
        "disclosure_manifest": str(disclosure_manifest),
        "reports_dir": str(reports_dir),
        "provider": provider,
        "provider_cwd": str(provider_cwd),
        "outbound_prompt_ledger": str(outbound_prompt_ledger),
        "learn_metadata_hook": str(metadata_hook),
        "learn_metadata_hook_scope": "temp_runner_only",
        "learn_metadata_hook_allowed_paths": list(LEARN_METADATA_PATHS),
        "session_marker_reset_hook": str(session_marker_hook),
        "session_worker_id": session_worker_id,
        "session_marker_paths": [str(path) for path in _session_marker_paths(session_id=session_worker_id)],
        "model_name": model_name,
        "baseline_only": bool(baseline_only),
        "run_script": str(run_script),
        "preflight_command": preflight_command,
        "run_command": command,
        "claim_boundary": "Package contains sanitized fixture manifests, isolated model cwd, and an outbound prompt ledger gate; it does not itself create live model evidence.",
    }
    package_manifest = output_dir / "sanitized_runner_manifest.json"
    package_manifest.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return {key: str(value) for key, value in manifest.items()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a sanitized benchmark runner package.")
    parser.add_argument("--source-manifest", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--runner-path", default="scripts/bench/capability_ab_runner.py")
    parser.add_argument("--model-name", default="gemini-3-flash-preview")
    parser.add_argument("--provider", choices=["gemini", "codex"], default="gemini")
    parser.add_argument("--max-tasks", type=int, default=1)
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="Build a direct baseline package that runs only the without_nexus arm.",
    )
    args = parser.parse_args()
    manifest = build_sanitized_runner(
        source_manifest=Path(args.source_manifest).resolve(),
        output_dir=Path(args.output_dir).resolve(),
        runner_path=Path(args.runner_path).resolve(),
        model_name=args.model_name,
        provider=args.provider,
        max_tasks=max(1, int(args.max_tasks)),
        baseline_only=bool(args.baseline_only),
    )
    print(json.dumps({"status": "PASS", "package": manifest["execution_manifest"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
