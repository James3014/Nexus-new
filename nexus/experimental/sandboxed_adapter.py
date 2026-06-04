class SandboxedAdapter:
    def __init__(self, authorized: bool):
        self.authorized = authorized
    def execute(self):
        if not self.authorized: raise PermissionError("Not authorized")
        return "Success"
