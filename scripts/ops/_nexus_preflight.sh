#!/bin/bash
# Core repository preflight. Provider checks are opt-in and never part of the
# core setup verdict. This script does not read .env or claim production state.
set -u

# Preserve caller precedence; append common cross-install locations only.
export PATH="$PATH:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT" || exit 1

if command -v uv >/dev/null 2>&1; then
    UV_BIN="$(command -v uv)"
else
    echo "[preflight] FAIL: uv is missing (install it or provide it on PATH)" >&2
    exit 1
fi

if [[ -x ".venv/bin/python" ]]; then
    PYTHON=(".venv/bin/python")
    NEXUS_CLI_SMOKE=(".venv/bin/python" "scripts/engine/nexus_cli.py" "--help")
else
    PYTHON=("$UV_BIN" "run" "--no-sync" "python")
    NEXUS_CLI_SMOKE=("uv" "run" "scripts/engine/nexus_cli.py" "--help")
fi

"${PYTHON[@]}" scripts/ops/repo_doctor.py --format human
doctor_status=$?
if (( doctor_status != 0 )); then
    exit "$doctor_status"
fi

if ! "${NEXUS_CLI_SMOKE[@]}" >/dev/null 2>&1; then
    echo "[preflight] FAIL: Nexus CLI smoke failed" >&2
    exit 1
fi

if [[ "${NEXUS_PREFLIGHT_PROVIDER:-0}" == "1" ]]; then
    echo "[preflight] provider checks requested (optional; core already passed)"
    for tool in gemini node; do
        if command -v "$tool" >/dev/null 2>&1; then
            echo "[preflight] provider tool $tool: present"
        else
            echo "[preflight] provider tool $tool: missing"
        fi
    done
    for variable in GEMINI_API_KEY OPENAI_API_KEY; do
        if [[ -n "${!variable:-}" ]]; then
            echo "[preflight] provider variable $variable: present (value redacted)"
        else
            echo "[preflight] provider variable $variable: missing"
        fi
    done
fi

echo "[preflight] core setup canary passed; provider state is optional"
