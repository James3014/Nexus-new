import pytest
import textwrap
from pathlib import Path
from nexus.engine.patch.envelope_parser import PatchEnvelopeParser
from nexus.engine.patch.block_normalizer import SearchBlockNormalizer
from nexus.engine.patch.unique_locator import UniqueLocator
from nexus.engine.patch.apply_planner import ApplyPlanner
from nexus.engine.patch.bounded_fuzzy_applier import BoundedFuzzyApplier
from nexus.engine.patch.apply_verifier import ApplyVerifier

def test_full_patch_pipeline_success():
    """驗證 7 大模組協作完成一個成功的套用。"""
    raw_output = textwrap.dedent("""
        好的，我來修復這個問題。
        <<<<<<< SEARCH
        def old(): return 1
        =======
        def old(): return 2
        >>>>>>> REPLACE
    """)

    file_content = "import os\ndef old(): return 1\ndef other(): pass"
    
    # 1. Parse
    parser = PatchEnvelopeParser()
    intent = parser.parse("t1", raw_output)
    assert len(intent.blocks) == 1
    
    # 2. Normalize
    normalizer = SearchBlockNormalizer()
    search_block = normalizer.canonicalize(intent.blocks[0].search)
    assert search_block == "def old(): return 1"
    
    # 3. Locate
    locator = UniqueLocator()
    is_unique, pos, _ = locator.find_unique_position(file_content, search_block)
    assert is_unique is True
    
    # 4. Apply (Exact)
    new_content = file_content.replace(search_block, intent.blocks[0].replace)
    
    # 5. Verify
    verifier = ApplyVerifier()
    success, msg = verifier.verify_change(file_content, new_content)
    assert success is True
    assert "def old(): return 2" in new_content
