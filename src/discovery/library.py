"""Metric Library — stores validated metrics with full provenance.

A validated metric has cleared:
1. Discovery screening (predictive value across multiple targets)
2. FDR correction (honest family-size accounting)
3. Adversarial review (mechanism, leakage, redundancy checks)
4. Held-out validation (untouched data confirms discovery-set findings)

Status lifecycle:
- CANDIDATE: Generated, not yet screened
- SCREENED: Passed screening, awaiting FDR
- FDR_SURVIVOR: Survived multiple-testing correction
- REVIEWED: Passed adversarial review
- DISCOVERED: Confirmed on held-out set (eligible for forward testing)
- QUARANTINED: In 90-day forward test
- VALIDATED: Cleared quarantine (available as composition primitive)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

LIBRARY_DIR = Path("/home/ubuntu/data/discovery")
LIBRARY_FILE = LIBRARY_DIR / "metric_library.json"
SEARCH_LOG_FILE = LIBRARY_DIR / "search_log.jsonl"
ATTRITION_FILE = LIBRARY_DIR / "attrition_report.json"


class MetricStatus(str, Enum):
    CANDIDATE = "CANDIDATE"
    SCREENED = "SCREENED"
    FDR_SURVIVOR = "FDR_SURVIVOR"
    REVIEWED = "REVIEWED"
    DISCOVERED = "DISCOVERED"
    QUARANTINED = "QUARANTINED"
    VALIDATED = "VALIDATED"
    REJECTED = "REJECTED"


@dataclass
class MetricRecord:
    """A metric in the library with full provenance."""
    metric_id: str
    name: str
    formula_type: str
    fields: list[str]
    params: dict[str, Any]
    description: str
    status: MetricStatus

    # Discovery results
    discovery_date: Optional[str] = None
    screening_result: Optional[dict] = None
    fdr_result: Optional[dict] = None
    adversarial_review: Optional[dict] = None
    heldout_result: Optional[dict] = None

    # Mechanism (from adversarial review)
    mechanism: Optional[str] = None

    # Performance summary
    targets_positive: int = 0
    breadth_score: float = 0.0
    best_vs_naive_pct: float = 0.0

    def to_dict(self) -> dict:
        return {
            "metric_id": self.metric_id,
            "name": self.name,
            "formula_type": self.formula_type,
            "fields": self.fields,
            "params": self.params,
            "description": self.description,
            "status": self.status.value,
            "discovery_date": self.discovery_date,
            "screening_result": self.screening_result,
            "fdr_result": self.fdr_result,
            "adversarial_review": self.adversarial_review,
            "heldout_result": self.heldout_result,
            "mechanism": self.mechanism,
            "targets_positive": self.targets_positive,
            "breadth_score": self.breadth_score,
            "best_vs_naive_pct": self.best_vs_naive_pct,
        }


class MetricLibrary:
    """Manages the metric library and search provenance.

    Every candidate ever generated is logged to search_log.jsonl —
    this is what makes the FDR correction auditable.
    """

    def __init__(self) -> None:
        LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
        self._metrics: dict[str, MetricRecord] = {}
        self._load()

    def _load(self) -> None:
        """Load existing library from disk."""
        if LIBRARY_FILE.exists():
            with open(LIBRARY_FILE) as f:
                data = json.load(f)
            for entry in data.get("metrics", []):
                self._metrics[entry["metric_id"]] = MetricRecord(
                    metric_id=entry["metric_id"],
                    name=entry["name"],
                    formula_type=entry["formula_type"],
                    fields=entry["fields"],
                    params=entry["params"],
                    description=entry["description"],
                    status=MetricStatus(entry["status"]),
                    discovery_date=entry.get("discovery_date"),
                    screening_result=entry.get("screening_result"),
                    fdr_result=entry.get("fdr_result"),
                    adversarial_review=entry.get("adversarial_review"),
                    heldout_result=entry.get("heldout_result"),
                    mechanism=entry.get("mechanism"),
                    targets_positive=entry.get("targets_positive", 0),
                    breadth_score=entry.get("breadth_score", 0.0),
                    best_vs_naive_pct=entry.get("best_vs_naive_pct", 0.0),
                )

    def save(self) -> None:
        """Persist library to disk."""
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "total_metrics": len(self._metrics),
            "by_status": {s.value: sum(1 for m in self._metrics.values() if m.status == s) for s in MetricStatus},
            "metrics": [m.to_dict() for m in self._metrics.values()],
        }
        with open(LIBRARY_FILE, "w") as f:
            json.dump(data, f, indent=2)

    def add_candidate(self, metric_id: str, name: str, formula_type: str,
                      fields: list[str], params: dict, description: str) -> None:
        """Register a candidate metric (logged for FDR family counting)."""
        if metric_id not in self._metrics:
            self._metrics[metric_id] = MetricRecord(
                metric_id=metric_id,
                name=name,
                formula_type=formula_type,
                fields=fields,
                params=params,
                description=description,
                status=MetricStatus.CANDIDATE,
            )

    def promote_to_screened(self, metric_id: str, screening_result: dict) -> None:
        """Mark a metric as having passed screening."""
        if metric_id in self._metrics:
            m = self._metrics[metric_id]
            m.status = MetricStatus.SCREENED
            m.screening_result = screening_result
            m.targets_positive = screening_result.get("targets_positive", 0)
            m.breadth_score = screening_result.get("breadth_score", 0.0)
            m.best_vs_naive_pct = screening_result.get("best_vs_naive_pct", 0.0)

    def promote_to_fdr_survivor(self, metric_id: str, fdr_result: dict) -> None:
        """Mark as surviving FDR correction."""
        if metric_id in self._metrics:
            m = self._metrics[metric_id]
            m.status = MetricStatus.FDR_SURVIVOR
            m.fdr_result = fdr_result

    def promote_to_reviewed(self, metric_id: str, review: dict, mechanism: str) -> None:
        """Mark as passing adversarial review."""
        if metric_id in self._metrics:
            m = self._metrics[metric_id]
            m.status = MetricStatus.REVIEWED
            m.adversarial_review = review
            m.mechanism = mechanism

    def promote_to_discovered(self, metric_id: str, heldout_result: dict) -> None:
        """Mark as confirmed on held-out set."""
        if metric_id in self._metrics:
            m = self._metrics[metric_id]
            m.status = MetricStatus.DISCOVERED
            m.heldout_result = heldout_result
            m.discovery_date = datetime.now(timezone.utc).isoformat()

    def reject(self, metric_id: str, reason: str) -> None:
        """Mark as rejected at any stage."""
        if metric_id in self._metrics:
            self._metrics[metric_id].status = MetricStatus.REJECTED

    def get(self, metric_id: str) -> Optional[MetricRecord]:
        return self._metrics.get(metric_id)

    def get_by_status(self, status: MetricStatus) -> list[MetricRecord]:
        return [m for m in self._metrics.values() if m.status == status]

    @property
    def count(self) -> int:
        return len(self._metrics)

    def log_search(self, metric_id: str, result: dict) -> None:
        """Log a screening result to the search log (append-only, auditable)."""
        SEARCH_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "metric_id": metric_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **result,
        }
        with open(SEARCH_LOG_FILE, "a") as f:
            f.write(json.dumps(record) + "\n")

    def save_attrition_report(self, report: dict) -> None:
        """Save the attrition report showing funnel at each stage."""
        with open(ATTRITION_FILE, "w") as f:
            json.dump(report, f, indent=2)

    def get_attrition_report(self) -> dict:
        """Load the attrition report."""
        if ATTRITION_FILE.exists():
            with open(ATTRITION_FILE) as f:
                return json.load(f)
        return {}
