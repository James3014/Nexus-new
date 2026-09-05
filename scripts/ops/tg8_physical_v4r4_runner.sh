#!/usr/bin/env bash
set -euo pipefail

MODE="${1:?collect|audit}"
CANDIDATE_SHA="${CANDIDATE_SHA:?}"
CANDIDATE_TREE="${CANDIDATE_TREE:?}"
RC1_SHA="${RC1_SHA:?}"
RC2_SHA="${RC2_SHA:?}"
STABLE_SHA="${STABLE_SHA:?}"

materialize() {
  for s in "$CANDIDATE_SHA" "$RC1_SHA" "$RC2_SHA" "$STABLE_SHA"; do git cat-file -e "$s^{commit}"; done
  for pair in "candidate:$CANDIDATE_SHA" "rc1:$RC1_SHA" "rc2:$RC2_SHA" "stable:$STABLE_SHA"; do
    name="${pair%%:*}"; sha="${pair#*:}"
    rm -rf "$name"
    git worktree add --detach "$name" "$sha"
  done
  test "$(git -C candidate rev-parse HEAD^{tree})" = "$CANDIDATE_TREE"
  git merge-base --is-ancestor "$CANDIDATE_SHA" "$RC1_SHA"
  test "$(git diff --name-only "$CANDIDATE_SHA" "$RC1_SHA" -- product)" = product/protocol/__init__.py
  test "$(git rev-parse "$RC2_SHA^")" = "$RC1_SHA"
  test "$(git rev-parse "$STABLE_SHA^")" = "$RC2_SHA"
  test "$(git diff --name-only "$RC1_SHA" "$RC2_SHA" -- product)" = product/protocol/__init__.py
  test "$(git diff --name-only "$RC2_SHA" "$STABLE_SHA" -- product)" = product/protocol/__init__.py
  grep -qx 'PUBLIC_PROTOCOL_VERSION = "0.1.0-experimental"' candidate/product/protocol/__init__.py
  grep -qx 'PUBLIC_PROTOCOL_VERSION = "1.0.0-rc.1"' rc1/product/protocol/__init__.py
  grep -qx 'PUBLIC_PROTOCOL_VERSION = "1.0.0-rc.2"' rc2/product/protocol/__init__.py
  grep -qx 'PUBLIC_PROTOCOL_VERSION = "1.0.0"' stable/product/protocol/__init__.py
}

build_wheels() {
  local root="$1"
  rm -rf "$root"; mkdir -p "$root"/{current,rc1,rc2,stable}
  (cd candidate && uv build --wheel --out-dir "$root/current")
  (cd rc1 && uv build --wheel --out-dir "$root/rc1")
  (cd rc2 && uv build --wheel --out-dir "$root/rc2")
  (cd stable && uv build --wheel --out-dir "$root/stable")
  CURRENT_WHEEL="$(find "$root/current" -name '*.whl' -print -quit)"
  RC1_WHEEL="$(find "$root/rc1" -name '*.whl' -print -quit)"
  RC2_WHEEL="$(find "$root/rc2" -name '*.whl' -print -quit)"
  STABLE_WHEEL="$(find "$root/stable" -name '*.whl' -print -quit)"
  test -n "$CURRENT_WHEEL"; test -n "$RC1_WHEEL"; test -n "$RC2_WHEEL"; test -n "$STABLE_WHEEL"
  export CURRENT_WHEEL RC1_WHEEL RC2_WHEEL STABLE_WHEEL
}

adjudicate() {
  local root="$1" report="$2" stdout="$3"
  (cd candidate && .venv/bin/python -m product.protocol.compatibility_gate \
    --thresholds "$root/thresholds.json" --expected-thresholds-sha256-file "$root/thresholds.sha256" \
    --compatibility "$root/protocol-compatibility.json" --conformance "$root/client-conformance.json" \
    --upgrade-rollback "$root/upgrade-rollback.json" --open-issues "$root/open-issues.json" \
    --tg4-receipt "$root/tg4-receipt.json" --tg5-receipt "$root/tg5-receipt.json" --tg6-receipt "$root/tg6-receipt.json" \
    --tg7-selection "$root/tg7-selection.json" --tg7-corpus "$root/tg7-corpus.json" --tg7-shadow "$root/tg7-shadow-receipt.json" --tg7-report "$root/tg7-report.json" \
    --stable-run-1 "$root/stable-run-1.json" --stable-run-2 "$root/stable-run-2.json" --stable-run-3 "$root/stable-run-3.json" \
    --report "$report" > "$stdout")
}

materialize
(cd candidate && uv sync --frozen --all-groups --all-extras)

