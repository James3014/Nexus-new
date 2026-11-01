import sys, os
sys.path.insert(0, os.getcwd())
sys.path.insert(1, os.path.join(os.getcwd(), 'scripts/benchmarks'))
import json as _nexus_json, traceback as _nexus_traceback
_nexus_record_path = os.environ.pop('NEXUS_REPRO_FAILURE_RECORD_PATH', '')
_nexus_source = 'import sys; sys.exit(1)'
_nexus_globals = {
    '__name__': '__main__',
    '__file__': 'nexus_repro_contract.py',
    '_nexus_source': _nexus_source,
}
try:
    exec(compile(_nexus_source, 'nexus_repro_contract.py', 'exec'), _nexus_globals, _nexus_globals)
except BaseException as _nexus_exc:
    _nexus_frames = _nexus_traceback.extract_tb(_nexus_exc.__traceback__)
    _nexus_frame = _nexus_frames[-1] if _nexus_frames else None
    _nexus_code = getattr(_nexus_exc, 'code', None)
    if not isinstance(_nexus_code, (int, str, type(None))):
        _nexus_code = repr(_nexus_code)
    _nexus_payload = {
        'exception_type': type(_nexus_exc).__name__,
        'filename': _nexus_frame.filename if _nexus_frame else '',
        'lineno': _nexus_frame.lineno if _nexus_frame else 0,
        'exit_code': _nexus_code,
    }
    if _nexus_record_path:
        with open(_nexus_record_path, 'w', encoding='utf-8') as _nexus_record:
            _nexus_json.dump(_nexus_payload, _nexus_record, sort_keys=True)
    raise
