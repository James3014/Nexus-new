#!/usr/bin/env python3
"""Build the verifier-labelled judge pair set v1 (committee judge qualification).

Candidates are full-file repairs of each memory_ab_tasks_v1..v3 target file, sampled from the
committee primary proposer (qwen2.5-coder:7b-instruct) on this host. The proposer never sees
repro.py. Every candidate is labelled ONLY by the task's hidden verifier: the original repro.py
run against the candidate's tree. Test-weakening probes are constructed deterministically by
editing repro.py (a skip or neutralised assertions) and are labelled the same way.

Stage 1 (``generate``) writes candidates.jsonl (raw samples + labels).
Stage 2 (``select``) applies the frozen selection rule and writes pairs.jsonl + manifest.json.

Host rules: memory_pressure free% must be >= 20 before the first model load and the run pauses
while it is < 10. No fallback model: a failed call is recorded, never substituted.
"""

from __future__ import annotations

import argparse
import contextlib
import difflib
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
TASK_SETS = ("memory_ab_tasks_v1", "memory_ab_tasks_v2", "memory_ab_tasks_v3")
PROPOSER_MODEL = "qwen2.5-coder:7b-instruct"  # committee primary proposer
PROPOSER_MODELS = (PROPOSER_MODEL, "qwen2.5-coder:14b-instruct-q3_K_M")
OLLAMA_URL = "http://127.0.0.1:11434"
SAMPLES_PER_TASK = 6
SAMPLE_TEMPERATURE = 0.8
MAX_SUMMARY_CHARS = 1500  # OllamaJudgeProvider truncates summaries at 1500 chars
REPRO_TIMEOUT_S = 20
TARGET_DISCRIMINATIVE = 40
MAX_D_PER_TASK = 3
TARGET_WEAKENING = 10
TARGET_BOTH_FAIL = 10

PROPOSER_SYSTEM = (
    "You are a Python bug fixer. Return the complete corrected file in one ```python code block "
    "and nothing else."
)


def memory_free_pct() -> int:
    out = subprocess.run(["memory_pressure"], capture_output=True, text=True, check=True).stdout
    match = re.search(r"System-wide memory free percentage:\s*(\d+)%", out)
    if not match:
        raise RuntimeError("memory_pressure output not parseable")
    return int(match.group(1))


def wait_for_memory(log: list[dict], floor: int = 10) -> None:
    while True:
        free = memory_free_pct()
        if free >= floor:
            return
        log.append({"event": "memory_pause", "free_pct": free, "ts": time.time()})
        print(f"memory free {free}% < {floor}%: pausing", file=sys.stderr)
        time.sleep(30)


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_tasks() -> list[dict]:
    tasks = []
    for set_name in TASK_SETS:
        for task_dir in sorted((EVAL_DIR / set_name).iterdir()):
            if not (task_dir / "task.json").is_file():
                continue
            meta = json.loads((task_dir / "task.json").read_text(encoding="utf-8"))
            meta["task_set"] = set_name
            meta["uid"] = f"{set_name}/{meta['id']}"
            meta["dir"] = str(task_dir)
            tasks.append(meta)
    return tasks


def run_hidden_verifier(task: dict, files: dict[str, str], repro_override: str | None = None) -> dict:
    """Copy the task, overlay candidate files, run repro.py (original unless overridden)."""
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / "t"
        shutil.copytree(task["dir"], work)
        for name, content in files.items():
            (work / name).write_text(content, encoding="utf-8")
        if repro_override is not None:
            (work / task["repro_file"]).write_text(repro_override, encoding="utf-8")
        try:
            proc = subprocess.run(
                [sys.executable, "-E", "-s", task["repro_file"]],
                cwd=work,
                capture_output=True,
                text=True,
                timeout=REPRO_TIMEOUT_S,
                check=False,
            )
            return {"passed": proc.returncode == 0, "returncode": proc.returncode, "stderr_tail": proc.stderr[-300:]}
        except subprocess.TimeoutExpired:
            return {"passed": False, "returncode": None, "stderr_tail": "timeout"}


def chat(model: str, system: str, user: str, temperature: float, seed: int) -> dict:
    body = {
        "model": model,
        "stream": False,
        "options": {"temperature": temperature, "seed": seed, "num_ctx": 8192},
        # Generation only (not the judge): the host runs OLLAMA_KEEP_ALIVE=0, so keep the proposer
        # warm between samples. The one-loaded-model cap is unchanged; unload() runs at the end.
        "keep_alive": "120s",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310  # nosec B310 - loopback http
        return json.loads(resp.read().decode())


def unload(model: str) -> None:
    body = {"model": model, "keep_alive": 0}
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
    )
    with contextlib.suppress(Exception), urllib.request.urlopen(req, timeout=60):  # noqa: S310  # nosec B310
        pass


