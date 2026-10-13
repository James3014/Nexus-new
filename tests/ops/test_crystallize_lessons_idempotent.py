import json

from scripts.ops.crystallize_lessons import crystallize


def test_crystallize_appends_fixed_belief_once(tmp_path):
    (tmp_path / ".codex_lessons.md").write_text("- lesson\n", encoding="utf-8")
    knowledge = tmp_path / ".nexusknowledge"
    knowledge.mkdir()

    crystallize(tmp_path)
    crystallize(tmp_path)

    beliefs = [json.loads(line) for line in (knowledge / "beliefs.jsonl").read_text().splitlines()]
    proposals = (knowledge / "reconciliation_proposals.jsonl").read_text().splitlines()
    assert [b["belief_id"] for b in beliefs] == ["B-FED-SINGULARITY-001"]
    assert len(proposals) == 1
