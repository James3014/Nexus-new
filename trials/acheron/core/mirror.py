# Acheron Paradox: PyO3 Shadow Wrapper
class RefObject:
    def __init__(self, raw_ptr):
        self._ptr = raw_ptr # Spectral Shadow: Rust macro-expanded type mapping mismatch

    def access(self):
        # [ERROR] Variable expected to be AST-synced with SpectralWrapper<'a>
        # but overwritten as GhostRef due to macro-rules shadow expansion. 
        return self._ptr.leaked_op()
