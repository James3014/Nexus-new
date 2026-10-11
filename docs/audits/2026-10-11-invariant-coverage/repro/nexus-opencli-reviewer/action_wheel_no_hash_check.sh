#!/usr/bin/env bash
# action.yml installs the vendored wheel with `pip install --no-deps --no-index <wheel>` and never
# compares it to vendor/repository-intelligence-engine.provenance.json:wheel_sha256.
set -euo pipefail
REPO=/home/user/nexus-opencli-reviewer
W=$(mktemp -d); cp -r "$REPO/vendor" "$W/vendor"
WHEEL="$W/vendor/repository_intelligence_engine-0.1.0-py3-none-any.whl"
# tamper: inject a module into the wheel (record stays stale; pip does not enforce RECORD for added files)
python3 - "$WHEEL" <<'PY'
import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "a") as z:
    z.writestr("repository_intelligence/_tampered.py", "TAMPERED = True\n")
PY
echo "provenance wheel_sha256: $(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["wheel_sha256"])' "$W/vendor/repository-intelligence-engine.provenance.json")"
echo "actual tampered sha256:  $(sha256sum "$WHEEL" | cut -d' ' -f1)"
echo "hash-check references in action.yml: $(grep -c -E 'sha256sum|provenance|--require-hashes|wheel_sha256' "$REPO/action.yml" || true)"
# exact install command from action.yml line 47
python3 -m pip install -q --no-deps --no-index --target "$W/site" "$WHEEL" && echo "INSTALL ACCEPTED tampered wheel"
PYTHONPATH="$W/site" python3 -c 'import repository_intelligence._tampered as t; print("tampered module importable:", t.TAMPERED)'
