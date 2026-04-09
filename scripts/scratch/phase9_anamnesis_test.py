#!/usr/bin/env python3
"""
🧪 Phase 9 Anamnesis Stress Test
驗證：
1. S7: 記憶召回注入 (Prior Wisdom)
2. S8: 高信號截斷 (Traceback -> 4000 lines)
3. S9: 低信號壓縮 (Repetitive -> 500 lines)
4. S10: 深呼吸觀察 (Grep injection in Round 3)
"""
import sys
import os
from pathlib import Path
import subprocess
import json

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.engine.output_guard import truncate_output, _classify_output_density
from scripts.ops.autonomous_repair_loop import _recall_prior_wisdom, _deep_breath
from nexus.services.memory import MemoryService, FaultLesson

def test_semantic_guard():
    print("\n--- [S8/S9] Testing Semantic Guard ---")
    
    # High Signal: Traceback (Exceed 4000 lines)
    high_text = "Traceback (most recent call last):\n  File 'main.py', line 10\n    1/0\nZeroDivisionError: division by zero\n" + ("Normal line\n" * 5000)
    density_h = _classify_output_density(high_text)
    print(f"High Signal Density Result: {density_h}")
    assert density_h == "HIGH_SIGNAL"
    
    out_h = truncate_output(high_text, "test_high")
    print(f"High Signal Truncation Head: {out_h.splitlines()[1]}")
    assert "HIGH_SIGNAL" in out_h

    # Low Signal: Repetitive
    low_text = ("Duplicate warning line\n" * 2000)
    density_l = _classify_output_density(low_text)
    print(f"Low Signal Density Result: {density_l}")
    assert density_l == "LOW_SIGNAL"
    
    out_l = truncate_output(low_text, "test_low")
    print(f"Low Signal Truncation Head: {out_l.splitlines()[1]}")
    assert "LOW_SIGNAL" in out_l


def test_anamnesis_recall():
    print("\n--- [S7] Testing Anamnesis Recall ---")
    mem = MemoryService(str(ROOT))
    
    # Inject a fake lesson
    test_fault = "ZeroDivisionError: division by zero"
    lesson = FaultLesson(
        fault_hash=test_fault,
        error_type="healing_success",
        diagnosis_kind="R",
        lesson="Don't divide by zero, check the denominator.",
        repair_patch="if den != 0: ...",
        audit_pass_rate=1.0
    )
    mem.record_fault_lesson(lesson)
    
    # Try reaching it
    wisdom = _recall_prior_wisdom(test_fault, mem)
    print(f"Recalled Wisdom: {wisdom}")
    assert "PRIOR WISDOM" in wisdom
    assert "denominator" in wisdom


def test_deep_breath_observation():
    print("\n--- [S10] Testing Deep Breath Observation ---")
    # Use a symbol that is definitely in the failing context and the repo
    context = "Error: ContextHub failed to initialize"
    
    obs = _deep_breath(context, ROOT)
    print(f"Observation Result (first 200 chars): {obs[:200]}...")
    assert "OBSERVATION CONTEXT" in obs
    assert "ContextHub" in obs


if __name__ == "__main__":
    print("🚀 Running Phase 9 Physical Verification...")
    try:
        test_semantic_guard()
        test_anamnesis_recall()
        test_deep_breath_observation()
        print("\n✅ All Anamnesis tests PASSED.")
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
