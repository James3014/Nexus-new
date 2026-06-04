class RuntimeGuardrail:
    """
    ⛔ Task C: Runtime Guardrails
    職責: 在執行期強制執行政策約束。
    """
    def __init__(self, mode: str):
        self.mode = mode

    def validate_patch(self, patch: str):
        if self.mode == 'readonly' and ('open(' in patch or '.write(' in patch):
            raise PermissionError('Guardrail: Mutation blocked in readonly mode')
        return True

    @staticmethod
    def enforce_readonly(patch: str):
        """兼容靜態調用"""
        return RuntimeGuardrail(mode='readonly').validate_patch(patch)
