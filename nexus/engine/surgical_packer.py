import re, ast
class SurgicalPacker:
    def __init__(self, code, budget_tokens=4000):
        self.code, self.budget = code, budget_tokens
    def pack(self):
        c = self.code
        if len(c)//4 <= self.budget: return c
        c = re.sub(r'#.*', '', c)
        if len(c)//4 <= self.budget: return c
        try:
            t = ast.parse(c)
            for n in ast.walk(t):
                if isinstance(n, (ast.FunctionDef, ast.ClassDef, ast.Module)) and n.body:
                    if isinstance(n.body[0], ast.Expr) and isinstance(n.body[0].value, (ast.Constant, ast.Str)):
                        n.body.pop(0)
            c = ast.unparse(t)
        except: pass
        if len(c)//4 <= self.budget: return c
        raise RuntimeError("Context budget exceeded")
