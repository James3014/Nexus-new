from typing import Any, Dict, List, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)

class UIBudgetEnforcer:
    """🎨 [Wave 2] UI Budget: Physical UI constraints"""
    
    def __init__(self, max_font_size: int = 18, max_colors: int = 4):
        self.max_font_size = max_font_size
        self.max_colors = max_colors

    def audit_css(self, css_text: str) -> Dict[str, Any]:
        """審計 CSS 是否符合視覺預算內容內容內容及性能"""
        violations = []
        
        # 1. 檢測字體過大 (UI Bloat)
        fonts = re.findall(r"font-size:\s*(\d+)px", css_text)
        for f in fonts:
            if int(f) > self.max_font_size:
                violations.append(f"FONT_LIMIT: Found font-size {f}px (Max: {self.max_font_size})")
        
        # 2. 檢測顏色過多 (Cohesion violation)
        colors = set(re.findall(r"#[0-9a-fA-F]{3,6}|rgba\(.*?\)|rgb\(.*?\)", css_text))
        if len(colors) > self.max_colors:
             violations.append(f"COLOR_LIMIT: Found {len(colors)} unique colors (Max: {self.max_colors})")
             
        is_vetoed = len(violations) > 0
        return {
            "status": "VETOED" if is_vetoed else "PASS",
            "violations": violations,
            "colors_found": list(colors)
        }
