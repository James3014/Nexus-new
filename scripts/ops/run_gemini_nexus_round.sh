#!/bin/bash
set -euo pipefail

# Usage:
#   bash scripts/ops/run_gemini_nexus_round.sh /tmp/round_task.md .nexus/reports/gemini_round_report.json

if [[ $# -lt 2 ]]; then
  echo "Usage: bash scripts/ops/run_gemini_nexus_round.sh <prompt-file> <report-file> [timeout-sec]"
  exit 2
fi

PROMPT_FILE="$1"
REPORT_FILE="$2"
TIMEOUT_SEC="${3:-420}"

if [[ ! -f "$PROMPT_FILE" ]]; then
  echo "Prompt file not found: $PROMPT_FILE"
  exit 3
fi

REPO_ROOT="/Users/jameschen/Workspace/nexus"
cd "$REPO_ROOT"

GEMINI_BIN="/Users/jameschen/.npm-global/bin/gemini"
if [[ ! -x "$GEMINI_BIN" ]]; then
  echo "Gemini binary not found or not executable: $GEMINI_BIN"
  exit 4
fi

echo "[Gemini+Nexus] preflight..."
python3 - <<'PY'
import json, subprocess, time
from pathlib import Path

gemini_bin = "/Users/jameschen/.npm-global/bin/gemini"
report_path = Path(".nexus/reports/gemini_preflight_round.json")
report_path.parent.mkdir(parents=True, exist_ok=True)

start = time.time()
def _as_text(v):
    if v is None:
        return ""
    if isinstance(v, bytes):
        return v.decode("utf-8", errors="replace")
    return str(v)

try:
    proc = subprocess.run(
        [gemini_bin, "-m", "gemini-3-flash-preview", "-y", "--output-format", "text", "-p", "reply with exactly: OK"],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(Path.cwd()),
    )
    out = _as_text(proc.stdout) + _as_text(proc.stderr)
    ok = proc.returncode == 0 and "OK" in out
    payload = {
        "status": "ok" if ok else "fail",
        "reason": "preflight_ok" if ok else "preflight_failed",
        "attempts": [{"phase": "preflight", "exit_code": proc.returncode, "elapsed_sec": round(time.time()-start, 4)}],
        "output": out[-1200:],
    }
except subprocess.TimeoutExpired as exc:
    payload = {
        "status": "fail",
        "reason": "preflight_failed",
        "attempts": [{"phase": "preflight", "exit_code": 124, "classification": "TIMEOUT_WALLCLOCK", "elapsed_sec": round(time.time()-start, 4)}],
        "output": (_as_text(exc.stdout) + _as_text(exc.stderr))[-1200:],
    }

report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(payload, ensure_ascii=False))
if payload["status"] != "ok":
    raise SystemExit(4)
PY

# Always force Nexus armor context into delegated Gemini tasks.
NEXUS_PREAMBLE="$(cat <<'EOF'
[NEXUS v22 ACTIVE]

Mandatory operating contract:
1. Read and follow /Users/jameschen/Workspace/nexus/AGENTS.md and /Users/jameschen/Workspace/nexus/MUSE_PROTO.md.
2. Execute work through Nexus entrypoints (prefer: uv run scripts/engine/nexus_cli.py ...).
3. Do not claim completion without command evidence.
4. Provide: modified files, commands executed, key outputs, residual risks.
5. If gates fail, report NOT DONE and provide next-round plan.
EOF
)"

MERGED_PROMPT_FILE="$(mktemp /tmp/nexus_gemini_prompt.XXXXXX.md)"
trap 'rm -f "$MERGED_PROMPT_FILE"' EXIT
{
  printf "%s\n\n" "$NEXUS_PREAMBLE"
  cat "$PROMPT_FILE"
} > "$MERGED_PROMPT_FILE"

