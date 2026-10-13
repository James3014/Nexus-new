// pushCandidate only protects main/master/trunk plus refs/remotes/<remote>/HEAD when it
// happens to exist locally. With a non-conventional default branch and no origin/HEAD
// symref (git init + remote add + fetch), the default branch is pushed to directly.
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
const SRC = process.env.DEVSPACE_SRC!;
const { pushCandidate } = await import(`${SRC}/git-candidate.ts`);
const g = (cwd: string, ...a: string[]) => execFileSync("git", a, { cwd, encoding: "utf8", env: { ...process.env, GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@t", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@t" } }).trim();
const base = mkdtempSync(join(tmpdir(), "ds-push-"));
const remote = join(base, "remote.git"); const seed = join(base, "seed"); const wt = join(base, "wt");
g(base, "init", "-q", "--bare", "-b", "production", remote);
g(base, "init", "-q", "-b", "production", seed); g(seed, "commit", "-q", "--allow-empty", "-m", "base"); g(seed, "push", "-q", remote, "production");
g(base, "init", "-q", "-b", "work", wt); g(wt, "remote", "add", "origin", remote); g(wt, "fetch", "-q", "origin");
g(wt, "reset", "-q", "--hard", "origin/production"); g(wt, "commit", "-q", "--allow-empty", "-m", "unreviewed candidate");
const head = g(wt, "rev-parse", "HEAD");
console.log("remote default (bare HEAD):", g(remote, "symbolic-ref", "HEAD"));
let sym = "absent"; try { sym = g(wt, "symbolic-ref", "refs/remotes/origin/HEAD"); } catch {}
console.log("local refs/remotes/origin/HEAD:", sym);
const res = await pushCandidate({ workspaceRoot: wt, expectedHead: head, remote: "origin", branch: "production" });
console.log("pushCandidate result:", JSON.stringify(res));
console.log("remote production now ==candidate:", g(remote, "rev-parse", "production") === head);
// control: with origin/HEAD present, it is refused
g(wt, "remote", "set-head", "origin", "production");
try { await pushCandidate({ workspaceRoot: wt, expectedHead: head, remote: "origin", branch: "production" }); console.log("control: NOT refused"); }
catch (e: any) { console.log("control with origin/HEAD set:", e.code); }
