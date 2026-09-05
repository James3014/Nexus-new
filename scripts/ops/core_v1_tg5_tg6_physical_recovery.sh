#!/usr/bin/env bash
set -euo pipefail

: "${GITHUB_TOKEN:?GITHUB_TOKEN required}"
: "${TG5_SHA:?TG5_SHA required}"
: "${TG6_SHA:?TG6_SHA required}"
: "${EXPECTED_PREDECESSOR_SHA256:?EXPECTED_PREDECESSOR_SHA256 required}"
: "${EXPECTED_TG5_RECEIPT_HASH:?EXPECTED_TG5_RECEIPT_HASH required}"

EVIDENCE_DIR="${EVIDENCE_DIR:-/tmp/core-v1-physical-recovery-v2}"
TG5_MERGE_SHA="${TG5_MERGE_SHA:-4bf99aac7673603400e6a69436aaf23f4d7b3f88}"
TG7_MERGE_SHA="${TG7_MERGE_SHA:-ddfdfc6d3277f134130fef992e0b4deb3d86efe1}"
MAIN_FENCE_SHA="${MAIN_FENCE_SHA:-f5fa2d69c22c51f20ec5090293fc36d5d4ae813c}"

rm -rf "$EVIDENCE_DIR" /tmp/nexus-tg5 /tmp/nexus-tg6 /tmp/nexus-pred-*
mkdir -p "$EVIDENCE_DIR" \
  /private/tmp/nexus-core-v1-evidence/tg7 \
  /private/tmp/nexus-core-v1-predecessor \
  /private/tmp/nexus-core-v1-wheel-a \
  /private/tmp/nexus-core-v1-wheel-b \
  /private/tmp/nexus-core-v1-wheelhouse

git cat-file -e "$TG5_SHA^{commit}"
git cat-file -e "$TG6_SHA^{commit}"
git worktree add --detach /tmp/nexus-tg5 "$TG5_SHA"
git worktree add --detach /tmp/nexus-tg6 "$TG6_SHA"

TG5_TREE="$(git -C /tmp/nexus-tg5 rev-parse HEAD^{tree})"
TG6_TREE="$(git -C /tmp/nexus-tg6 rev-parse HEAD^{tree})"
printf 'tg5_sha=%s\ntg5_tree=%s\ntg6_sha=%s\ntg6_tree=%s\n' \
  "$TG5_SHA" "$TG5_TREE" "$TG6_SHA" "$TG6_TREE" > "$EVIDENCE_DIR/exact-subjects.txt"

(cd /tmp/nexus-tg5 && uv sync --frozen --all-groups --all-extras)
(cd /tmp/nexus-tg6 && uv sync --frozen --all-groups --all-extras)

cd /tmp/nexus-tg5
NEXUS_CORE_HTTP_PORT=8767 uv run pytest -qq tests/product/test_http_e2e.py -m live --run-live \
  | tee "$EVIDENCE_DIR/tg5-live-pytest.log"

cat > /tmp/capture_tg5_receipt.py <<'PY'
import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

import httpx
import requests

from product.evidence import _hash
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.runtime.auth import generate_bearer_token, write_secure_token
from product.runtime.http import start_runtime
from product.runtime.service import RuntimeCertificationService
from tests.product.test_http_e2e import MockGitHubPort, make_mock_executor

EVIDENCE_DIR = Path(os.environ["EVIDENCE_DIR"])
EXPECTED = os.environ["EXPECTED_TG5_RECEIPT_HASH"]
TOKEN = os.environ["GITHUB_TOKEN"]


def live_subject():
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github.v3+json"}
    pr = requests.get("https://api.github.com/repos/James3014/Nexus-new/pulls/635", headers=headers, timeout=30)
    pr.raise_for_status()
    data = pr.json()
    diff_headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github.v3.diff"}
    diff = requests.get("https://api.github.com/repos/James3014/Nexus-new/pulls/635", headers=diff_headers, timeout=30)
    diff.raise_for_status()
    files = requests.get("https://api.github.com/repos/James3014/Nexus-new/pulls/635/files?per_page=100", headers=headers, timeout=30)
    files.raise_for_status()
    changed = tuple(sorted(row["filename"] for row in files.json()))
    return data["base"]["sha"], data["head"]["sha"], diff.content, changed


