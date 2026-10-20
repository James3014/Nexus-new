"""L-B state contrast for #2721 (PREREG v0.9.9, layer1-rie 2026-10-21).

L-B runs once per Nexus state (LEARN, COLD, IRRELEVANT), each in its own run
root with BARE + NEXUS, blinded and scored on its own (``score_arms.py``).  The
state contrast is computed here, after unblinding, with the registered formula:

* only the NEXUS rows of each run root, ``counted`` ones (the scorer's rule);
* pairs are (task, repeat) present in both states; per task the mean solve rate
  over its paired repeats in each state; the per-task difference is
  ``LEARN - <other>``;
* percentile 95% CI of the mean difference by paired bootstrap, 10,000
  resamples, ``numpy.random.default_rng(20261020)`` (``score_arms.paired_bootstrap``);
* primary: LEARN - COLD; secondary: LEARN - IRRELEVANT; every result is
  labelled ``cards-only`` (Q2 measures the findings cards, no Belief writeback).

Each run root must first pass ``score_arms.analyze`` (archive and arm map
verified, NEXUS vs BARE): a void or refused run root refuses the contrast.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts.bench.measure_2721 import score_arms as sa

SCHEMA = "nexus.measure_2721.lb_contrast.v1"
LABEL = "cards-only"
TREATMENT, CONTROL = "NEXUS", "BARE"


def state_rows(arch: Path, arm_map_path: Path, *, strata: Mapping[str, str], primary_set: str,
               expect_manifest_sha: str) -> list[dict[str, Any]]:
    """The counted NEXUS rows of one state's run root, after its own full analysis."""
    report = sa.analyze(arch, arm_map_path, treatment=TREATMENT, control=CONTROL, noop=None, strata=strata,
                        primary_set=primary_set, expect_manifest_sha=expect_manifest_sha)
    if report["void"]:
        raise sa.Refused(f"STATE_RUN_VOID {arch}: {report['void']}")
    amap = json.loads(Path(arm_map_path).read_text())
    rows = []
    for path in sorted((Path(arch) / "rows").glob("*.json")):
        row = json.loads(path.read_text())
        mapped = amap["map"][row["opaque_id"]]
        if mapped["arm"] == TREATMENT and row["counted"]:
            rows.append({"task_id": row["task_id"], "repeat": int(row["repeat"]), "solved": bool(row["solved"])})
    return rows


def contrast(learn: Sequence[Mapping[str, Any]], other: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """LEARN - other on (task, repeat) pairs present in both; per-task means; paired bootstrap."""
    a = {(r["task_id"], r["repeat"]): r["solved"] for r in learn}
    b = {(r["task_id"], r["repeat"]): r["solved"] for r in other}
    per_task: dict[str, list[tuple[bool, bool]]] = {}
    for key in sorted(set(a) & set(b)):
        per_task.setdefault(key[0], []).append((a[key], b[key]))
    diffs = [sum(x for x, _ in pairs) / len(pairs) - sum(y for _, y in pairs) / len(pairs)
             for _, pairs in sorted(per_task.items())]
    return {"ci95": sa.paired_bootstrap(diffs), "tasks": len(per_task),
            "pairs": sum(len(p) for p in per_task.values()),
            "unpaired": len(set(a) ^ set(b)), "label": LABEL}


def main(argv: Sequence[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    for state in ("learn", "cold", "irrelevant"):
        p.add_argument(f"--{state}", nargs=3, metavar=("ARCHIVE", "ARM_MAP", "MANIFEST_SHA256"),
                       required=state != "irrelevant", help=f"the {state.upper()} run root's scoring archive")
    p.add_argument("--s1-result", type=Path, default=sa.DEFAULTS["s1_result"])
    p.add_argument("--primary-set", default="LB")
    p.add_argument("--out", type=Path, help="write the report here (create-only)")
    args = p.parse_args(argv)
    try:
        s1 = json.loads(Path(args.s1_result).read_text())
        strata = {row["id"]: row["set"] for row in s1["rows"] if row.get("survives")}
        rows = {state: state_rows(Path(spec[0]), Path(spec[1]), strata=strata, primary_set=args.primary_set,
                                  expect_manifest_sha=spec[2])
                for state in ("learn", "cold", "irrelevant") if (spec := getattr(args, state))}
        report = {"schema": SCHEMA, "seed": sa.BOOTSTRAP_SEED, "resamples": sa.BOOTSTRAP_RESAMPLES,
                  "primary": {"contrast": "LEARN-COLD", **contrast(rows["learn"], rows["cold"])}}
        if "irrelevant" in rows:
            report["secondary"] = {"contrast": "LEARN-IRRELEVANT", **contrast(rows["learn"], rows["irrelevant"])}
    except sa.Refused as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=1, sort_keys=True)
    if args.out:
        sa.write_new(args.out, (text + "\n").encode())
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
