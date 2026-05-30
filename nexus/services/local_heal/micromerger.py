import ast

class EnvContextPerceiver:
    """環境特徵探查組件 (SRP / Clean Code)"""
    def detect_indent(self, code: str) -> str:
        """探查程式碼中的主要縮排類型與字元 (Tab / 2格 / 4格)"""
        lines = code.splitlines()
        for line in lines:
            if line.startswith("\t"):
                return "\t"
            if line.startswith("    "):
                return "    "
            if line.startswith("  ") and not line.startswith("   "):
                return "  "
        return "    "  # 預設為標準 4 空格


class ASTMicroMerger:
    """負責對語法碎裂或遺漏縮排的程式碼區塊實施 AST 級微修復的引擎 (Linus 原則)"""
    def fix_indentation(self, code_block: str, expected_indent: str) -> str:
        """利用 AST unparse 自動對程式碼重新格式化，補齊缺失縮排"""
        try:
            # 嘗試解析
            node = ast.parse(code_block)
            return ast.unparse(node)
        except (SyntaxError, IndentationError):
            # 若為語法或縮排不全，補上縮排後再度 unparse
            adjusted_lines = []
            lines = code_block.splitlines()
            if len(lines) > 1:
                adjusted_lines.append(lines[0])
                for line in lines[1:]:
                    if line.strip() and not line.startswith(expected_indent):
                        adjusted_lines.append(expected_indent + line)
                    else:
                        adjusted_lines.append(line)
            else:
                adjusted_lines = lines
            try:
                node = ast.parse("\n".join(adjusted_lines))
                return ast.unparse(node)
            except Exception:
                return code_block
