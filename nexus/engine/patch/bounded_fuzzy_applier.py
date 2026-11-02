from typing import List, Tuple


def _split_lines(content: str) -> List[str]:
    # 只在 "\n" 切行，行尾的 "\r" 留在該行，才能原樣寫回檔案本來的換行。
    return content.split("\n")


class BoundedFuzzyApplier:
    """
    🛡️ BoundedFuzzyApplier: 受限模糊套用器
    只容忍行尾空白與 CR/LF 的差異；比對與替換用同一套行座標，
    換掉的範圍剛好是原檔的那幾行，找不到唯一對應就失敗，不做部分套用。
    """

    def fuzzy_match_and_replace(
        self, content: str, search: str, replace: str
    ) -> Tuple[bool, str, str]:
        search_lines = [line.rstrip() for line in search.split("\n")]
        if not any(search_lines):
            return False, content, "FUZZY_MATCH_LOW_CONFIDENCE"
        lines = _split_lines(content)
        stripped = [line.rstrip() for line in lines]
        width = len(search_lines)
        starts = [
            i for i in range(len(stripped) - width + 1) if stripped[i : i + width] == search_lines
        ]
        if len(starts) != 1:
            return False, content, "FUZZY_MATCH_LOW_CONFIDENCE"
        start = starts[0]
        end = start + width
        # 行數相同就逐行沿用原檔該行的換行；行數不同則新行用第一行的換行，最後一行保留原本的尾端。
        new_lines = replace.split("\n")
        old_cr = ["\r" if line.endswith("\r") else "" for line in lines[start:end]]
        if len(new_lines) == width:
            new_lines = [line + cr for line, cr in zip(new_lines, old_cr)]
        else:
            new_lines = [line + old_cr[0] for line in new_lines]
            if new_lines:
                new_lines[-1] = new_lines[-1][: len(new_lines[-1]) - len(old_cr[0])] + old_cr[-1]
        out = lines[:start] + new_lines + lines[end:]
        return True, "\n".join(out), f"Fuzzy matched {width} lines at line {start + 1}"
