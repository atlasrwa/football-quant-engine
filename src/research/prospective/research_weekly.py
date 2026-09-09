"""Weekly coverage summary formatter (research observability, not alpha).

Compact once-weekly message summarizing the operational universe and captured
coverage. It reads only persisted artifacts (the committed coverage matrix and
the capture store analysis-support strata) and NEVER ranks leagues by
profitability or publishes any apparent alpha.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from src.research.prospective.research_notify import (
    MessageType,
    NotifyMessage,
    ResearchStatus,
    _iso,
    _msg,
    _quota_str,
)


def _load_universe(coverage_matrix_path: Path) -> dict:
    """Read universe counts from the committed coverage-matrix artifact.

    Returns a dict of counts; missing artifact yields an explicit 'unknown'
    marker rather than fabricated numbers.
    """
    p = Path(coverage_matrix_path)
    if not p.exists():
        return {"artifact_present": False}
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"artifact_present": False}
    rows = obj.get("rows", []) if isinstance(obj, dict) else []
    from collections import Counter
    klass = Counter(r.get("capture_classification") for r in rows)
    ident = Counter(r.get("identity_status") for r in rows)
    return {
        "artifact_present": True,
        "competitions": len(rows),
        "verified": ident.get("VERIFIED", 0),
        "capture_ready": klass.get("CAPTURE_READY", 0),
        "capture_partial": klass.get("CAPTURE_PARTIAL", 0),
    }


def format_weekly_summary(
    status: ResearchStatus,
    *,
    coverage_matrix_path: Path = Path("research/evaluation/prospective_coverage_matrix.json"),
) -> NotifyMessage:
    u = _load_universe(coverage_matrix_path)
    lines = [
        "Football Quant Engine \u2014 Weekly Coverage",
        "",
        f"Collector: {status.collector_health}",
        f"Quota: {_quota_str(status)}",
        f"Errors last run: {status.errors_last_run if status.errors_last_run is not None else 'n/a'}",
        "",
    ]
    if u.get("artifact_present"):
        lines += [
            f"Active competitions (verified): {u['verified']}",
            f"CAPTURE_READY: {u['capture_ready']}",
            f"CAPTURE_PARTIAL: {u['capture_partial']}",
        ]
    else:
        lines.append("Coverage matrix artifact: not present (counts unknown)")
    lines += [
        "",
        "Evidence accumulation:",
        f"  Fixtures captured: {status.captured_fixtures}",
        f"  LATE->FINAL: {status.same_book_late_final}",
        f"  Confirmed lineups: {status.confirmed_lineups}",
        f"  PRE->POST pairs: {status.pre_post_lineup_pairs}",
        f"  Genuine closes: {status.genuine_closes}",
        "",
        f"Readiness: {status.readiness_state}",
    ]
    text = "\n".join(lines)
    # Dedup per ISO week.
    import datetime as _dt
    dt = _dt.datetime.fromtimestamp(status.generated_at, _dt.timezone.utc)
    iso_year, iso_week, _ = dt.isocalendar()
    return _msg(MessageType.WEEKLY_SUMMARY, f"weekly:{iso_year}-W{iso_week:02d}", text, status)