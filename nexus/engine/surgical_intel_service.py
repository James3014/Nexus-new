from pathlib import Path
from nexus.engine.surgical_retriever import SurgicalRetriever
from nexus.engine.surgical_slicer import SurgicalSlicer
from nexus.engine.surgical_packer import SurgicalPacker
class SurgicalIntelligence:
    def __init__(self, root):
        self.root = Path(root)
        self.retriever = SurgicalRetriever(self.root)
    def provide_context(self, sym, budget=4000):
        files = self.retriever.find_definition(sym)
        if not files: return ""
        s = SurgicalSlicer(files[0])
        res = s.slice_function(sym)
        try: return SurgicalPacker(res.code_content, budget).pack()
        except: return res.code_content[:budget*4]
