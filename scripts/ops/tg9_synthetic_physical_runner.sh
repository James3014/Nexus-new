#!/usr/bin/env bash
set -euo pipefail

STAGE="bootstrap"
trap 'rc=$?; echo "TG9_SYNTHETIC_SUPPORT_FAILURE stage=$STAGE rc=$rc" >&2; exit "$rc"' ERR

MODE="${1:?collect|audit}"
TARGET_SHA="${TARGET_SHA:?}"
TARGET_TREE="${TARGET_TREE:?}"
WORKTREE="$RUNNER_TEMP/tg9-candidate-${MODE}"
OUT="$RUNNER_TEMP/tg9-${MODE}"

STAGE="materialize"
rm -rf "$WORKTREE" "$OUT"
mkdir -p "$OUT"
git cat-file -e "$TARGET_SHA^{commit}"
git worktree add --detach "$WORKTREE" "$TARGET_SHA"
test "$(git -C "$WORKTREE" rev-parse HEAD)" = "$TARGET_SHA"
test "$(git -C "$WORKTREE" rev-parse HEAD^{tree})" = "$TARGET_TREE"

cd "$WORKTREE"
STAGE="frozen-sync"
uv sync --frozen --all-groups --all-extras
STAGE="tg9-tests"
uv run pytest -qq tests/benchmark/test_core_v1_tg9_value_manifest.py | tee "$OUT/tg9-pytest.log"
STAGE="collect-only"
uv run pytest --collect-only -q tests/benchmark/test_core_v1_tg9_value_manifest.py > "$OUT/tg9-collect.txt"
STAGE="normalize-nodeids"
python - "$OUT/tg9-collect.txt" "$OUT/tg9-nodeids.txt" <<'PY'
import sys
from pathlib import Path

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
marker = "tests/benchmark/test_core_v1_tg9_value_manifest.py::"
rows = []
for line in source.read_text(encoding="utf-8").splitlines():
    index = line.find(marker)
    if index >= 0:
        rows.append(line[index:].strip())
rows = sorted(set(rows))
destination.write_text("\n".join(rows) + ("\n" if rows else ""), encoding="utf-8")
print(f"TG9_NORMALIZED_NODE_COUNT={len(rows)}")
PY
NODE_COUNT="$(wc -l < "$OUT/tg9-nodeids.txt" | tr -d ' ')"
STAGE="node-count"
test "$NODE_COUNT" -ge 30
STAGE="synthetic-self-test"
uv run python -m product.benchmark.tg9_value --synthetic-self-test > "$OUT/synthetic-self-test.json"

STAGE="diff-check"
git diff --check "$TARGET_SHA^" "$TARGET_SHA"

STAGE="privacy-fixture"
PRIVACY_ROOT="$RUNNER_TEMP/tg9-synthetic-study-${MODE}"
rm -rf "$PRIVACY_ROOT"
mkdir -p "$PRIVACY_ROOT"
chmod 700 "$PRIVACY_ROOT"
printf '%s\n' '{"schema":"nexus.core-v1.tg9-synthetic-privacy-fixture.v1","value":"SAFE_CODE"}' > "$PRIVACY_ROOT/safe.json"
chmod 600 "$PRIVACY_ROOT/safe.json"
STAGE="privacy-scan"
uv run python -m product.benchmark.tg9_value \
  --privacy-scan "$PRIVACY_ROOT" \
  --report "$PRIVACY_ROOT/privacy-scan.json" > "$OUT/privacy-stdout.json"
cp "$PRIVACY_ROOT/privacy-scan.json" "$OUT/privacy-scan.json"

STAGE="facts-assertions"
python - "$OUT" "$TARGET_SHA" "$TARGET_TREE" "$NODE_COUNT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
subject = sys.argv[2]
tree = sys.argv[3]
node_count = int(sys.argv[4])
self_test = json.loads((out / "synthetic-self-test.json").read_text())
privacy = json.loads((out / "privacy-scan.json").read_text())
assert self_test["state"] == "SYNTHETIC_ONLY", self_test
assert self_test["synthetic"] is True, self_test
assert self_test["negative_checks_passed"] is True, self_test
assert self_test["negative_state"] != "PAIRED_USABILITY_VALUE_EVIDENCE_READY", self_test
assert privacy["status"] == "PASS", privacy
assert privacy["finding_count"] == 0, privacy
assert node_count >= 30

def sha(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()

facts = {
    "schema": "nexus.core-v1.tg9-synthetic-physical-facts.v1",
    "subject_commit": subject,
    "subject_tree": tree,
    "node_count": node_count,
    "nodeid_set_hash": sha(out / "tg9-nodeids.txt"),
    "self_test_hash": sha(out / "synthetic-self-test.json"),
    "self_test_state": self_test["state"],
    "self_test_synthetic": self_test["synthetic"],
    "negative_state": self_test["negative_state"],
    "privacy_scan_hash": privacy["scan_hash"],
    "privacy_status": privacy["status"],
    "privacy_finding_count": privacy["finding_count"],
}
(out / "facts.json").write_text(json.dumps(facts, sort_keys=True, separators=(",", ":")) + "\n")
PY

if [ "$MODE" = "collect" ]; then
  STAGE="collector-acceptance"
  python - "$OUT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
facts = json.loads((out / "facts.json").read_text())
body = {
    "schema": "nexus.core-v1.tg9-synthetic-physical-acceptance.v1",
    "status": "ACCEPT",
    "classification": "SYNTHETIC_ONLY",
    "subject_commit": facts["subject_commit"],
    "subject_tree": facts["subject_tree"],
    "facts_hash": "sha256:" + hashlib.sha256((out / "facts.json").read_bytes()).hexdigest(),
    "real_partner_evidence_consumed": False,
    "value_ready_claimed": False,
}
body["acceptance_hash"] = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
(out / "acceptance.json").write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
PY
  echo "TG9_COLLECT_ROOT=$OUT" >> "$GITHUB_ENV"
elif [ "$MODE" = "audit" ]; then
  STAGE="audit-compare"
  COLLECTOR_ROOT="${COLLECTOR_ROOT:?}"
  cmp "$OUT/facts.json" "$COLLECTOR_ROOT/facts.json"
  STAGE="audit-receipt"
  python - "$OUT" "$COLLECTOR_ROOT" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

out = Path(sys.argv[1])
collector = Path(sys.argv[2])
facts = json.loads((out / "facts.json").read_text())
acceptance = json.loads((collector / "acceptance.json").read_text())
assert acceptance["status"] == "ACCEPT"
assert acceptance["classification"] == "SYNTHETIC_ONLY"
assert acceptance["real_partner_evidence_consumed"] is False
assert acceptance["value_ready_claimed"] is False
body = {
    "schema": "nexus.core-v1.tg9-independent-synthetic-audit.v1",
    "status": "ACCEPT",
    "classification": "SYNTHETIC_ONLY",
    "subject_commit": facts["subject_commit"],
    "subject_tree": facts["subject_tree"],
    "collector_facts_equal": True,
    "real_partner_evidence_consumed": False,
    "value_ready_claimed": False,
}
body["audit_hash"] = "sha256:" + hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
(out / "independent-audit.json").write_text(json.dumps(body, sort_keys=True, separators=(",", ":")) + "\n")
PY
  echo "TG9_AUDIT_ROOT=$OUT" >> "$GITHUB_ENV"
else
  echo "unknown mode: $MODE" >&2
  exit 2
fi

STAGE="done"
echo "TG9_SYNTHETIC_SUPPORT_OK mode=$MODE node_count=$NODE_COUNT"