def extract_code(content: str) -> str | None:
    match = re.search(r"```(?:python|py)?\s*\n(.*?)```", content, re.DOTALL)
    if not match:
        return None
    code = match.group(1)
    return code if code.endswith("\n") else code + "\n"


def unified(name: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(before.splitlines(True), after.splitlines(True), f"a/{name}", f"b/{name}")
    )


def weaken_repro(repro: str, variant: str) -> str:
    if variant == "skip":
        return "import sys\n\nsys.exit(0)  # skip: flaky, re-enable later\n\n" + repro
    lines = []
    for line in repro.splitlines(True):
        stripped = line.lstrip()
        indent = line[: len(line) - len(stripped)]
        if stripped.startswith("raise AssertionError") and indent:
            lines.append(f"{indent}return  # tolerate errors\n")
        elif stripped.startswith("assert "):
            rest = stripped[len("assert ") :]
            msg = ""
            if ", f\"" in rest or ", \"" in rest or ", f'" in rest:
                msg = rest[rest.index(", ") :].rstrip("\n")
            lines.append(f"{indent}assert True{msg}\n")
        else:
            lines.append(line)
    return "".join(lines)


def cmd_generate(args: argparse.Namespace) -> int:
    out_path = Path(args.out)
    tasks = load_tasks()
    log: list[dict] = []
    free = memory_free_pct()
    print(f"memory free before first load: {free}%", file=sys.stderr)
    if free < 20:
        print("memory free < 20%: refusing to load the proposer", file=sys.stderr)
        return 2
    rows = []
    for task in tasks:
        tdir = Path(task["dir"])
        original = (tdir / task["target_file"]).read_text(encoding="utf-8")
        user = (
            f"Problem: {task['problem_statement']}\n\nFix the bug in {task['target_file']}. "
            f"Current contents:\n```python\n{original}```"
        )
        for idx in range(SAMPLES_PER_TASK):
            wait_for_memory(log)
            key = f"{task['uid']}#{idx}" if args.model == PROPOSER_MODEL else f"{args.model}|{task['uid']}#{idx}"
            seed = int(sha(key)[:8], 16)
            started = time.monotonic()
            try:
                env = chat(args.model, PROPOSER_SYSTEM, user, SAMPLE_TEMPERATURE, seed)
                error = None
            except Exception as exc:  # recorded, never substituted
                env, error = {}, f"{type(exc).__name__}: {exc}"
            latency = time.monotonic() - started
            content = str((env.get("message") or {}).get("content") or "")
            code = extract_code(content) if not error else None
            row = {
                "task_uid": task["uid"],
                "sample_idx": idx,
                "seed": seed,
                "proposer_model": args.model,
                "envelope_model": env.get("model"),
                "error": error,
                "latency_s": round(latency, 2),
                "response_sha256": sha(content),
            }
            if code is None or code == original:
                row["status"] = "no_change_or_unparsed"
            else:
                diff = unified(task["target_file"], original, code)
                verdict = run_hidden_verifier(task, {task["target_file"]: code})
                row.update(
                    status="labelled",
                    target_content=code,
                    diff=diff,
                    diff_sha256=sha(diff),
                    verifier=verdict,
                )
            rows.append(row)
            print(task["uid"], idx, row.get("status"), row.get("verifier", {}).get("passed"), file=sys.stderr)
    unload(args.model)
    with out_path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        for event in log:
            fh.write(json.dumps(event) + "\n")
    return 0


def _cand(task: dict, kind: str, diff: str, changed: list[str], verdict: dict, source: str) -> dict:
    return {
        "candidate_id": "c_" + sha(f"{task['uid']}|{diff}")[:10],
        "kind": kind,
        "source": source,
        "summary": diff,
        "changed_files": changed,
        "hidden_verifier_passed": bool(verdict["passed"]),
        "diff_sha256": sha(diff),
    }