if [ "$MODE" = collect ]; then
  ROOT="$RUNNER_TEMP/tg8-v4r4"
  RAW="$ROOT/raw-v4"
  rm -rf "$ROOT"; mkdir -p "$ROOT"
  SEED_ZIP="$RUNNER_TEMP/tg8-v3-seed.zip"
  gh api /repos/James3014/Nexus-new/actions/artifacts/9966978707/zip > "$SEED_ZIP"
  echo 'f68276f3e77237383c4c8491b543be4b017c766556bb844fdef95ad8370d13c9  '"$SEED_ZIP" | sha256sum -c -
  unzip -q "$SEED_ZIP" -d "$ROOT"
  for f in client-conformance.json protocol-compatibility.json upgrade-rollback.json thresholds.json thresholds.sha256 gate-report.json gate-stdout.json physical-acceptance.json; do rm -f "$ROOT/$f"; done
  # Re-seed thresholds only as a manifest skeleton; v4 overlay rewrites all three matrices,
  # their input hashes, and the threshold hash before adjudication.
  unzip -p "$SEED_ZIP" thresholds.json > "$ROOT/thresholds.json"
  unzip -p "$SEED_ZIP" thresholds.sha256 > "$ROOT/thresholds.sha256"
  build_wheels "$RUNNER_TEMP/wheels-v4r4"
  candidate/.venv/bin/python scripts/ops/tg8_physical_v4_overlay_r3.py collect \
    --candidate candidate --rc1 rc1 --current-wheel "$CURRENT_WHEEL" --rc1-wheel "$RC1_WHEEL" --rc2-wheel "$RC2_WHEEL" --stable-wheel "$STABLE_WHEEL" \
    --evidence "$ROOT" --raw "$RAW"
  (cd candidate && .venv/bin/pytest -qq tests/benchmark/test_core_v1_tg8_protocol_gate.py | tee "$ROOT/tg8-pytest-v4.log")
  (cd candidate && .venv/bin/pytest --collect-only -q tests/benchmark/test_core_v1_tg8_protocol_gate.py > "$ROOT/tg8-collect-v4.txt")
  adjudicate "$ROOT" "$ROOT/gate-report-v4.json" "$ROOT/gate-stdout-v4.json"
  python3 - "$ROOT" <<'PY'
import hashlib,json,sys
from pathlib import Path
r=Path(sys.argv[1]); g=json.load(open(r/'gate-report-v4.json')); fp=json.load(open(r/'physical-fingerprint-v4.json'))
assert g['classification']=='PROTOCOL_RC_EVIDENCE_READY',g
assert g['compatibility_counts']=={'failed':0,'refused':12,'supported':12,'total':24},g
assert g['conformance_summary']['parity'] is True and g['upgrade_summary']['failed']==0,g
assert g['false_certification_count']==0 and g['stable_run_count']==0,g
assert all([fp['client_parity'],fp['current_to_rc'],fp['rc_patch'],fp['rc_to_stable'],fp['bad_protocol'],fp['bad_schema'],fp['bad_receipt'],fp['ledger_valid'],not fp['foreign_ledger_valid'],fp['failed_restore']]),fp
b={'schema':'nexus.core-v1.tg8-physical-acceptance-v4.v1','status':'ACCEPT','classification':g['classification'],'subject_commit':g['subject_commit'],'subject_tree':g['subject_tree'],'report_hash':g['report_hash'],'stable_candidate_materialized':True,'stable_promotion_performed':False}
b['acceptance_hash']='sha256:'+hashlib.sha256(json.dumps(b,sort_keys=True,separators=(',',':')).encode()).hexdigest()
(r/'physical-acceptance-v4.json').write_text(json.dumps(b,sort_keys=True,separators=(',',':'))+'\n')
PY
  echo "TG8_V4_ROOT=$ROOT" >> "$GITHUB_ENV"
elif [ "$MODE" = audit ]; then
  ROOT="${COLLECTOR_ROOT:?}"
  RAW="$RUNNER_TEMP/tg8-v4r4-audit"
  mkdir -p "$RAW"
  build_wheels "$RUNNER_TEMP/audit-wheels-v4r4"
  candidate/.venv/bin/python scripts/ops/tg8_physical_v4_overlay_r3.py audit \
    --candidate candidate --rc1 rc1 --current-wheel "$CURRENT_WHEEL" --rc1-wheel "$RC1_WHEEL" --rc2-wheel "$RC2_WHEEL" --stable-wheel "$STABLE_WHEEL" \
    --evidence "$ROOT" --raw "$RAW"
  adjudicate "$ROOT" "$RAW/audit-gate-report-v4.json" "$RAW/audit-gate-stdout-v4.json"
  python3 - "$RAW/audit-gate-report-v4.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); assert r['classification']=='PROTOCOL_RC_EVIDENCE_READY'; assert r['false_certification_count']==0; assert r['conformance_summary']['parity'] is True; assert r['upgrade_summary']['failed']==0
PY
  echo "TG8_V4_AUDIT_ROOT=$RAW" >> "$GITHUB_ENV"
else
  echo "unknown mode $MODE" >&2; exit 2
fi
