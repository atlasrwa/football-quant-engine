"""Atomic JSON persistence for live experimental artifacts (execution ledgers, control
manifests). Writes to a temp file in the same directory, fsyncs it, then `os.replace`s it
into place -- `os.replace` is atomic on POSIX (same filesystem), so a reader can never observe
a partially-written file, and a crash mid-write leaves only an orphaned `.tmp` file, never a
truncated/corrupt scientific ledger.

Deliberately narrow: this hardens the live-write path only. It does not touch how manifests
and ledgers are read, nor any scientific content.
"""
from __future__ import annotations
import json
import os


def atomic_write_json(path: str, obj) -> None:
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, indent=2, default=str)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
