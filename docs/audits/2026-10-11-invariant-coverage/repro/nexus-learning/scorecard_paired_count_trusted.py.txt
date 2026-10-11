"""Repro: build_adoption_from_scorecard trusts scorecard['paired_memory_uplift'] counts
(eligible / eligible_fingerprints) instead of recomputing paired_memory_uplift(rows).
One genuine pair + an edited count crosses min_eligible_pairs=3 and yields ADOPT."""
import sys, copy
sys.path.insert(0, "/home/user/nexus-learning"); sys.path.insert(0, "/home/user/nexus-learning/tests")
from test_adoption import attempt, decide            # fixture rows from the repo's own tests
from nexus_learning.effectiveness_measurement import replay_scorecard

rows = [attempt("fp-1", "memory_off", False), attempt("fp-1", "memory_on", True)]
genuine = replay_scorecard(rows)
print("genuine eligible pairs:", genuine["paired_memory_uplift"]["eligible"])
r = decide(genuine)
print("genuine decision:", r["decision"], r["reason_codes"])
forged = copy.deepcopy(genuine)
forged["paired_memory_uplift"].update(eligible=3, eligible_pairs=3, numerator=3, denominator=3)
r = decide(forged)
print("edited-count decision:", r["decision"], r["reason_codes"], "| uplift_summary:", r["uplift_summary"])