# Dynamic timeout tuning by prompt size to avoid false timeout on heavy tasks.
PROMPT_BYTES="$(wc -c < "$MERGED_PROMPT_FILE" | tr -d ' ')"
INACTIVITY_TIMEOUT_SEC=120
if [[ "$PROMPT_BYTES" -ge 4000 ]]; then
  TIMEOUT_SEC=$(( TIMEOUT_SEC > 720 ? TIMEOUT_SEC : 720 ))
  INACTIVITY_TIMEOUT_SEC=300
elif [[ "$PROMPT_BYTES" -ge 2000 ]]; then
  TIMEOUT_SEC=$(( TIMEOUT_SEC > 480 ? TIMEOUT_SEC : 480 ))
  INACTIVITY_TIMEOUT_SEC=180
fi

echo "[Gemini+Nexus] tuned timeout: timeout_sec=${TIMEOUT_SEC}, inactivity_sec=${INACTIVITY_TIMEOUT_SEC}, prompt_bytes=${PROMPT_BYTES}"

echo "[Gemini+Nexus] dispatch start..."
python3 - "$MERGED_PROMPT_FILE" "$REPORT_FILE" "$TIMEOUT_SEC" "$INACTIVITY_TIMEOUT_SEC" <<'PY'
import json, subprocess, sys, time, selectors
from pathlib import Path

prompt_file = Path(sys.argv[1])
report_file = Path(sys.argv[2])
timeout_sec = int(sys.argv[3])
inactivity_timeout_sec = int(sys.argv[4])
gemini_bin = "/Users/jameschen/.npm-global/bin/gemini"

prompt = prompt_file.read_text(encoding="utf-8")
report_file.parent.mkdir(parents=True, exist_ok=True)
nexus_preamble_injected = "[NEXUS v22 ACTIVE]" in prompt and "Mandatory operating contract:" in prompt

cmd = [gemini_bin, "-m", "gemini-3-flash-preview", "-y", "--output-format", "text", "-p", prompt]
start = time.time()
buf = []
classification = "OK"
exit_code = 0

try:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        cwd=str(Path.cwd()),
        bufsize=1,
    )
    sel = selectors.DefaultSelector()
    sel.register(proc.stdout, selectors.EVENT_READ)
    last_activity = time.time()

    while True:
        now = time.time()
        if now - start > timeout_sec:
            proc.kill()
            classification = "TIMEOUT_WALLCLOCK"
            exit_code = 124
            break
        if now - last_activity > inactivity_timeout_sec:
            proc.kill()
            classification = "TIMEOUT_INACTIVITY"
            exit_code = 124
            break

        events = sel.select(timeout=1.0)
        if events:
            line = proc.stdout.readline()
            if line:
                buf.append(line)
                print(line, end="")
                last_activity = time.time()
            elif proc.poll() is not None:
                break
        elif proc.poll() is not None:
            break

    if proc.poll() is None:
        proc.kill()
        proc.wait()
    else:
        exit_code = proc.returncode

except Exception as exc:  # noqa: BLE001
    classification = "ERROR"
    exit_code = 1
    buf.append(str(exc))

output = "".join(buf)
if classification == "OK":
    if exit_code == 0:
        classification = "OK"
    else:
        classification = "NON_ZERO_EXIT"

payload = {
    "status": "ok" if classification == "OK" else "fail",
    "reason": classification if classification != "OK" else "ok",
    "attempts": [{"phase": "task", "attempt": 1, "exit_code": exit_code, "classification": classification, "elapsed_sec": round(time.time()-start, 4)}],
    "meta": {
        "nexus_preamble_injected": nexus_preamble_injected,
        "model": "gemini-3-flash-preview",
        "prompt_bytes": len(prompt.encode("utf-8")),
    },
    "output": output[-4000:],
}
report_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
if classification != "OK":
    print(json.dumps(payload, ensure_ascii=False))
    raise SystemExit(5)
PY

echo "[Gemini+Nexus] dispatch done. report=$REPORT_FILE"
