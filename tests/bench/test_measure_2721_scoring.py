"""#2721 arm scoring/aggregation (score_arms.py): synthetic fixtures, fake receipts, no scorer."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import numpy as np
import pytest

from scripts.bench.measure_2721 import score_arms as sa

ARMS = ("BARE", "NEXUS", "NOOP")
ENV_KEY, SPEC = "e" * 64, "5" * 64


# -- fixtures --------------------------------------------------------------------------

def _tasks(n=4):
    return [{"id": f"pkg-{100 + i}", "key": f"own__pkg--{100 + i}", "base": "a" * 40, "merge": "b" * 40,
             "venv": "pkg", "set": "M" if i % 2 == 0 else "LA"} for i in range(n)]


@pytest.fixture
def env(tmp_path):
    tasks = _tasks()
    (tmp_path / "index.json").write_text(json.dumps(tasks))
    (tmp_path / "s1.json").write_text(json.dumps({"rows": [{"id": t["id"], "set": t["set"], "survives": True}
                                                           for t in tasks] + [{"id": "pkg-999", "set": "M",
                                                                               "survives": False}]}))
    s1 = tmp_path / "s1arch"
    (s1 / "harness").mkdir(parents=True)
    driver = s1 / "harness" / "driver_s1_2721.py"
    driver.write_text("print('fake driver')\n")
    (s1 / "MANIFEST.sha256").write_text(f"{sa.sha256_file(driver)}  ./harness/driver_s1_2721.py\n")
    export = tmp_path / "export"
    for rel in sa.SCORER_FILES:
        (export / rel).parent.mkdir(parents=True, exist_ok=True)
        (export / rel).write_text(f"# {rel}\n")
    pins = {"driver_sha": sa.sha256_file(driver), "s1_manifest_sha": sa.sha256_file(s1 / "MANIFEST.sha256"),
            "scorer_files": {rel: sa.git_blob_sha(export / rel) for rel in sa.SCORER_FILES}}
    for t in tasks:  # S1 self-check receipts: the venv identity reference
        rdir = s1 / "receipts" / "gold_a" / "tasks" / t["key"]
        rdir.mkdir(parents=True)
        (rdir / "real_outcome.json").write_text(json.dumps({"env_key": ENV_KEY, "spec_sha256": SPEC}))
    cfg = {"s1_archive": s1, "s1_receipts": s1 / "receipts", "driver": driver, "export": export,
           "venvs": tmp_path / "venvs",
           "synth_root": tmp_path / "synth", "task_index": tmp_path / "index.json",
           "s1_result": tmp_path / "s1.json", "python": "python3", "work_root": tmp_path / "work",
           "concurrency": 2}
    return {"tmp": tmp_path, "tasks": tasks, "cfg": cfg, "pins": pins,
            "identity": lambda: sa.verify_identity(driver, s1, export, **pins)}


def make_blind(tmp, tasks, *, repeats=3, arms=ARMS, flags=None, drop=(), extra=None, excluded=()):
    """Blind dir + the custodian's arm map. ``flags``: {(task, repeat, arm): [..]};
    ``drop``: (task, repeat, arm) rows that blind.py excluded (harness infra)."""
    blind_dir = tmp / "blind"
    (blind_dir / "candidates").mkdir(parents=True)
    rows, amap, n = [], {}, 0
    for t in tasks:
        for r in range(1, repeats + 1):
            for a in arms:
                if (t["id"], r, a) in drop:
                    continue
                n += 1
                opaque = f"{n:016x}"
                diff = f"diff --git a/x.py b/x.py\n+{a.lower()}-{t['id']}-{r}\n".encode() if a != "NOOP" else b""
                (blind_dir / "candidates" / f"{opaque}.diff").write_bytes(diff)
                row = {"opaque_id": opaque, "task_id": t["id"], "repeat": r, "diff_sha256": sa.sha256_bytes(diff),
                       "scoring_flags": sorted((flags or {}).get((t["id"], r, a), []))}
                row.update(extra or {})
                rows.append(row)
                amap[opaque] = {"arm": a, "task_id": t["id"], "repeat": r, "run_id": f"run-{a}"}
    text = "".join(json.dumps(x, sort_keys=True) + "\n" for x in rows)
    (blind_dir / "candidates.jsonl").write_text(text)
    arm_map = tmp / "custodian" / "arm_map.json"
    arm_map.parent.mkdir()
    exc = [{"arm": a, "task_id": t, "repeat": r, "run_id": f"run-{a}", "outcome": "INFRA", "infra": infra,
            "reason": "INFRA_TEST"} for t, r, a, infra in excluded]
    arm_map.write_text(json.dumps({"candidates_jsonl_sha256": sa.sha256_bytes(text.encode()), "map": amap,
                                   "excluded": exc}))
    return blind_dir, arm_map, amap


class FakeRunner:
    """Writes a fake receipt (or a driver log for exit 8). ``outcome(arm, task, repeat, call_no)``
    -> label | ("rc8", reason) | dict(receipt fields)."""

    def __init__(self, amap, outcome, *, on_call=None):
        self.amap, self.outcome, self.calls, self.on_call = amap, outcome, [], on_call

    def __call__(self, cmd, log_path, work):
        arg = lambda name: cmd[cmd.index(name) + 1]  # noqa: E731
        opaque = Path(arg("--store")).name
        key, out = arg("--task"), Path(arg("--out"))
        assert "--sandbox" in cmd and arg("--sandbox") == "os" and arg("--min-free-disk-gib") == "40"
        assert not Path(work).exists()  # fresh --work per scoring
        m = self.amap[opaque]
        n = sum(1 for c in self.calls if c == opaque)
        self.calls.append(opaque)
        if self.on_call:
            self.on_call(len(self.calls))
        res = self.outcome(m["arm"], m["task_id"], m["repeat"], n)
        if isinstance(res, tuple) and res[0] == "reap_error":
            Path(log_path).write_text("ok\n")
            out_rec = out / "tasks" / key
            out_rec.mkdir(parents=True)
            (out_rec / "real_outcome.json").write_text(json.dumps({
                "scorer_version": sa.SCORER_VERSION, "runner_sandbox": "os", "env_key": ENV_KEY, "spec_sha256": SPEC,
                "runner_sandbox_profile_sha256": sa.PROFILE_SHA256, "task_key": key, "label": "RESOLVED"}))
            return {"rc": 0, "stragglers_killed": [], "reap_error": res[1]}
        if isinstance(res, tuple) and res[0] == "rc7":
            Path(log_path).write_text("no sandbox\n")
            return {"rc": 7}
        if isinstance(res, tuple) and res[0] == "rc8":
            Path(log_path).write_text(f"{key}: INFRA_ABORT {res[1]}; stopping, no receipt written\n")
            return {"rc": 8, "stragglers_killed": [{"pid": 4242, "how": "descendant"}]}
        rec = {"label": res} if isinstance(res, str) else dict(res)
        rec = {"scorer_version": sa.SCORER_VERSION, "runner_sandbox": "os", "env_key": ENV_KEY, "spec_sha256": SPEC,
               "runner_sandbox_profile_sha256": sa.PROFILE_SHA256, "task_key": key,
               "trees": {"BASE": "1" * 40, "CAND+T": "2" * 40}, **rec}
        (out / "tasks" / key).mkdir(parents=True)
        (out / "tasks" / key / "real_outcome.json").write_text(json.dumps(rec))
        Path(log_path).write_text("ok\n")
        return {"rc": 0, "stragglers_killed": []}


def run(env, blind_dir, runner, **kw):
    return sa.run_scoring(env["tmp"] / "arch", blind_dir, env["cfg"], arms_per_group=len(ARMS), runner=runner,
                          identity=env["identity"], require_lab=False, **kw)


def rows_of(arch):
    return {json.loads(p.read_text())["opaque_id"]: json.loads(p.read_text()) for p in (arch / "rows").glob("*.json")}


def simple(arm, task, repeat, n):
    return {"NEXUS": "RESOLVED", "BARE": "UNRESOLVED", "NOOP": "NO_CANDIDATE"}[arm]


# -- S4: infra re-run in all arms, then drop -------------------------------------------

def test_infra_reruns_the_task_repeat_in_all_arms_then_drops_it(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:2])
    t0 = env["tasks"][0]["id"]

    def outcome(arm, task, repeat, n):
        if task == t0 and repeat == 1 and arm == "BARE":
            return ("rc8", "host_disk_low:free=1B floor=2B (no candidate run yet)")  # persistent, pre-candidate
        if task == t0 and repeat == 2 and arm == "NEXUS" and n == 0:
            return {"label": "NOT_SCORABLE_ORACLE_INVALID", "sub_reason": "GOLD_PORT_FAILED",
                    "trees": {"BASE": "1" * 40}}  # infra once
        return simple(arm, task, repeat, n)

    runner = FakeRunner(amap, outcome)
    res = run(env, blind_dir, runner)
    by = {}
    for o in runner.calls:
        m = amap[o]
        by.setdefault((m["task_id"], m["repeat"]), {}).setdefault(m["arm"], 0)
        by[(m["task_id"], m["repeat"])][m["arm"]] += 1
    assert by[(t0, 1)] == {"BARE": 3, "NEXUS": 3, "NOOP": 3}  # 1 + 2 re-runs, every arm
    assert by[(t0, 2)] == {"BARE": 2, "NEXUS": 2, "NOOP": 2}  # infra once, re-run in all arms
    assert by[(t0, 3)] == {"BARE": 1, "NEXUS": 1, "NOOP": 1}
    assert res["groups_dropped_infra"] == 1 and res["groups_kept"] == 5
    rows = rows_of(env["tmp"] / "arch")
    dropped = [r for r in rows.values() if r["group_status"] == "DROPPED_INFRA"]
    assert {(r["task_id"], r["repeat"]) for r in dropped} == {(t0, 1)} and len(dropped) == 3
    assert all(not r["counted"] for r in dropped)
    kept_r2 = [r for r in rows.values() if (r["task_id"], r["repeat"]) == (t0, 2)]
    assert all(r["counted"] and len(r["attempts"]) == 2 for r in kept_r2)
    assert res["s42_host_disk_low_post_candidate"] == 0  # "(no candidate run yet)"-type aborts are not S4.2
    assert res["stragglers_killed_total"] == 3  # the fake reported one per rc8 attempt


def test_incomplete_group_is_dropped_from_all_arms(env):
    t = env["tasks"][0]["id"]
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], drop={(t, 2, "NEXUS")})
    res = run(env, blind_dir, FakeRunner(amap, simple))
    assert res["groups_dropped_incomplete"] == 1
    rows = rows_of(env["tmp"] / "arch")
    assert sorted(r["group_status"] for r in rows.values() if r["repeat"] == 2) == ["DROPPED_INCOMPLETE_GROUP"] * 2


def test_group_with_too_many_candidates_is_refused(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], arms=("BARE", "NEXUS", "NOOP", "X"))
    with pytest.raises(sa.Refused, match="GROUP_TOO_LARGE"):
        run(env, blind_dir, FakeRunner(amap, simple))


# -- S4.2 ---------------------------------------------------------------------------------

def test_s42_lists_post_candidate_host_disk_aborts_per_opaque_id(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:2], repeats=1)
    t0, t1 = env["tasks"][0]["id"], env["tasks"][1]["id"]
    reason = "host_disk_low:post_run_recovered_without_reap:free_before=1B reclaimed=0B floor=2B"

    def outcome(arm, task, repeat, n):
        if arm == "NEXUS" and task == t0:
            return ("rc8", reason)  # persists -> group dropped -> possible evasion
        if arm == "BARE" and task == t1 and n == 0:
            return ("rc8", "host_disk_low:free_after_reap=1B candidate_bytes=0B reclaimed=0B free_start=3 floor=2B")
        return simple(arm, task, repeat, n)

    res = run(env, blind_dir, FakeRunner(amap, outcome))
    arch = env["tmp"] / "arch"
    listing = json.loads((arch / "s42_host_disk_low.json").read_text())
    nexus_t0 = next(o for o, m in amap.items() if m["arm"] == "NEXUS" and m["task_id"] == t0)
    bare_t1 = next(o for o, m in amap.items() if m["arm"] == "BARE" and m["task_id"] == t1)
    assert [a["opaque_id"] for a in listing["aborts"]] == [nexus_t0] * 3 + [bare_t1]
    assert listing["aborts"][0]["reason"] == reason
    assert "arm" not in json.dumps(listing["aborts"]).lower().replace("alarm", "")
    (ev,) = listing["possible_evasion_groups"]
    assert ev["task_id"] == t0 and ev["possible_evasion_opaque_ids"] == [nexus_t0]
    assert res["groups_dropped_possible_evasion"] == 1
    # the listing is sealed in the manifest before any unblinding
    assert "./s42_host_disk_low.json" in (arch / "MANIFEST.sha256").read_text()


# -- S0 / S4.1 / amendment 8.3 ----------------------------------------------------------------

@pytest.mark.parametrize("flag", [sa.FLAG_OUT_OF_SCOPE, sa.FLAG_HARNESS_TAMPER])
def test_out_of_scope_or_tamper_is_not_solved_but_kept(env, flag):
    t = env["tasks"][0]["id"]
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1, flags={(t, 1, "NEXUS"): [flag]})
    run(env, blind_dir, FakeRunner(amap, simple))
    (row,) = [r for o, r in rows_of(env["tmp"] / "arch").items() if amap[o]["arm"] == "NEXUS"]
    assert row["scorer_label"] == "RESOLVED"  # stripped remainder scored, diagnostics only
    assert row["counted"] is True and row["solved"] is False and row["flag_override"] is True
    assert row["diagnostic_stripped_resolved"] is True


def test_flagged_row_infra_does_not_force_a_rerun(env):
    t = env["tasks"][0]["id"]
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1,
                                    flags={(t, 1, "NEXUS"): [sa.FLAG_HARNESS_TAMPER]})
    runner = FakeRunner(amap, lambda a, *_: ("rc8", "lsof_failed: x") if a == "NEXUS" else "UNRESOLVED")
    res = run(env, blind_dir, runner)
    assert len(runner.calls) == 3 and res["groups_kept"] == 1


@pytest.mark.parametrize("receipt,cls", [
    ({"label": "RESOLVED"}, sa.SOLVED),
    ({"label": "BROKE_EXISTING"}, sa.NOT_SOLVED),
    ({"label": "NO_CANDIDATE"}, sa.NOT_SOLVED),
    ({"label": "NOT_RUNNABLE", "sub_reason": "APPLY_FAILED"}, sa.NOT_SOLVED),  # bad patch never dropped
    ({"label": "NOT_RUNNABLE", "sub_reason": "SCRATCH_TMP_CAP_EXCEEDED"}, sa.NOT_SOLVED),
    ({"label": "NOT_RUNNABLE", "sub_reason": "ENV_FAILED"}, sa.INFRA),
    ({"label": "NOT_SCORABLE_ORACLE_INVALID", "sub_reason": "ORACLE_RUN_FAILED", "trees": {"CAND+T": "x"}},
     sa.NOT_SOLVED),  # S4.1: cap trip after the candidate
    ({"label": "NOT_SCORABLE_ORACLE_INVALID", "sub_reason": "SCRATCH_TMP_TASK_CAP_EXCEEDED",
      "trees": {"CAND+T": "x"}}, sa.NOT_SOLVED),
    ({"label": "NOT_SCORABLE_ORACLE_INVALID", "sub_reason": "ORACLE_RUN_FAILED", "trees": {}}, sa.INFRA),
    ({"label": "NOT_SCORABLE_ORACLE_INVALID", "sub_reason": "GOLD_REF_RUN_FAILED", "trees": {"CAND+T": "x"}},
     sa.INFRA),
    ({"label": "PENDING_GROUND_TRUTH"}, sa.INFRA),
])
def test_s0_mapping(receipt, cls):
    assert sa.classify_receipt(receipt)["cls"] == cls


def test_unknown_label_refuses():
    with pytest.raises(sa.Refused):
        sa.classify_receipt({"label": "SOMETHING_NEW"})


def test_receipt_with_wrong_profile_voids_the_run(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    runner = FakeRunner(amap, lambda *a: {"label": "RESOLVED", "runner_sandbox_profile_sha256": "0" * 64})
    with pytest.raises(sa.Refused, match="RECEIPT_IDENTITY_MISMATCH"):
        run(env, blind_dir, runner)


# -- identity -------------------------------------------------------------------------------

def test_refuses_when_driver_sha_does_not_match(env):
    env["identity"]()  # matches as built
    Path(env["cfg"]["driver"]).write_text("print('patched driver')\n")
    with pytest.raises(sa.Refused, match="DRIVER_SHA_MISMATCH"):
        env["identity"]()
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    with pytest.raises(sa.Refused, match="DRIVER_SHA_MISMATCH"):
        run(env, blind_dir, FakeRunner(amap, simple))
    assert not (env["tmp"] / "arch").exists()


def test_driver_change_mid_run_stops_before_the_next_scoring(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:2], repeats=1)
    env["cfg"]["concurrency"] = 1
    drv = Path(env["cfg"]["driver"])
    runner = FakeRunner(amap, simple, on_call=lambda n: n == 2 and drv.write_text("x\n"))
    with pytest.raises(sa.Refused, match="DRIVER_SHA_MISMATCH"):
        run(env, blind_dir, runner)
    assert len(runner.calls) == 2


def test_real_pins_match_the_s1_archive():
    if not sa.DEFAULTS["driver"].exists():
        pytest.skip("S1 archive not on this host")
    ident = sa.verify_identity(sa.DEFAULTS["driver"], sa.DEFAULTS["s1_archive"], sa.DEFAULTS["export"])
    assert ident["driver_sha256"] == sa.DRIVER_SHA256


def test_scorer_blob_mismatch_refuses(env):
    rel = next(iter(sa.SCORER_FILES))
    (Path(env["cfg"]["export"]) / rel).write_text("# changed\n")
    with pytest.raises(sa.Refused, match="SCORER_BLOB_MISMATCH"):
        env["identity"]()


# -- blindness ------------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [{"arm": "BARE"}, {"run_id": "m2721-x"}, {"condition": "t"}, {"note": "x"}])
def test_refuses_arm_labels_or_unknown_fields(env, extra):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1, extra=extra)
    with pytest.raises(sa.Refused, match="ARM_LABEL_IN_INPUT"):
        run(env, blind_dir, FakeRunner(amap, simple))


def test_refuses_arm_revealing_flags_and_files(env):
    t = env["tasks"][0]["id"]
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1, flags={(t, 1, "NEXUS"): ["STATE_LEAK"]})
    with pytest.raises(sa.Refused, match="ARM_LABEL_IN_INPUT"):
        run(env, blind_dir, FakeRunner(amap, simple))
    (env["tmp"] / "b2").mkdir()
    blind2, _, _ = make_blind(env["tmp"] / "b2", env["tasks"][:1], repeats=1)
    (blind2 / "arm_map.json").write_text("{}")
    with pytest.raises(sa.Refused, match="UNEXPECTED_FILE"):
        sa.load_candidates(blind2, {t})


def test_refuses_non_survivor_task_and_changed_diff(env):
    blind_dir, _, _ = make_blind(env["tmp"], [{"id": "pkg-999"}], repeats=1)
    with pytest.raises(sa.Refused, match="TASK_NOT_AN_S1_SURVIVOR"):
        sa.load_candidates(blind_dir, {"pkg-100"})
    b2 = env["tmp"] / "b2"
    b2.mkdir()
    blind2, _, amap = make_blind(b2, env["tasks"][:1], repeats=1)
    victim = next(iter(amap))
    (blind2 / "candidates" / f"{victim}.diff").write_bytes(b"tampered")
    with pytest.raises(sa.Refused, match="DIFF_SHA_MISMATCH"):
        sa.load_candidates(blind2, {env["tasks"][0]["id"]})


def test_refuses_outside_lab(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    os.environ.pop("LAB_RID", None)
    with pytest.raises(sa.Refused, match="NOT_UNDER_LAB"):
        sa.run_scoring(env["tmp"] / "arch", blind_dir, env["cfg"], arms_per_group=3,
                       runner=FakeRunner(amap, simple), identity=env["identity"])


# -- S6 create-only archive --------------------------------------------------------------

def test_archive_is_create_only_and_sealed(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    res = run(env, blind_dir, FakeRunner(amap, simple))
    arch = env["tmp"] / "arch"
    assert res["manifest_sha256"] == sa.sha256_file(arch / "MANIFEST.sha256")
    assert (arch / "MANIFEST.sha256.sha256").read_text().strip() == res["manifest_sha256"]
    assert sa.verify_archive(arch) == res["manifest_sha256"]
    with pytest.raises(sa.Refused, match="ARCHIVE_SEALED"):
        run(env, blind_dir, FakeRunner(amap, simple))
    with pytest.raises(sa.Refused, match="ARCHIVE_SEALED"):
        run(env, blind_dir, FakeRunner(amap, simple), resume=True)
    row = next((arch / "rows").glob("*.json"))
    assert stat.S_IMODE(row.stat().st_mode) == 0o444
    with pytest.raises(FileExistsError):
        sa.write_new(row, b"x")
    # tampering after sealing is detected
    os.chmod(arch / "rows", 0o755)
    os.chmod(row, 0o644)
    row.write_text("{}")
    with pytest.raises(sa.Refused, match="ARCHIVE_FILE_MODIFIED"):
        sa.verify_archive(arch)
    # per-row record carries receipt hash, diff sha256, label and identity hashes
    rec = json.loads(next(p for p in (arch / "rows").glob("*.json") if p != row).read_text())
    assert {"receipt_sha256", "diff_sha256", "scorer_label", "identity", "receipt_path"} <= set(rec)
    assert rec["identity"]["scorer_blobs"]


def test_existing_unsealed_archive_needs_resume_and_resume_reuses_finished_attempts(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    (env["tmp"] / "arch").mkdir()
    with pytest.raises(sa.Refused, match="ARCHIVE_EXISTS"):
        run(env, blind_dir, FakeRunner(amap, simple))
    import shutil
    shutil.rmtree(env["tmp"] / "arch")

    class Crash(Exception):
        pass

    first = FakeRunner(amap, simple, on_call=lambda n: (_ for _ in ()).throw(Crash()) if n == 2 else None)
    env["cfg"]["concurrency"] = 1
    with pytest.raises(Crash):
        run(env, blind_dir, first)
    crashed = first.calls[1]
    assert len(first.calls) == 2  # one task's rows run in sequence: the crash stops that batch
    second = FakeRunner(amap, simple)
    res = run(env, blind_dir, second, resume=True)
    assert second.calls[0] == crashed and first.calls[0] not in second.calls  # finished attempt reused
    assert len(second.calls) == 2 and res["rows_counted"] == 3
    adir = env["tmp"] / "arch" / "attempts" / crashed
    assert sorted(p.name for p in adir.iterdir()) == ["r0-a0", "r0-a1"]  # interrupted slot kept as is
    assert not (adir / "r0-a0" / "attempt.json").exists()


# -- S5 --------------------------------------------------------------------------------

def test_bootstrap_is_reproducible_with_the_registered_seed():
    # continuous values, so the percentile CI moves with the generator stream
    diffs = [0.137, -0.291, 0.513, 0.0071, -0.0443, 0.389, 0.211, -0.157, 0.604, 0.0919, 0.33, -0.12]
    assert sa.BOOTSTRAP_SEED == 20261020 and sa.BOOTSTRAP_RESAMPLES == 10_000
    a, b = sa.paired_bootstrap(diffs), sa.paired_bootstrap(diffs)
    assert a == b
    d = np.asarray(diffs)
    rng = np.random.default_rng(20261020)
    means = d[rng.integers(0, d.size, size=(10_000, d.size))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    assert (a["lo"], a["hi"]) == (float(lo), float(hi))
    assert sa.paired_bootstrap(diffs, seed=1) != a


def test_mcnemar_exact():
    assert sa.mcnemar_exact(1, 8) == pytest.approx(0.0390625)
    assert sa.mcnemar_exact(8, 1) == sa.mcnemar_exact(1, 8)
    assert sa.mcnemar_exact(0, 0) == 1.0
    assert sa.mcnemar_exact(0, 5) == pytest.approx(0.0625)
    assert sa.mcnemar_exact(3, 3) == 1.0


@pytest.mark.parametrize("ci,bd,band", [
    ({"n": 10, "lo": 0.01, "hi": 0.3}, 0.0, "WORKS"),
    ({"n": 10, "lo": 0.01, "hi": 0.3}, 0.05, "WORKS"),
    ({"n": 10, "lo": 0.01, "hi": 0.3}, 0.06, "NO_DETECTABLE_DIFFERENCE"),  # BROKE_EXISTING rose > 5 pp
    ({"n": 10, "lo": -0.3, "hi": -0.01}, 0.0, "HARMS"),
    ({"n": 10, "lo": -0.1, "hi": 0.2}, 0.0, "NO_DETECTABLE_DIFFERENCE"),
    ({"n": 10, "lo": 0.0, "hi": 0.2}, 0.0, "NO_DETECTABLE_DIFFERENCE"),
])
def test_decision_bands(ci, bd, band):
    assert sa.decision_band(ci, bd) == band


def _msha(env):
    return (env["tmp"] / "arch" / "MANIFEST.sha256.sha256").read_text().strip()


def _analyze(env, outcome, n_tasks=4, primary_set="M", **kw):
    blind_dir, arm_map, amap = make_blind(env["tmp"], env["tasks"][:n_tasks], **kw)
    run(env, blind_dir, FakeRunner(amap, outcome))
    strata = {t["id"]: t["set"] for t in env["tasks"]}
    return sa.analyze(env["tmp"] / "arch", arm_map, treatment="NEXUS", control="BARE", noop="NOOP", strata=strata,
                      primary_set=primary_set,
                      expect_manifest_sha=_msha(env))


def test_analyze_end_to_end_works_band_per_stratum(env):
    rep = _analyze(env, simple)
    p = rep["primary"]
    assert p["tasks"] == 2 and p["ci95"]["lo"] == p["ci95"]["hi"] == 1.0 and p["band"] == "WORKS"
    assert p["mcnemar_majority_of_3"] == {"treatment_only": 2, "control_only": 0, "p_exact": 0.5}
    assert rep["verdict"] == "WORKS" and rep["void"] == [] and rep["primary_set"] == "M"
    assert set(rep["other_sets"]) == {"LA"} and rep["other_sets"]["LA"]["tasks"] == 2
    assert rep["arms"]["NOOP"]["scorer_resolved"] == 0


def test_analyze_harms_and_broke_rate(env):
    rep = _analyze(env, lambda a, t, r, n: {"NEXUS": "BROKE_EXISTING", "BARE": "RESOLVED", "NOOP": "NO_CANDIDATE"}[a])
    assert rep["primary"]["band"] == "HARMS"
    assert rep["primary"]["broke_existing_rate"]["NEXUS"] == 1.0 and rep["primary"]["broke_existing_rate"]["BARE"] == 0


def test_noop_resolved_voids_the_run(env):
    def outcome(arm, task, repeat, n):
        return "RESOLVED" if (arm == "NOOP" and repeat == 2 and task == "pkg-101") else simple(arm, task, repeat, n)

    rep = _analyze(env, outcome)
    assert rep["verdict"] == "VOID" and len(rep["void"][0]["opaque_ids"]) == 1


def test_noop_tampered_resolved_still_voids(env):
    # a RESOLVED scorer label in the NOOP arm voids even when a flag overrides the solve
    rep = _analyze(env, lambda a, t, r, n: "RESOLVED" if a == "NOOP" else "UNRESOLVED", n_tasks=1, repeats=1,
                   flags={("pkg-100", 1, "NOOP"): [sa.FLAG_HARNESS_TAMPER]})
    assert rep["verdict"] == "VOID"


def test_analyze_refuses_a_foreign_arm_map(env):
    blind_dir, arm_map, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    run(env, blind_dir, FakeRunner(amap, simple))
    data = json.loads(arm_map.read_text())
    data["candidates_jsonl_sha256"] = "0" * 64
    arm_map.write_text(json.dumps(data))
    with pytest.raises(sa.Refused, match="ARM_MAP_NOT_FOR_THIS_CANDIDATE_SET"):
        sa.analyze(env["tmp"] / "arch", arm_map, treatment="NEXUS", control="BARE", noop="NOOP",
                   strata={t["id"]: t["set"] for t in env["tasks"]}, primary_set="M", expect_manifest_sha=_msha(env))


def test_possible_evasion_on_one_arm_is_reported_with_and_without(env):
    reason = "host_disk_low:post_run_recovered_without_reap:free_before=1B reclaimed=0B floor=2B"

    def outcome(arm, task, repeat, n):
        if arm == "NEXUS" and task == "pkg-100" and repeat == 1:
            return ("rc8", reason)
        return simple(arm, task, repeat, n)

    rep = _analyze(env, outcome)
    assert rep["drops"]["possible_evasion_by_arm"] == {"NEXUS": 1}
    alt = rep["primary_with_possible_evasion_groups"]
    assert alt is not None and alt["tasks"] == 2
    assert alt["solve_rate"]["NEXUS"] < rep["primary"]["solve_rate"]["NEXUS"]


def test_majority_uses_kept_repeats_only(env):
    # pkg-100 repeat 3 dropped from all arms: majority over 2 kept repeats (1 of 2 is not a majority)
    def outcome(arm, task, repeat, n):
        if task == "pkg-100" and repeat == 3:
            return ("rc8", "lsof_failed: x")
        if task == "pkg-100" and arm == "NEXUS":
            return "RESOLVED" if repeat == 1 else "UNRESOLVED"
        return "UNRESOLVED" if arm != "NOOP" else "NO_CANDIDATE"

    rep = _analyze(env, outcome)
    assert rep["drops"]["infra"] == 1
    assert rep["primary"]["mcnemar_majority_of_3"]["treatment_only"] == 0
    assert rep["primary"]["ci95"]["mean"] == pytest.approx(0.5 / 2)


# -- S2.1(c): per-run straggler reaping (real processes, no scorer) ---------------------

@pytest.mark.skipif(not Path("/usr/sbin/lsof").exists() or not Path("/bin/ps").exists(), reason="macOS tools")
def test_run_tracked_kills_and_records_a_setsid_straggler(tmp_path):
    import sys
    import time

    work = tmp_path / "work"
    work.mkdir()
    pidfile = tmp_path / "daemon.pid"
    code = (
        "import os, sys, time\n"
        "if os.fork() == 0:\n"
        "    os.setsid()\n"
        f"    os.chdir({str(work)!r})\n"
        f"    open({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "    time.sleep(120)\n"
        "    os._exit(0)\n"
        "time.sleep(1.5)\n"
    )
    res = sa.run_tracked([sys.executable, "-c", code], tmp_path / "log.txt", work, poll=0.1)
    pid = int(pidfile.read_text())
    assert res["rc"] == 0
    assert pid in {k.get("pid") for k in res["stragglers_killed"]}
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            break
        time.sleep(0.1)
    else:
        pytest.fail("straggler still alive")



# -- review round 2 (REJECT of fa10d9f15) ---------------------------------------------------

def test_run_invalid_and_patch_does_not_apply_are_not_solved_but_kept(env):
    t = env["tasks"][0]["id"]
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=2,
                                    flags={(t, 1, "NEXUS"): [sa.FLAG_RUN_INVALID],
                                           (t, 2, "NEXUS"): [sa.FLAG_PATCH_DOES_NOT_APPLY]})
    res = run(env, blind_dir, FakeRunner(amap, simple))
    assert res["groups_kept"] == 2 and res["groups_dropped_incomplete"] == 0
    nexus = [r for o, r in rows_of(env["tmp"] / "arch").items() if amap[o]["arm"] == "NEXUS"]
    assert len(nexus) == 2 and all(r["counted"] and r["solved"] is False and r["flag_override"] for r in nexus)


def test_blind_keeps_non_infra_invalid_rows_as_flagged_candidates(tmp_path, monkeypatch):
    from scripts.bench.measure_2721 import blind

    monkeypatch.setattr(blind, "applies_to_base", lambda diff, task: True)
    task = {"task_id": "pkg-100", "scope": ["x.py"]}
    diff = tmp_path / "d.diff"
    diff.write_text("")
    base = {"task_id": "pkg-100", "repeat": 1, "diff_path": str(diff), "diff_sha256": sa.sha256_bytes(b"")}
    rows = [{**base, "arm": "BARE", "run_id": "b", "outcome": "TAMPERED"},
            {**base, "arm": "NEXUS", "run_id": "n", "outcome": "GATEWAY_ERROR"},
            {**base, "arm": "NEXUS", "run_id": "n2", "outcome": "OK", "flags": ["STATE_LEAK"], "repeat": 2},
            {**base, "arm": "BARE", "run_id": "b2", "outcome": "OK", "void_reason": "X", "repeat": 2},
            {**base, "arm": "NOOP", "run_id": "z", "outcome": "INFRA", "infra": True, "void_reason": "agy"}]
    out, amap_path = tmp_path / "o", tmp_path / "c" / "m.json"
    blind.blind(rows, out, amap_path, {"pkg-100": task})
    cands = [json.loads(line) for line in (out / "candidates.jsonl").read_text().splitlines()]
    assert len(cands) == 4 and all(c["scoring_flags"] == ["RUN_INVALID_NOT_SOLVED"] for c in cands)
    amap = json.loads(amap_path.read_text())
    assert amap["excluded"] == [{"arm": "NOOP", "run_id": "z", "task_id": "pkg-100", "repeat": 1,
                                 "outcome": "INFRA", "infra": True, "reason": "agy"}]
    assert "STATE_LEAK" not in (out / "candidates.jsonl").read_text()


def test_blind_writes_diff_files_after_the_shuffle(tmp_path, monkeypatch):
    from scripts.bench.measure_2721 import blind

    class Reverse:
        def shuffle(self, items):
            items.reverse()

    written = []
    monkeypatch.setattr(blind, "applies_to_base", lambda diff, task: True)
    monkeypatch.setattr(blind.secrets, "SystemRandom", Reverse)
    monkeypatch.setattr(blind, "write_diff", lambda path, diff: written.append(Path(path).stem))
    task = {"task_id": "pkg-100", "scope": ["x.py"]}
    rows = []
    for i in range(4):
        d = tmp_path / f"{i}.diff"
        d.write_text("")
        rows.append({"task_id": "pkg-100", "repeat": i + 1, "arm": ARMS[i % 3], "run_id": str(i), "outcome": "OK",
                     "diff_path": str(d), "diff_sha256": sa.sha256_bytes(b"")})
    blind.blind(rows, tmp_path / "o", tmp_path / "c" / "m.json", {"pkg-100": task})
    order = [json.loads(line)["opaque_id"] for line in (tmp_path / "o" / "candidates.jsonl").read_text().splitlines()]
    processing = list(reversed(order))
    assert written == order != processing  # created in the shuffled order, not arm/processing order


def test_rows_of_one_task_are_never_co_scheduled(env):
    import threading
    import time as _t

    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"], repeats=2)
    env["cfg"]["concurrency"] = 4
    live: dict[str, int] = {}
    lock = threading.Lock()
    clash, peak = [], [0]

    class Slow(FakeRunner):
        def __call__(self, cmd, log_path, work):
            task = self.amap[Path(cmd[cmd.index("--store") + 1]).name]["task_id"]
            with lock:
                live[task] = live.get(task, 0) + 1
                if live[task] > 1:
                    clash.append(task)
                peak[0] = max(peak[0], sum(live.values()))
            _t.sleep(0.02)
            try:
                return super().__call__(cmd, log_path, work)
            finally:
                with lock:
                    live[task] -= 1

    run(env, blind_dir, Slow(amap, simple))
    assert clash == [] and peak[0] > 1  # parallel across tasks, never within one
    assert json.loads((env["tmp"] / "arch" / "run.json").read_text())["concurrency"] == 4


def test_cli_concurrency_defaults_to_one():
    seen = {}
    orig = sa.run_scoring
    try:
        sa.run_scoring = lambda *a, **k: seen.update(cfg=a[2]) or {}
        sa.main(["run", "--blind-dir", "b", "--archive", "a", "--arms-per-group", "3", "--allow-outside-lab"])
    finally:
        sa.run_scoring = orig
    assert seen["cfg"]["concurrency"] == 1


def test_primary_verdict_is_on_the_declared_set_only(env):
    # M tasks (pkg-100, pkg-102): no difference; LA tasks: NEXUS solves everything
    def outcome(arm, task, repeat, n):
        if arm == "NOOP":
            return "NO_CANDIDATE"
        if task in ("pkg-101", "pkg-103") and arm == "NEXUS":
            return "RESOLVED"
        return "UNRESOLVED"

    rep = _analyze(env, outcome)
    assert rep["primary"]["tasks"] == 2 and rep["verdict"] == "NO_DETECTABLE_DIFFERENCE"
    assert rep["other_sets"]["LA"]["band"] == "WORKS"


def test_analyze_refuses_unknown_task_set_or_primary_set(env):
    blind_dir, arm_map, amap = make_blind(env["tmp"], env["tasks"][:2], repeats=1)
    run(env, blind_dir, FakeRunner(amap, simple))
    kw = dict(treatment="NEXUS", control="BARE", noop="NOOP", expect_manifest_sha=_msha(env))
    with pytest.raises(sa.Refused, match="TASK_SET_UNKNOWN"):
        sa.analyze(env["tmp"] / "arch", arm_map, strata={"pkg-100": "M"}, primary_set="M", **kw)
    with pytest.raises(sa.Refused, match="PRIMARY_SET_UNKNOWN"):
        sa.analyze(env["tmp"] / "arch", arm_map, strata={"pkg-100": "M", "pkg-101": "LA"}, primary_set="LB", **kw)


def test_analyze_custody_requires_manifest_sha_and_noop(env):
    blind_dir, arm_map, amap = make_blind(env["tmp"], env["tasks"][:2], repeats=1)
    run(env, blind_dir, FakeRunner(amap, simple))
    strata = {"pkg-100": "M", "pkg-101": "LA"}
    with pytest.raises(sa.Refused, match="EXPECT_MANIFEST_SHA_REQUIRED"):
        sa.analyze(env["tmp"] / "arch", arm_map, treatment="NEXUS", control="BARE", noop="NOOP", strata=strata,
                   primary_set="M", expect_manifest_sha="")
    with pytest.raises(sa.Refused, match="NOOP_REQUIRED"):
        sa.analyze(env["tmp"] / "arch", arm_map, treatment="NEXUS", control="BARE", noop=None, strata=strata,
                   primary_set="M", expect_manifest_sha=_msha(env))
    with pytest.raises(SystemExit):
        sa.main(["analyze", "--archive", "a", "--arm-map", "m", "--treatment", "NEXUS", "--control", "BARE",
                 "--primary-set", "M"])


def test_noop_resolved_in_an_earlier_round_voids(env):
    def outcome(arm, task, repeat, n):
        if task == "pkg-100" and repeat == 1:
            if arm == "BARE" and n == 0:
                return ("rc8", "lsof_failed: x")  # forces a second round of the group
            if arm == "NOOP":
                return "RESOLVED" if n == 0 else "NO_CANDIDATE"
        return simple(arm, task, repeat, n)

    rep = _analyze(env, outcome, n_tasks=1)
    assert rep["verdict"] == "VOID"


def test_noop_resolved_in_an_incomplete_group_voids(env):
    rep = _analyze(env, lambda a, t, r, n: "RESOLVED" if a == "NOOP" and r == 2 else simple(a, t, r, n), n_tasks=1,
                   drop={("pkg-100", 2, "BARE")}, excluded=[("pkg-100", 2, "BARE", True)])
    assert rep["drops"]["incomplete_group"] == 1 and rep["verdict"] == "VOID"


def test_incomplete_groups_are_cross_checked_against_the_arm_map(env):
    rep = _analyze(env, simple, n_tasks=1, drop={("pkg-100", 2, "BARE")}, excluded=[("pkg-100", 2, "BARE", True)])
    assert rep["drops"]["incomplete_groups_by_arm"] == [
        {"task_id": "pkg-100", "repeat": 2, "excluded_by_arm": {"BARE": "INFRA_TEST"}}]
    assert rep["drops"]["exclusions_by_arm"] == {"BARE": {"INFRA_TEST": 1}}


@pytest.mark.parametrize("excluded,match", [([], "INCOMPLETE_GROUP_UNEXPLAINED"),
                                            ([("pkg-100", 2, "BARE", False)], "NON_INFRA_EXCLUSION")])
def test_incomplete_group_without_an_infra_exclusion_refuses(env, excluded, match):
    with pytest.raises(sa.Refused, match=match):
        _analyze(env, simple, n_tasks=1, drop={("pkg-100", 2, "BARE")}, excluded=excluded)


def test_env_key_or_spec_mismatch_with_s1_stops(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    with pytest.raises(sa.Refused, match="RECEIPT_IDENTITY_MISMATCH.*env_key"):
        run(env, blind_dir, FakeRunner(amap, lambda *a: {"label": "RESOLVED", "env_key": "f" * 64}))


def test_missing_s1_reference_stops(env):
    import shutil

    shutil.rmtree(Path(env["cfg"]["s1_receipts"]))
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    with pytest.raises(sa.Refused, match="S1_REFERENCE_MISSING"):
        run(env, blind_dir, FakeRunner(amap, simple))


def test_resume_after_a_fatal_exit(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    env["cfg"]["concurrency"] = 1
    first = FakeRunner(amap, lambda a, *r: ("rc7",) if a == "NEXUS" else simple(a, *r))
    with pytest.raises(sa.Refused, match="SCORER_FATAL"):
        run(env, blind_dir, first)
    res = run(env, blind_dir, FakeRunner(amap, simple), resume=True)
    assert res["rows_counted"] == 3


def test_macro_solve_rate_matches_the_ci_and_pooled_is_labelled(env):
    # pkg-100: NEXUS 3/3 kept; pkg-102: only repeat 1 kept (2 and 3 dropped), NEXUS 0/1
    def outcome(arm, task, repeat, n):
        if task == "pkg-102" and repeat > 1:
            return ("rc8", "lsof_failed: x")
        if arm == "NEXUS":
            return "RESOLVED" if task == "pkg-100" else "UNRESOLVED"
        return "UNRESOLVED" if arm == "BARE" else "NO_CANDIDATE"

    rep = _analyze(env, outcome, n_tasks=3)
    p = rep["primary"]
    assert p["solve_rate"]["NEXUS"] == pytest.approx(0.5) == p["ci95"]["mean"]
    assert p["solve_rate_pooled_rows"]["NEXUS"] == pytest.approx(0.75)


def test_reap_error_is_infra_and_recorded(env):
    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    res = run(env, blind_dir, FakeRunner(amap, lambda a, *r: ("reap_error", "lsof_failed: boom") if a == "BARE"
                                         else simple(a, *r)))
    assert res["groups_dropped_infra"] == 1
    (bare,) = [r for o, r in rows_of(env["tmp"] / "arch").items() if amap[o]["arm"] == "BARE"]
    assert bare["why"].startswith("REAP_FAILED:lsof_failed") and bare["scorer_label"] == "RESOLVED"


def test_cwd_holders_fails_closed(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise OSError("no lsof")

    monkeypatch.setattr(sa.subprocess, "run", boom)
    with pytest.raises(sa.ReapError, match="lsof_failed"):
        sa._cwd_holders(tmp_path)

    class Empty:
        stdout, stderr, returncode = "", "denied", 1

    monkeypatch.setattr(sa.subprocess, "run", lambda *a, **k: Empty())
    with pytest.raises(sa.ReapError, match="lsof_no_output"):
        sa._cwd_holders(tmp_path)


def test_final_label_is_from_the_last_round(env):
    def outcome(arm, task, repeat, n):
        if arm == "BARE" and n == 0:
            return ("rc8", "lsof_failed: x")
        if arm == "NEXUS":
            return "RESOLVED" if n == 0 else "UNRESOLVED"
        return simple(arm, task, repeat, n)

    blind_dir, _, amap = make_blind(env["tmp"], env["tasks"][:1], repeats=1)
    run(env, blind_dir, FakeRunner(amap, outcome))
    (nexus,) = [r for o, r in rows_of(env["tmp"] / "arch").items() if amap[o]["arm"] == "NEXUS"]
    assert nexus["scorer_label"] == "UNRESOLVED" and nexus["solved"] is False
    assert nexus["round_labels"] == ["RESOLVED", "UNRESOLVED"]


def test_two_sided_possible_evasion_gives_no_with_report(env):
    reason = "host_disk_low:post_run_recovered_without_reap:free_before=1B reclaimed=0B floor=2B"

    def outcome(arm, task, repeat, n):
        if (arm, task, repeat) in (("NEXUS", "pkg-100", 1), ("BARE", "pkg-102", 1)):
            return ("rc8", reason)
        return simple(arm, task, repeat, n)

    rep = _analyze(env, outcome)
    assert rep["drops"]["possible_evasion_by_arm"] == {"NEXUS": 1, "BARE": 1}
    assert rep["primary_with_possible_evasion_groups"] is None


def test_incomplete_group_rows_are_never_counted(env):
    # NEXUS solves everything; its repeat-2 row sits in an incomplete group (BARE excluded as infra)
    rep = _analyze(env, simple, n_tasks=1, drop={("pkg-100", 2, "BARE")}, excluded=[("pkg-100", 2, "BARE", True)])
    rows = rows_of(env["tmp"] / "arch")
    inc = [r for r in rows.values() if r["group_status"] == "DROPPED_INCOMPLETE_GROUP"]
    assert len(inc) == 2 and all(r["counted"] is False and r["solved"] is None for r in inc)
    assert rep["arms"]["NEXUS"] == {**rep["arms"]["NEXUS"], "rows": 3, "counted": 2, "solved": 2, "dropped": 1}
    assert rep["arms"]["NOOP"]["counted"] == 2 and rep["arms"]["BARE"]["counted"] == 2
    p = rep["primary"]
    assert p["tasks"] == 1 and p["solve_rate_pooled_rows"]["NEXUS"] == 1.0
    assert p["broke_existing_rate"]["NEXUS"] == 0.0
