"""repo-learning: inspect_skill_directory fails OPEN when a fingerprinted control
file is missing/unreadable: compute_skill_content_sha256 raises OSError ->
computed_content_sha256=None -> ContractAttestation.current falls back to comparing
the self-declared manifest identity only -> current=True, defect=NONE."""
import shutil, subprocess, sys, tempfile
from pathlib import Path
REPO = Path("/home/user/repo-learning")
sys.path.insert(0, str(REPO / "src"))
from repolearn.deployment import inspect_skill_directory, sync_skill_install

tmp = Path(tempfile.mkdtemp())
root = tmp / "skills"
print("sync:", sync_skill_install(REPO / "skills/repo-learning", root).defect.value)
installed = root / "repo-learning"
# Tamper 1: modify SKILL.md -> correctly detected
(installed / "SKILL.md").write_text("# hijacked policy\n")
a = inspect_skill_directory(installed)
print("modified SKILL.md       -> current=%s defect=%s" % (a.current, a.defect.value))
# Tamper 2: delete SKILL.md entirely (and policy.md) -> fails open
(installed / "SKILL.md").unlink(); (installed / "references/policy.md").unlink()
a = inspect_skill_directory(installed)
print("deleted SKILL.md+policy -> current=%s defect=%s computed=%s" % (a.current, a.defect.value, a.computed_content_sha256))
# Same through the operator CLI --check path
r = subprocess.run([sys.executable, str(REPO / "scripts/install_skill.py"), "--root", str(root), "--check"],
                   capture_output=True, text=True)
print("install_skill.py --check rc=%d stdout=%r stderr=%r" % (r.returncode, r.stdout.strip(), r.stderr.strip()))
# Tamper 3: also on the SOURCE gate: a source tree with a missing control file is accepted as current
src = tmp / "src-skill"; shutil.copytree(REPO / "skills/repo-learning", src)
(src / "references/state-contract.md").unlink()
r2 = sync_skill_install(src, tmp / "other-root")
print("sync from source missing state-contract.md -> current=%s defect=%s" % (r2.current, r2.defect.value))