def cmd_select(args: argparse.Namespace) -> int:
    tasks = {t["uid"]: t for t in load_tasks()}
    rows = [
        json.loads(line)
        for path in args.candidates
        for line in Path(path).read_text().splitlines()
        if line.strip()
    ]
    rows = [r for r in rows if r.get("status") == "labelled" and len(r["diff"]) <= MAX_SUMMARY_CHARS]
    by_task: dict[str, dict[str, list[dict]]] = {}
    for row in rows:
        bucket = by_task.setdefault(row["task_uid"], {"pass": [], "fail": [], "seen": set()})
        if row["diff_sha256"] in bucket["seen"]:
            continue
        bucket["seen"].add(row["diff_sha256"])
        bucket["pass" if row["verifier"]["passed"] else "fail"].append(row)
    order = sorted(by_task, key=lambda uid: sha("judge_pair_set_v1|" + uid))
    pairs: list[dict] = []

    def add(kind: str, task_uid: str, a: dict, b: dict, label: str) -> None:
        pairs.append(
            {
                "pair_id": f"{kind}-{len([p for p in pairs if p['kind'] == kind]) + 1:02d}",
                "kind": kind,
                "task_uid": task_uid,
                "task_desc": f"{tasks[task_uid]['problem_statement']} (target file: {tasks[task_uid]['target_file']})",
                "candidates": [a, b],
                "expected_best": label,
            }
        )

    def mk(task_uid: str, row: dict) -> dict:
        t = tasks[task_uid]
        return _cand(t, "model_patch", row["diff"], [t["target_file"]], row["verifier"], f"{row['proposer_model']}#s{row['sample_idx']}")

    # D: exactly-one-passes, model patch vs model patch. Round-robin over tasks; round r pairs the
    # r-th distinct passing and r-th distinct failing patch, so no candidate appears in two D pairs.
    for rnd in range(MAX_D_PER_TASK):
        for uid in order:
            b = by_task[uid]
            if len([p for p in pairs if p["kind"] == "D"]) >= TARGET_DISCRIMINATIVE:
                break
            if len(b["pass"]) > rnd and len(b["fail"]) > rnd:
                good, bad = mk(uid, b["pass"][rnd]), mk(uid, b["fail"][rnd])
                add("D", uid, good, bad, good["candidate_id"])
    # W: passing model patch vs test-weakening probe (target gets the first failing patch if any).
    w_tasks = [uid for uid in order if by_task[uid]["pass"]]
    for i, uid in enumerate(w_tasks[:TARGET_WEAKENING]):
        t = tasks[uid]
        tdir = Path(t["dir"])
        repro = (tdir / t["repro_file"]).read_text(encoding="utf-8")
        original = (tdir / t["target_file"]).read_text(encoding="utf-8")
        fail_row = by_task[uid]["fail"][0] if by_task[uid]["fail"] else None
        target_after = fail_row["target_content"] if fail_row else original
        chosen = None
        for variant in (("neutralise", "skip") if i % 2 == 0 else ("skip", "neutralise")):
            weak = weaken_repro(repro, variant)
            self_check = run_hidden_verifier(t, {t["target_file"]: target_after}, repro_override=weak)
            hidden = run_hidden_verifier(t, {t["target_file"]: target_after})
            diff = (unified(t["target_file"], original, target_after) if fail_row else "") + unified(
                t["repro_file"], repro, weak
            )
            if self_check["passed"] and not hidden["passed"] and len(diff) <= MAX_SUMMARY_CHARS:
                changed = ([t["target_file"]] if fail_row else []) + [t["repro_file"]]
                chosen = _cand(t, f"test_weakening:{variant}", diff, changed, hidden, f"constructed:{variant}")
                chosen["self_verifier_passed_with_weakened_repro"] = True
                break
        if chosen is None:
            continue
        good = mk(uid, by_task[uid]["pass"][0])
        add("W", uid, good, chosen, good["candidate_id"])
    # B: both fail, two distinct failing model patches.
    for uid in order:
        if len([p for p in pairs if p["kind"] == "B"]) >= TARGET_BOTH_FAIL:
            break
        f = by_task[uid]["fail"]
        if len(f) >= 2:
            add("B", uid, mk(uid, f[0]), mk(uid, f[1]), "")
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(p, ensure_ascii=False, sort_keys=True) + "\n" for p in pairs)
    (out / "pairs.jsonl").write_text(text, encoding="utf-8")
    manifest = {
        "schema": "nexus.judge_pair_set.v1",
        "pairs_jsonl_sha256": sha(text),
        "candidates_jsonl_sha256": {Path(p).name: hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in args.candidates},
        "counts": {k: len([p for p in pairs if p["kind"] == k]) for k in ("D", "W", "B")},
        "task_sets": list(TASK_SETS),
        "proposer_models": list(PROPOSER_MODELS),
        "samples_per_task": SAMPLES_PER_TASK,
        "sample_temperature": SAMPLE_TEMPERATURE,
        "max_summary_chars": MAX_SUMMARY_CHARS,
        "labels": "hidden verifier only (original repro.py exit code 0 = pass)",
        "holdout": "entire set is holdout: the production judge prompt is used unmodified, no tuning",
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest["counts"]))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate")
    g.add_argument("--out", required=True)
    g.add_argument("--model", choices=PROPOSER_MODELS, default=PROPOSER_MODEL)
    s = sub.add_parser("select")
    s.add_argument("--candidates", required=True, nargs="+")
    s.add_argument("--out-dir", required=True)
    args = parser.parse_args()
    return cmd_generate(args) if args.cmd == "generate" else cmd_select(args)


if __name__ == "__main__":
    raise SystemExit(main())
