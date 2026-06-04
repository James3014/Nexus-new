
from dataclasses import dataclass, field
import time

@dataclass
class ProblemTrace:
    ticket_id: str
    steps: list = field(default_factory=list)
    def record(self, node: str, action: str, **meta):
        self.steps.append({'node': node, 'action': action, 'ts': time.time(), 'meta': meta})
