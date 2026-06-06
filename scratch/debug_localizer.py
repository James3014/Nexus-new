import ast
import re
from rank_bm25 import BM25Okapi

def _tokenize(text: str):
    return re.findall(r"\b[a-zA-Z_0-9]{2,}\b", text.lower())

def refine_by_functions(file_path: str, content: str, query: str) -> str:
    try:
        tree = ast.parse(content)
        snippets = []
        lines = content.splitlines()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                start = node.lineno - 1
                end = getattr(node, "end_lineno", node.lineno + 10)
                body = "\n".join(lines[max(0, start-2):end+1])
                snippets.append({"name": node.name, "content": body, "start": start})

        if not snippets:
            print("No snippets found!")
            return content

        tokenized_snippets = [_tokenize(s["content"]) for s in snippets]
        print("tokenized_snippets:", tokenized_snippets)
        print("tokenized_query:", _tokenize(query))
        bm25 = BM25Okapi(tokenized_snippets)
        scores = list(bm25.get_scores(_tokenize(query)))
        
        query_tokens = set(_tokenize(query))
        PYTHON_KEYWORDS = {'def', 'class', 'import', 'from', 'return', 'pass', 'if', 'else', 'elif', 'for', 'while', 'in', 'is', 'not', 'and', 'or', 'try', 'except', 'finally', 'raise', 'as', 'assert', 'async', 'await', 'break', 'continue', 'del', 'global', 'nonlocal', 'with', 'yield', 'self', 'cls'}
        query_tokens = query_tokens - PYTHON_KEYWORDS
        
        for idx, s in enumerate(snippets):
            score = max(0.0, scores[idx])
            overlap = len(query_tokens.intersection(set(tokenized_snippets[idx])))
            scores[idx] = score + overlap * 1.0
            
        print("scores:", list(zip(scores, [s["name"] for s in snippets])))

        scored = sorted(zip(scores, snippets), key=lambda x: -x[0])
        top_snippets = sorted(scored[:3], key=lambda x: x[1]["start"])

        result = [f"# Refined snippets for {file_path}"]
        for score, s in top_snippets:
            if score > 0:
                result.append(f"## {s['name']} (Score: {score:.2f})\n{s['content']}\n")

        print("len(result) =", len(result))
        return "\n".join(result) if len(result) > 1 else content
    except Exception as e:
        import traceback
        traceback.print_exc()
        return content

content = """class HugeClass:
    class_var = 'huge_metadata_info' * 100
    def other_method1(self):
        pass
    def other_method2(self):
        pass
    def target_method(self):
        return 'find_me'
"""
query = "def target_method"
refined = refine_by_functions("large_class.py", content, query)
print("--- REFINED ---")
print(refined)
