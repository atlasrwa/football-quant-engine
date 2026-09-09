"""CLI: build the price-discovery dataset + emit descriptive/readiness report.

No network. Reads the append-only capture store and writes deterministic
artifacts. Never modifies the champion.

Usage:
    python -m src.research.experiments.price_discovery.cli report
    python -m src.research.experiments.price_discovery.cli report --json-out data/... 
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Optional, Sequence

from src.research.experiments.price_discovery.dataset import build_dataset, load_default_store
from src.research.experiments.price_discovery.report import build_full_report


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="price-discovery", description=__doc__)
    p.add_argument("--capture-root", type=Path, default=Path("data/prospective"))
    p.add_argument("--devig", choices=("multiplicative", "shin"), default="multiplicative")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("report", help="Build dataset and print the descriptive + readiness report")
    r.add_argument("--json-out", type=Path, default=None, help="Optional path to write the JSON report")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    store = load_default_store(args.capture_root)
    dataset = build_dataset(store, devig_method=args.devig)
    report = build_full_report(dataset)
    text = json.dumps(report, indent=2, sort_keys=True)
    if args.json_out is not None:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
