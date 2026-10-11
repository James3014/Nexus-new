#!/usr/bin/env bash
# Repro for .github/workflows/git-history-secret-audit.yml:
#  (A) the gate executes the CANDIDATE's own scripts/ops/git_history_secret_scan.py
#      (checked out at PR head), so a PR that edits the scanner self-certifies PASS;
#  (B) the real scanner has no detector for Anthropic keys (sk-ant-...).
set -euo pipefail
SRC=/home/user/Nexus-new/scripts/ops/git_history_secret_scan.py
W=$(mktemp -d); cd "$W"
git init -q --bare origin.git
git clone -q origin.git work 2>/dev/null; cd work
git config user.email t@t; git config user.name t
mkdir -p scripts/ops; cp "$SRC" scripts/ops/; echo base > README; git add -A; git commit -qm base; git push -q origin HEAD:main
check() { # exact workflow assertion (git-history-secret-audit.yml "Run full-history secret scan")
  git fetch -q --force --prune origin '+refs/heads/*:refs/remotes/origin/*' '+refs/tags/*:refs/tags/*'
  snap=$( { git for-each-ref --format='%(refname) %(objectname)' refs/remotes/origin | grep -v '^refs/remotes/origin/HEAD ' ; git for-each-ref --format='%(refname) %(objectname)' refs/tags; } | LC_ALL=C sort | sha256sum | awk '{print $1}')
  python3 scripts/ops/git_history_secret_scan.py --repo . --output scan.json || true
  python3 -c 'import json,sys; p=json.load(open("scan.json")); assert p["status"]=="PASS" and p["blocking_finding_count"]==0 and p["secret_values_emitted"] is False and p["source_revision"]==sys.argv[1] and p["published_ref_snapshot_sha256"]==sys.argv[2]; print("FULL_GIT_HISTORY_SECRET_SCAN_G2_VERIFIED")' "$(git rev-parse HEAD)" "$snap" 2>/dev/null || echo "GATE FAILED (blocking)"
  rm -f scan.json
}
echo "== (B) Anthropic key committed, unmodified scanner"
git checkout -qb pr-b; echo "ANTHROPIC=sk-ant-api03-$(printf 'Q%.0s' $(seq 90))AA" > cfg.txt; git add cfg.txt; git commit -qm b; git push -q origin HEAD:pr-b
check
echo "== control: GitHub PAT committed, unmodified scanner"
git checkout -q main 2>/dev/null || git checkout -qb main origin/main; git checkout -qb pr-c
echo "tok=ghp_$(printf 'Z%.0s' $(seq 36))" > leak.txt; git add leak.txt; git commit -qm c; git push -q origin HEAD:pr-c
check
echo "== (A) same PAT, PR also edits the scanner it is gated by"
sed -i 's/blocking = \[item for item in ordered if item.blocking\]/blocking = []/' scripts/ops/git_history_secret_scan.py
git commit -qam "tweak scanner"; git push -q origin HEAD:pr-c
check
