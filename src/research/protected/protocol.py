"""Frozen QFE V2 protected-evaluation contract."""
from __future__ import annotations
import json
from pathlib import Path
from src.research.dataset.manifest import sha256_json

PROTECTED_EVALUATION_VERSION = "qfe-v2-protected-evaluation-v1"
PROTECTED_EVALUATION_CONTRACT_HASH = "41c446b15f03ae91bcc76ab26b5b90e0a6f40cfed603d8a0f4bb08df97b0a0d7"

def load_contract(repo_root: Path = Path('.')) -> dict:
    d=json.loads((Path(repo_root)/"evidence/protected_v1/QFE_PROTECTED_EVALUATION_PROTOCOL_V1.json").read_text())
    payload={k:v for k,v in d.items() if k != "contract_hash"}
    if d.get("contract_hash") != PROTECTED_EVALUATION_CONTRACT_HASH or sha256_json(payload) != PROTECTED_EVALUATION_CONTRACT_HASH:
        raise ValueError("protected evaluation contract hash mismatch")
    return d
