#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
TARGET = HERE / "tg8_physical_rc_controller_v4_core.py"
spec = importlib.util.spec_from_file_location("tg8_v4_core", TARGET)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load {TARGET}")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def runtime_probe(venv: Path) -> dict[str, object]:
    code = r'''
import hashlib, json, re
from pathlib import Path
import product
from product.protocol import (
    PUBLIC_PROTOCOL_VERSION, IMPLEMENTATION_SCHEMA, EVIDENCE_BUNDLE_SCHEMA,
    PROVENANCE_ENVELOPE_SCHEMA, CERTIFICATION_RECEIPT_SCHEMA,
)
root=Path(product.__file__).resolve().parent
rows=[]
for p in sorted(root.rglob('*.py')):
    rows.append([p.relative_to(root).as_posix(), hashlib.sha256(p.read_bytes()).hexdigest()])
runtime_hash='sha256:'+hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest()
ledger_path=root/'ledger.py'
ledger_text=ledger_path.read_text(encoding='utf-8')
ledger_match=re.search(r'^LEDGER_SCHEMA_VERSION\s*=\s*[\"\']([^\"\']+)[\"\']', ledger_text, re.M)
if not ledger_match:
    raise SystemExit('LEDGER_SCHEMA_VERSION not found in installed wheel source')
schemas_path=root/'runtime'/'schemas.py'
schemas_text=schemas_path.read_text(encoding='utf-8')
http_match=re.search(r'HTTP_RESPONSE_SCHEMA:.*?\"\$id\":\s*\"([^\"]+)\"', schemas_text, re.S)
if not http_match:
    raise SystemExit('HTTP_RESPONSE_SCHEMA $id not found in installed wheel source')
print(json.dumps({
  'public_protocol_version': PUBLIC_PROTOCOL_VERSION,
  'implementation_schema': IMPLEMENTATION_SCHEMA,
  'evidence_bundle_schema': EVIDENCE_BUNDLE_SCHEMA,
  'provenance_envelope_schema': PROVENANCE_ENVELOPE_SCHEMA,
  'certification_receipt_schema': CERTIFICATION_RECEIPT_SCHEMA,
  'ledger_schema': ledger_match.group(1),
  'http_schema': http_match.group(1),
  'runtime_hash': runtime_hash,
  'ledger_source_hash': 'sha256:'+hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
  'product_root': str(root),
}, sort_keys=True))
'''
    result = mod.run([str(mod._venv_python(venv)), "-c", code])
    value = json.loads(result.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("runtime probe did not return object")
    return value


mod.runtime_probe = runtime_probe

if __name__ == "__main__":
    raise SystemExit(mod.main())
