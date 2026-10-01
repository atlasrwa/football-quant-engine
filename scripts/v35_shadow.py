#!/usr/bin/env python3
"""Offline-safe CLI for the QFE V3.5 selected frontier."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.research.v35_frontier.pipeline import compare_frozen, freeze_fixture


def _json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("freeze", help="freeze model distributions for a supplied future fixture")
    p.add_argument("--fixture", required=True)
    p.add_argument("--output-root", required=True)

    p = sub.add_parser("compare", help="compare an already frozen bundle with timestamped odds")
    p.add_argument("--bundle", required=True)
    p.add_argument("--odds", required=True)

    args = parser.parse_args()
    if args.command == "freeze":
        out = freeze_fixture(
            _json(args.fixture),
            output_root=args.output_root,
        )
    else:
        out = compare_frozen(_json(args.bundle), _json(args.odds))
    print(json.dumps(out, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
