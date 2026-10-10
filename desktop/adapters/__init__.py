"""Source formats are separate contracts, not aliases for the HCTP parser."""
from dataclasses import dataclass

@dataclass(frozen=True)
class SourceFormat:
    key: str
    label: str
    supported: bool

FORMATS = (
    SourceFormat('jbi','SmackDown! Just Bring It (PS2)',False),
    SourceFormat('sym','SmackDown! Shut Your Mouth (PS2)',False),
    SourceFormat('hctp','SmackDown! Here Comes the Pain (PS2)',True),
    SourceFormat('svr','SmackDown! vs. Raw (PS2)',False),
)

def adapter(key):
    selected = next((f for f in FORMATS if f.key==key),None)
    if selected is None or not selected.supported:
        raise ValueError('This source format is not supported yet. Select Here Comes the Pain.')
    from .hctp import HctpAdapter
    return HctpAdapter()
