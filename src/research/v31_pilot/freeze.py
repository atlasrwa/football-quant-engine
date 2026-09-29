from __future__ import annotations
import hashlib, json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_FREEZE = ROOT / 'research/v3_1_live_pilot/V31_FREEZE_V1.json'
EXPECTED_CONTRACT_SHA256 = '73b185749aaea6e25880807adbf3d337331a638942c52625aa48f77da3c1aa94'

class FreezeIntegrityError(RuntimeError):
    pass

def _canonical(obj: dict[str, Any]) -> bytes:
    return json.dumps({k:v for k,v in obj.items() if k!='freeze_sha256'}, sort_keys=True, separators=(',',':')).encode()

def load_freeze(path: Path = DEFAULT_FREEZE) -> dict[str, Any]:
    obj=json.loads(Path(path).read_text(encoding='utf-8'))
    observed=hashlib.sha256(_canonical(obj)).hexdigest(); declared=str(obj.get('freeze_sha256') or '')
    if observed != declared or observed != EXPECTED_CONTRACT_SHA256:
        raise FreezeIntegrityError(f'V3.1 freeze mismatch: expected {EXPECTED_CONTRACT_SHA256}, declared {declared}, observed {observed}')
    return obj

def freeze_hash(path: Path = DEFAULT_FREEZE) -> str:
    load_freeze(path); return EXPECTED_CONTRACT_SHA256
