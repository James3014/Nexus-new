import difflib
from pathlib import Path
from typing import List, Tuple
from dataclasses import dataclass
from nexus.services.local_heal.protocol import SolidSearchReplaceProtocol, SyntaxGate
from nexus.services.local_heal.validator import validate_effective_change, validate_name_sanity
from nexus.services.local_heal.errors import PatchError

@dataclass
class PatchApplicationResult:
    success: bool
    applied_diffs: List[str]
    error_reason: str | None = None
    syntax_gate_passed: bool = True

class PatchApplier:
    """多重關卡修補套用與驗證器 - 依據 Linus 切小與關注點分離原則"""

    def __init__(self, parser: SolidSearchReplaceProtocol, patcher):
        self.parser = parser
        self.patcher = patcher

    def apply_and_validate(
        self,
        intents: list,
        repo_dir: Path,
        localized_files: List[Tuple[str, str]]
    ) -> PatchApplicationResult:
        applied_diffs = []
        syntax_gate_passed = True

        for intent in intents:
            target_path = repo_dir / intent.file_path
            
            # 輔助：處理相對路徑與模糊匹配
            if not target_path.exists():
                found = list(repo_dir.rglob(Path(intent.file_path).name))
                if found:
                    target_path = found[0]

            if not target_path.exists():
                return PatchApplicationResult(
                    success=False,
                    applied_diffs=applied_diffs,
                    error_reason=f"FILE_NOT_FOUND:{intent.file_path}"
                )

            source_text = target_path.read_text(encoding="utf-8", errors="replace")

            # A. [MatchGate] 逐字匹配與占位符阻斷
            match_res = self.parser.validate(intent, source_text)
            if not match_res.is_valid:
                # P0-3b: Cross-file SEARCH fallback
                corrected = False
                for alt_rel_path, alt_content_unused in localized_files:
                    alt_path = repo_dir / alt_rel_path
                    if not alt_path.exists() or alt_path == target_path:
                        continue
                    alt_text = alt_path.read_text(encoding="utf-8", errors="replace")
                    alt_res = self.parser.validate(intent, alt_text)
                    if alt_res.is_valid:
                        # 找到正確的目標檔案 — 自動修正意圖與變數並繼續
                        intent = type(intent)(
                            file_path=alt_rel_path,
                            search=intent.search,
                            replace=intent.replace,
                            operation=intent.operation,
                        )
                        target_path = alt_path
                        source_text = alt_text
                        match_res = alt_res
                        corrected = True
                        break
                if not corrected:
                    return PatchApplicationResult(
                        success=False,
                        applied_diffs=applied_diffs,
                        error_reason=match_res.error.kind.name
                    )

            # B. [SyntaxGate] 語法編譯檢查 (ast.parse)
            syntax_res = SyntaxGate.check(intent, source_text)
            syntax_gate_passed = syntax_res.is_valid
            if not syntax_res.is_valid:
                return PatchApplicationResult(
                    success=False,
                    applied_diffs=applied_diffs,
                    error_reason=syntax_res.error.kind.name,
                    syntax_gate_passed=False
                )

            # C. [SemanticsGate] 語意安全檢查 (空改動與 NameSanity)
            patched_content = source_text.replace(intent.search, intent.replace)
            
            is_effective, eff_err = validate_effective_change(source_text, patched_content)
            if not is_effective:
                return PatchApplicationResult(
                    success=False,
                    applied_diffs=applied_diffs,
                    error_reason="NO_EFFECTIVE_CHANGE"
                )

            is_sane, sane_err = validate_name_sanity(patched_content)
            if not is_sane:
                return PatchApplicationResult(
                    success=False,
                    applied_diffs=applied_diffs,
                    error_reason="NAME_SANITY_ERROR"
                )

            # D. 寫入檔案與紀錄 unified diff
            target_path.write_text(patched_content, encoding="utf-8")
            diff = self._build_file_diff(intent.file_path, source_text, patched_content)
            applied_diffs.append(diff)

        return PatchApplicationResult(
            success=True,
            applied_diffs=applied_diffs,
            syntax_gate_passed=syntax_gate_passed
        )

    def _build_file_diff(self, relative_path: str, old_content: str, new_content: str) -> str:
        return "".join(difflib.unified_diff(
            old_content.splitlines(keepends=True),
            new_content.splitlines(keepends=True),
            fromfile=f"a/{relative_path}",
            tofile=f"b/{relative_path}",
            lineterm="\n",
        ))