async def main():
    base_sha, head_sha, diff_bytes, changed_paths = live_subject()
    gh_port = MockGitHubPort(base_sha=base_sha, head_sha=head_sha, diff_bytes=diff_bytes, changed_paths=changed_paths)
    executor = make_mock_executor(exit_code=0)
    with tempfile.TemporaryDirectory(prefix="tg5-recovery-") as td:
        root = Path(td)
        token_path = root / ".config" / "nexus-core" / "token"
        token_path.parent.mkdir(parents=True, mode=0o700)
        token = generate_bearer_token()
        write_secure_token(token, token_path)
        db_path = root / "state" / "ledger.sqlite3"
        db_path.parent.mkdir(parents=True, mode=0o700)
        service = RuntimeCertificationService(db_path=db_path, github_port=gh_port, runner_executor=executor)
        handle = await start_runtime(host="127.0.0.1", port=0, token_path=token_path, db_path=db_path, service=service)
        request = {
            "protocol_version": PUBLIC_PROTOCOL_VERSION,
            "implementation_schema": IMPLEMENTATION_SCHEMA,
            "repository": {
                "owner": "James3014", "name": "Nexus-new", "pr_number": 635,
                "expected_base_sha": base_sha, "expected_head_sha": head_sha,
            },
            "acceptance_contract": {
                "contract_id": "ac-live-635", "requirements_hash": _hash("reqs"),
                "required_verifier_ids": ["pytest"], "allowed_paths": list(changed_paths),
                "deletion_policy": "FORBID",
            },
            "verification_plan": {
                "plan_id": "plan-live-635", "acceptance_contract_hash": _hash("ac"),
                "change_set_hash": _hash("cs"), "required_verifier_ids": ["pytest"],
            },
            "profile_id": "python-oci-pytest-v1",
            "idempotency_key": "live-tracer-635-run-1",
            "expected_generation": 0,
        }
        try:
            headers = {"Authorization": f"Bearer {handle.token}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{handle.port}", timeout=30.0) as client:
                response = await client.post("/v1/certifications", headers=headers, json=request)
                assert response.status_code == 202, response.text
                request_id = response.json()["request_id"]
                terminal = None
                for _ in range(100):
                    await asyncio.sleep(0.1)
                    status = await client.get(f"/v1/certifications/{request_id}", headers=headers)
                    status.raise_for_status()
                    terminal = status.json()
                    if terminal.get("state") not in {"PENDING", "RUNNING"}:
                        break
                assert terminal and terminal["state"] == "COMPLETED", terminal
                assert terminal["disposition"] == "CERTIFIED", terminal
                rr = await client.get(f"/v1/certifications/{request_id}/receipt", headers=headers)
                rr.raise_for_status()
                receipt = rr.json()
        finally:
            await handle.stop()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    request_bytes = (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode()
    receipt_bytes = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
    (EVIDENCE_DIR / "tg5-live-request.json").write_bytes(request_bytes)
    (EVIDENCE_DIR / "tg5-receipt.json").write_bytes(receipt_bytes)
    (EVIDENCE_DIR / "tg5-live-response.json").write_text(json.dumps(terminal, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    metadata = {
        "schema": "nexus.core-v1.tg5-recovery.v1",
        "pr": 635,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "diff_sha256": "sha256:" + hashlib.sha256(diff_bytes).hexdigest(),
        "changed_paths": list(changed_paths),
        "receipt_hash": receipt.get("receipt_hash"),
        "expected_receipt_hash": EXPECTED,
        "receipt_file_sha256": "sha256:" + hashlib.sha256(receipt_bytes).hexdigest(),
        "request_file_sha256": "sha256:" + hashlib.sha256(request_bytes).hexdigest(),
        "matches_expected": receipt.get("receipt_hash") == EXPECTED,
    }
    (EVIDENCE_DIR / "tg5-recovery-metadata.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metadata, sort_keys=True))
    if receipt.get("receipt_hash") != EXPECTED:
        raise SystemExit("recovered TG5 receipt hash does not match durable historical physical evidence")


asyncio.run(main())
PY
EVIDENCE_DIR="$EVIDENCE_DIR" EXPECTED_TG5_RECEIPT_HASH="$EXPECTED_TG5_RECEIPT_HASH" GITHUB_TOKEN="$GITHUB_TOKEN" \
  .venv/bin/python /tmp/capture_tg5_receipt.py
cp "$EVIDENCE_DIR/tg5-receipt.json" /private/tmp/nexus-core-v1-evidence/tg7/tg5-receipt.json
chmod 0444 /private/tmp/nexus-core-v1-evidence/tg7/tg5-receipt.json

cd "$GITHUB_WORKSPACE"
: > "$EVIDENCE_DIR/predecessor-candidates.tsv"
MATCHED=""
for SHA in "$TG5_MERGE_SHA" "$TG7_MERGE_SHA" "$MAIN_FENCE_SHA"; do
  WT="/tmp/nexus-pred-${SHA:0:8}"
  OUT="$EVIDENCE_DIR/predecessor-${SHA}"
  mkdir -p "$OUT"
  git worktree add --detach "$WT" "$SHA"
  EPOCH="$(git -C "$WT" show -s --format=%ct "$SHA")"
  if (cd "$WT" && SOURCE_DATE_EPOCH="$EPOCH" uv build --wheel --out-dir "$OUT"); then
    WHEEL="$(find "$OUT" -maxdepth 1 -type f -name 'nexus_singularity-28.3.0-py3-none-any.whl' -print -quit)"
    if [[ -n "$WHEEL" ]]; then
      HASH="$(sha256sum "$WHEEL" | awk '{print $1}')"
      printf '%s\t%s\t%s\n' "$SHA" "$HASH" "$WHEEL" >> "$EVIDENCE_DIR/predecessor-candidates.tsv"
      if [[ "$HASH" == "$EXPECTED_PREDECESSOR_SHA256" ]]; then
        cp "$WHEEL" /private/tmp/nexus-core-v1-predecessor/nexus_singularity-28.3.0-py3-none-any.whl
        MATCHED="$SHA"
      fi
    fi
  else
    printf '%s\tBUILD_FAILED\t%s\n' "$SHA" "$OUT" >> "$EVIDENCE_DIR/predecessor-candidates.tsv"
  fi
  git worktree remove --force "$WT"
done
[[ -n "$MATCHED" ]]
printf '%s\n' "$MATCHED" > "$EVIDENCE_DIR/predecessor-source-sha.txt"
PRED=/private/tmp/nexus-core-v1-predecessor/nexus_singularity-28.3.0-py3-none-any.whl
[[ "$(sha256sum "$PRED" | awk '{print $1}')" == "$EXPECTED_PREDECESSOR_SHA256" ]]
cp "$PRED" "$EVIDENCE_DIR/"

EPOCH="$(git -C /tmp/nexus-tg6 show -s --format=%ct "$TG6_SHA")"
rm -rf /private/tmp/nexus-core-v1-wheel-a/* /private/tmp/nexus-core-v1-wheel-b/*
(cd /tmp/nexus-tg6 && SOURCE_DATE_EPOCH="$EPOCH" uv build --wheel --out-dir /private/tmp/nexus-core-v1-wheel-a)
(cd /tmp/nexus-tg6 && SOURCE_DATE_EPOCH="$EPOCH" uv build --wheel --out-dir /private/tmp/nexus-core-v1-wheel-b)
A=/private/tmp/nexus-core-v1-wheel-a/nexus_core-28.3.0-py3-none-any.whl
B=/private/tmp/nexus-core-v1-wheel-b/nexus_core-28.3.0-py3-none-any.whl
[[ -f "$A" && -f "$B" ]]
A_HASH="$(sha256sum "$A" | awk '{print $1}')"
B_HASH="$(sha256sum "$B" | awk '{print $1}')"
[[ "$A_HASH" == "$B_HASH" ]]
cmp -s "$A" "$B"
printf 'build_a_sha256=%s\nbuild_b_sha256=%s\nequal=true\n' "$A_HASH" "$B_HASH" > "$EVIDENCE_DIR/tg6-build-hashes.txt"
cp "$A" "$EVIDENCE_DIR/tg6-build-a.whl"
cp "$B" "$EVIDENCE_DIR/tg6-build-b.whl"

rm -rf /private/tmp/nexus-core-v1-wheelhouse/*
cd /tmp/nexus-tg6
.venv/bin/python - <<'PY'
import tomllib
from pathlib import Path
from packaging.markers import Marker

data = tomllib.loads(Path("uv.lock").read_text(encoding="utf-8"))
packages = {p["name"]: p for p in data["package"]}
todo = ["nexus-core"]
seen = set()
requirements = []
while todo:
    name = todo.pop()
    if name in seen:
        continue
    seen.add(name)
    pkg = packages.get(name)
    if not pkg:
        raise SystemExit(f"locked package missing: {name}")
    if name != "nexus-core":
        requirements.append(f"{name}=={pkg['version']}")
    for dep in pkg.get("dependencies", []):
        marker = dep.get("marker")
        if marker and not Marker(marker).evaluate():
            continue
        todo.append(dep["name"])
Path("/tmp/core-v1-locked-requirements.txt").write_text("\n".join(sorted(requirements)) + "\n", encoding="utf-8")
PY
python -m pip download --disable-pip-version-check --only-binary=:all: --no-deps \
  -r /tmp/core-v1-locked-requirements.txt -d /private/tmp/nexus-core-v1-wheelhouse
cp "$A" /private/tmp/nexus-core-v1-wheelhouse/

.venv/bin/python - <<'PY'
import hashlib
import json
import zipfile
from pathlib import Path
from packaging.utils import parse_wheel_filename

root = Path("/private/tmp/nexus-core-v1-wheelhouse")
build_a = Path("/private/tmp/nexus-core-v1-wheel-a/nexus_core-28.3.0-py3-none-any.whl")
build_b = Path("/private/tmp/nexus-core-v1-wheel-b/nexus_core-28.3.0-py3-none-any.whl")
lock = Path("/tmp/nexus-tg6/uv.lock")

def sha(path): return "sha256:" + hashlib.sha256(Path(path).read_bytes()).hexdigest()
def files(path):
    with zipfile.ZipFile(path) as zf: return sorted(zf.namelist())

rows = []
for wheel in sorted(root.glob("*.whl"), key=lambda p: p.name):
    dist, version, _build, _tags = parse_wheel_filename(wheel.name)
    rows.append({"distribution": str(dist), "version": str(version), "filename": wheel.name, "sha256": sha(wheel)})
closure_hash = "sha256:" + hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
manifest = {
    "schema": "nexus.core-v1.tg6-wheelhouse.v1",
    "python": "3.12",
    "platform": "ubuntu-24.04-x86_64",
    "source_lock_hash": sha(lock),
    "build_a_hash": sha(build_a),
    "build_b_hash": sha(build_b),
    "build_a_files": files(build_a),
    "build_b_files": files(build_b),
    "selected_successor_hash": sha(build_a),
    "closure": rows,
    "closure_hash": closure_hash,
    "generated_at": "2026-09-05T00:00:00Z",
}
body = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
manifest["manifest_hash"] = "sha256:" + hashlib.sha256(body).hexdigest()
(root / "wheelhouse-manifest.json").write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
PY
cp /private/tmp/nexus-core-v1-wheelhouse/wheelhouse-manifest.json "$EVIDENCE_DIR/"
cp /tmp/core-v1-locked-requirements.txt "$EVIDENCE_DIR/"

uv run pytest -qq tests/product/test_client_conformance.py -k predecessor_artifact \
  | tee "$EVIDENCE_DIR/tg6-02-predecessor.log"
uv run pytest -qq tests/product/test_client_conformance.py -k wheelhouse_manifest \
  | tee "$EVIDENCE_DIR/tg6-05-wheelhouse.log"
uv run pytest -qq tests/product/test_client_conformance.py -k install_upgrade_rollback \
  | tee "$EVIDENCE_DIR/tg6-10-migration.log"

rm -rf /private/tmp/nexus-core-v1-clean-install
python -m venv /private/tmp/nexus-core-v1-clean-install
/private/tmp/nexus-core-v1-clean-install/bin/pip install --disable-pip-version-check --no-index \
  --find-links /private/tmp/nexus-core-v1-wheelhouse nexus-core==28.3.0 \
  | tee "$EVIDENCE_DIR/tg6-07-install.log"
/private/tmp/nexus-core-v1-clean-install/bin/pip check | tee "$EVIDENCE_DIR/tg6-pip-check.log"
/private/tmp/nexus-core-v1-clean-install/bin/nexus-certify --help > "$EVIDENCE_DIR/tg6-08-nexus-certify-help.txt"
/private/tmp/nexus-core-v1-clean-install/bin/nexus --help > "$EVIDENCE_DIR/tg6-09-legacy-help.txt"

cat > /tmp/tg6_live_client.py <<'PY'
import asyncio
import json
import os
import tempfile
from pathlib import Path
import requests

from product.evidence import _hash
from product.protocol import IMPLEMENTATION_SCHEMA, PUBLIC_PROTOCOL_VERSION
from product.runtime.auth import generate_bearer_token, write_secure_token
from product.runtime.http import start_runtime
from product.runtime.service import RuntimeCertificationService
from tests.product.test_http_e2e import MockGitHubPort, make_mock_executor

EVIDENCE_DIR = Path(os.environ["EVIDENCE_DIR"])
EXPECTED = json.loads((EVIDENCE_DIR / "tg5-receipt.json").read_text(encoding="utf-8"))
TOKEN = os.environ["GITHUB_TOKEN"]
CLI = "/private/tmp/nexus-core-v1-clean-install/bin/nexus-certify"


def subject():
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github.v3+json"}
    pr = requests.get("https://api.github.com/repos/James3014/Nexus-new/pulls/635", headers=headers, timeout=30); pr.raise_for_status(); data = pr.json()
    diff = requests.get("https://api.github.com/repos/James3014/Nexus-new/pulls/635", headers={"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github.v3.diff"}, timeout=30); diff.raise_for_status()
    files = requests.get("https://api.github.com/repos/James3014/Nexus-new/pulls/635/files?per_page=100", headers=headers, timeout=30); files.raise_for_status()
    return data["base"]["sha"], data["head"]["sha"], diff.content, tuple(sorted(r["filename"] for r in files.json()))


async def main():
    base_sha, head_sha, diff_bytes, changed = subject()
    with tempfile.TemporaryDirectory(prefix="tg6-live-") as td:
        root = Path(td); home = root / "home"; token_path = home / ".config" / "nexus-core" / "token"
        token_path.parent.mkdir(parents=True, mode=0o700); token = generate_bearer_token(); write_secure_token(token, token_path)
        db_path = root / "state" / "ledger.sqlite3"; db_path.parent.mkdir(parents=True, mode=0o700)
        service = RuntimeCertificationService(db_path=db_path, github_port=MockGitHubPort(base_sha=base_sha, head_sha=head_sha, diff_bytes=diff_bytes, changed_paths=changed), runner_executor=make_mock_executor(exit_code=0))
        handle = await start_runtime(host="127.0.0.1", port=8767, token_path=token_path, db_path=db_path, service=service)
        request = {
            "protocol_version": PUBLIC_PROTOCOL_VERSION, "implementation_schema": IMPLEMENTATION_SCHEMA,
            "repository": {"owner":"James3014","name":"Nexus-new","pr_number":635,"expected_base_sha":base_sha,"expected_head_sha":head_sha},
            "acceptance_contract": {"contract_id":"ac-live-635","requirements_hash":_hash("reqs"),"required_verifier_ids":["pytest"],"allowed_paths":list(changed),"deletion_policy":"FORBID"},
            "verification_plan": {"plan_id":"plan-live-635","acceptance_contract_hash":_hash("ac"),"change_set_hash":_hash("cs"),"required_verifier_ids":["pytest"]},
            "profile_id":"python-oci-pytest-v1","idempotency_key":"live-tracer-635-run-1","expected_generation":0,
        }
        request_path = EVIDENCE_DIR / "tg6-live-request.json"; request_path.write_text(json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n")
        env = os.environ.copy(); env["HOME"] = str(home)
        try:
            proc = await asyncio.create_subprocess_exec(CLI,"submit","--request",str(request_path),"--url","http://127.0.0.1:8767",stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env)
            stdout, stderr = await proc.communicate()
        finally:
            await handle.stop()
    (EVIDENCE_DIR / "tg6-live-client-stderr.txt").write_bytes(stderr)
    if proc.returncode != 0: raise SystemExit(stderr.decode(errors="replace"))
    response = json.loads(stdout.decode())
    (EVIDENCE_DIR / "tg6-live-client-response.json").write_text(json.dumps(response, sort_keys=True, indent=2) + "\n")
    assert response["state"] == "COMPLETED" and response["disposition"] == "CERTIFIED"
    assert response["receipt"] == EXPECTED
    print(json.dumps({"request_id": response["request_id"], "receipt_hash": response["receipt"]["receipt_hash"], "parity": True}, sort_keys=True))


asyncio.run(main())
PY
cd /tmp/nexus-tg5
EVIDENCE_DIR="$EVIDENCE_DIR" GITHUB_TOKEN="$GITHUB_TOKEN" .venv/bin/python /tmp/tg6_live_client.py \
  | tee "$EVIDENCE_DIR/tg6-11-live-client.log"

EVIDENCE_DIR="$EVIDENCE_DIR" TG5_SHA="$TG5_SHA" TG6_SHA="$TG6_SHA" \
EXPECTED_PREDECESSOR_SHA256="$EXPECTED_PREDECESSOR_SHA256" EXPECTED_TG5_RECEIPT_HASH="$EXPECTED_TG5_RECEIPT_HASH" \
python - <<'PY'
import hashlib, json, os
from pathlib import Path
root = Path(os.environ["EVIDENCE_DIR"])
summary = {
    "schema": "nexus.core-v1.tg5-tg6-physical-recovery.v2",
    "tg5_sha": os.environ["TG5_SHA"], "tg6_sha": os.environ["TG6_SHA"],
    "expected_predecessor_sha256": os.environ["EXPECTED_PREDECESSOR_SHA256"],
    "expected_tg5_receipt_hash": os.environ["EXPECTED_TG5_RECEIPT_HASH"], "files": [],
}
for path in sorted(p for p in root.rglob("*") if p.is_file()):
    summary["files"].append({"path": str(path.relative_to(root)), "sha256": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(), "bytes": path.stat().st_size})
body = json.dumps(summary, sort_keys=True, separators=(",", ":")).encode(); summary["bundle_hash"] = "sha256:" + hashlib.sha256(body).hexdigest()
(root / "bundle-summary.json").write_text(json.dumps(summary, sort_keys=True, indent=2) + "\n")
PY
