"""Creator hypothesis testing API.

Endpoints for:
- Browsing available features
- Defining and saving hypotheses
- Submitting for validation
- Viewing verdicts
- Enrolling in quarantine
- Forking others' public hypotheses
- Viewing submission stats (anti-p-hacking transparency)

All validation uses the IDENTICAL pipeline as internal models.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.creator.features import build_creator_feature_catalog, get_feature_catalog_summary
from src.creator.guardrails import SubmissionGuardrails
from src.creator.hypothesis import (
    CreatorHypothesis,
    HypothesisBuilder,
    HypothesisStatus,
    PredictionTarget,
)
from src.creator.pipeline import ValidationPipeline, VerdictStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/creator", tags=["creator"])

# ═══════════════════════════════════════════════════════════════
# PERSISTENCE (file-based for v1 — matches forward loop pattern)
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path("/home/ubuntu/data/creator")
HYPOTHESES_FILE = DATA_DIR / "hypotheses.jsonl"
VERDICTS_FILE = DATA_DIR / "verdicts.jsonl"
QUARANTINE_FILE = DATA_DIR / "quarantine_enrollments.jsonl"

DATA_DIR.mkdir(parents=True, exist_ok=True)

# Singleton guardrails (persisted in memory for v1; production would use DB)
_guardrails = SubmissionGuardrails()

# Feature catalog (computed once, cached)
_feature_catalog: Optional[list] = None
_feature_lookup: Optional[dict] = None


def _get_feature_catalog():
    global _feature_catalog, _feature_lookup
    if _feature_catalog is None:
        _feature_catalog = build_creator_feature_catalog()
        _feature_lookup = {f.feature_id: f for f in _feature_catalog}
    return _feature_catalog, _feature_lookup


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    results = []
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")


def _load_match_data() -> list[dict]:
    """Load historical match data for validation pipeline.

    Uses the same cached FootyStats data as the forward loop.
    """
    cache_dir = Path("/home/ubuntu/.cache/footystats_forward")
    all_matches = []
    for cache_file in cache_dir.glob("*.json"):
        with open(cache_file) as f:
            data = json.load(f)
        if isinstance(data, dict) and "data" in data:
            matches = data["data"]
            for m in matches:
                if m.get("status") == "complete":
                    all_matches.append(m)
    return all_matches


# ═══════════════════════════════════════════════════════════════
# REQUEST SCHEMAS
# ═══════════════════════════════════════════════════════════════

class ConditionSchema(BaseModel):
    feature_id: str
    operator: str = Field(..., description="One of: >, <, >=, <=")
    threshold: float


class CreateHypothesisRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=1000)
    target: str = Field(..., description="corners_over_under, cards_over_under, goals_over_under, btts, clean_sheet")
    direction: str = Field(..., description="OVER, UNDER, YES, or NO")
    conditions: list[ConditionSchema] = Field(..., min_length=1, max_length=5)
    logic: str = Field(default="AND", description="AND or OR")
    line: Optional[float] = Field(default=None, description="Market line (e.g., 9.5 for corners)")


class SubmitRequest(BaseModel):
    hypothesis_id: str


class ForkRequest(BaseModel):
    source_hypothesis_id: str
    new_name: str = Field(..., min_length=1, max_length=200)
    new_description: str = Field(default="")


class EnrollQuarantineRequest(BaseModel):
    hypothesis_id: str


# ═══════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.get("/features")
def list_features():
    """List all available features for hypothesis construction.

    Returns the REAL feature set — everything available to internal models
    is available to creators.
    """
    return get_feature_catalog_summary()


@router.get("/features/{category}")
def list_features_by_category(category: str):
    """List features filtered by category."""
    summary = get_feature_catalog_summary()
    if category not in summary["categories"]:
        raise HTTPException(
            status_code=404,
            detail=f"Category '{category}' not found. Available: {list(summary['categories'].keys())}",
        )
    return {
        "category": category,
        "features": summary["categories"][category],
        "count": len(summary["categories"][category]),
    }


@router.post("/hypotheses")
def create_hypothesis(
    request: CreateHypothesisRequest,
    creator_id: str = "anonymous",  # In production: from auth context
):
    """Define a new hypothesis.

    Does NOT submit for validation — just saves as DRAFT. This lets
    creators review before spending a submission.
    """
    _, feature_lookup = _get_feature_catalog()

    builder = HypothesisBuilder(feature_catalog=feature_lookup)
    try:
        hypothesis = builder.build(
            creator_id=creator_id,
            name=request.name,
            description=request.description,
            target=request.target,
            direction=request.direction,
            conditions=[c.model_dump() for c in request.conditions],
            logic=request.logic,
            line=request.line,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # Persist
    _append_jsonl(HYPOTHESES_FILE, hypothesis.to_dict())

    return {
        "hypothesis": hypothesis.to_dict(),
        "next_step": "Submit for validation via POST /api/v1/creator/validate",
        "note": (
            "Your hypothesis is saved as DRAFT. Submitting it for validation "
            "permanently adds it to your multiple-testing family — your FDR bar "
            "will increase. Review carefully before submitting."
        ),
    }


@router.post("/validate")
def validate_hypothesis(
    request: SubmitRequest,
    creator_id: str = "anonymous",
):
    """Submit a hypothesis for validation through the full pipeline.

    This is irreversible: the submission permanently joins the creator's
    FDR testing family, even if it fails.
    """
    # Load hypothesis
    hypotheses = _load_jsonl(HYPOTHESES_FILE)
    hypothesis_dict = next(
        (h for h in hypotheses if h["hypothesis_id"] == request.hypothesis_id),
        None,
    )
    if not hypothesis_dict:
        raise HTTPException(status_code=404, detail="Hypothesis not found")

    if hypothesis_dict.get("creator_id") != creator_id:
        raise HTTPException(status_code=403, detail="Cannot validate another creator's hypothesis")

    # Rate limit check
    can_submit, reason = _guardrails.check_can_submit(creator_id)
    if not can_submit:
        raise HTTPException(status_code=429, detail=reason)

    # Reconstruct hypothesis object
    from src.creator.hypothesis import HypothesisCondition, ConditionOperator
    hypothesis = CreatorHypothesis(
        hypothesis_id=hypothesis_dict["hypothesis_id"],
        creator_id=hypothesis_dict["creator_id"],
        name=hypothesis_dict["name"],
        description=hypothesis_dict.get("description", ""),
        target=PredictionTarget(hypothesis_dict["target"]),
        direction=hypothesis_dict["direction"],
        conditions=[
            HypothesisCondition(
                feature_id=c["feature_id"],
                operator=ConditionOperator(c["operator"]),
                threshold=c["threshold"],
            )
            for c in hypothesis_dict["conditions"]
        ],
        logic=hypothesis_dict["logic"],
        line=hypothesis_dict.get("line"),
        content_hash=hypothesis_dict["content_hash"],
        version=hypothesis_dict.get("version", 1),
        status=HypothesisStatus(hypothesis_dict.get("status", "DRAFT")),
        created_at=hypothesis_dict["created_at"],
        forked_from=hypothesis_dict.get("forked_from"),
    )

    # Load match data and run validation
    match_data = _load_match_data()
    if not match_data:
        raise HTTPException(
            status_code=503,
            detail="No historical match data available for validation. Data may still be loading.",
        )

    # Get creator's FDR family
    p_values = _guardrails.get_fdr_family(creator_id)
    record = _guardrails.get_record(creator_id)

    # Run the FULL pipeline (same as internal models)
    pipeline = ValidationPipeline(match_data=match_data)
    verdict = pipeline.validate(
        hypothesis=hypothesis,
        creator_submission_count=record.total_submissions + 1,
        creator_p_values=p_values,
    )

    # Record submission (permanently)
    _guardrails.record_submission(
        creator_id=creator_id,
        hypothesis_id=hypothesis.hypothesis_id,
        p_value=verdict.p_value,
        passed=(verdict.verdict == VerdictStatus.PASSED),
    )

    # Persist verdict
    _append_jsonl(VERDICTS_FILE, verdict.to_dict())

    return {
        "verdict": verdict.to_dict(),
        "submission_stats": _guardrails.get_submission_stats(creator_id),
        "next_steps": _next_steps(verdict),
    }


@router.post("/hypotheses/fork")
def fork_hypothesis(
    request: ForkRequest,
    creator_id: str = "anonymous",
):
    """Fork another creator's public hypothesis.

    Creates a new hypothesis owned by the forking creator with lineage
    preserved. The fork starts as DRAFT — it's a new hypothesis that
    must pass validation independently.
    """
    hypotheses = _load_jsonl(HYPOTHESES_FILE)
    source = next(
        (h for h in hypotheses if h["hypothesis_id"] == request.source_hypothesis_id),
        None,
    )
    if not source:
        raise HTTPException(status_code=404, detail="Source hypothesis not found")

    _, feature_lookup = _get_feature_catalog()
    builder = HypothesisBuilder(feature_catalog=feature_lookup)

    try:
        forked = builder.build(
            creator_id=creator_id,
            name=request.new_name,
            description=request.new_description or source.get("description", ""),
            target=source["target"],
            direction=source["direction"],
            conditions=source["conditions"],
            logic=source["logic"],
            line=source.get("line"),
            forked_from=source["hypothesis_id"],
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    _append_jsonl(HYPOTHESES_FILE, forked.to_dict())

    return {
        "hypothesis": forked.to_dict(),
        "forked_from": {
            "hypothesis_id": source["hypothesis_id"],
            "name": source["name"],
            "creator_id": source["creator_id"],
        },
        "note": "Forked hypothesis is a new DRAFT. Modify conditions before submitting, or submit as-is (it's your FDR family now).",
    }


@router.post("/quarantine/enroll")
def enroll_quarantine(
    request: EnrollQuarantineRequest,
    creator_id: str = "anonymous",
):
    """Enroll a validated hypothesis in the 90-day quarantine.

    Only hypotheses with VALIDATED_PASS status can be enrolled. The
    quarantine uses the SAME forward loop as internal models — same
    commit-reveal attestation, same settlement cycle.
    """
    # Find the verdict
    verdicts = _load_jsonl(VERDICTS_FILE)
    verdict = next(
        (v for v in verdicts if v["hypothesis_id"] == request.hypothesis_id and
         v.get("verdict") == "PASSED"),
        None,
    )
    if not verdict:
        raise HTTPException(
            status_code=400,
            detail="Only hypotheses that passed validation can enter quarantine. This one either hasn't been validated or didn't pass.",
        )

    # Check not already enrolled
    enrollments = _load_jsonl(QUARANTINE_FILE)
    existing = next(
        (e for e in enrollments if e["hypothesis_id"] == request.hypothesis_id),
        None,
    )
    if existing:
        return {"enrollment": existing, "note": "Already enrolled (idempotent)."}

    # Enroll
    now = datetime.now(timezone.utc)
    enrollment = {
        "hypothesis_id": request.hypothesis_id,
        "creator_id": creator_id,
        "hypothesis_name": verdict["hypothesis_name"],
        "content_hash": verdict["content_hash"],
        "enrolled_at": now.isoformat(),
        "quarantine_expires": (now.replace(day=now.day) + __import__("datetime").timedelta(days=90)).isoformat(),
        "status": "QUARANTINED",
        "note": (
            "This hypothesis is now in a 90-day live quarantine. It will generate "
            "predictions against real fixtures using the same forward loop as internal "
            "models. No model changes are permitted during quarantine."
        ),
    }

    _append_jsonl(QUARANTINE_FILE, enrollment)

    return {
        "enrollment": enrollment,
        "forward_loop_integration": {
            "mechanism": "Same cron-triggered forward loop (scripts/quarantine_forward_loop.py)",
            "schedule": "Every 4 hours",
            "attestation": "Automatic commit-reveal (same as internal models)",
            "capacity_note": (
                "Each enrolled hypothesis adds prediction generation for all upcoming "
                "fixtures in the window. Current capacity supports ~20 simultaneously "
                "quarantined hypotheses before fixture fetch rate limits become a concern "
                "(1,800 requests/hour to FootyStats, fixtures cached and shared across "
                "all models, ~150 predictions/model/run at current fixture density)."
            ),
        },
    }


@router.get("/submissions/{creator_id}")
def get_submission_stats(creator_id: str):
    """Get a creator's submission statistics.

    Visible to all — transparency about submission counts is part of
    the anti-p-hacking design. Others can see how many hypotheses a
    creator tested before one passed.
    """
    return _guardrails.get_submission_stats(creator_id)


@router.get("/hypotheses")
def list_hypotheses(creator_id: Optional[str] = None):
    """List hypotheses, optionally filtered by creator."""
    hypotheses = _load_jsonl(HYPOTHESES_FILE)
    if creator_id:
        hypotheses = [h for h in hypotheses if h.get("creator_id") == creator_id]
    return {"hypotheses": hypotheses, "total": len(hypotheses)}


@router.get("/verdicts/{hypothesis_id}")
def get_verdict(hypothesis_id: str):
    """Get the validation verdict for a hypothesis."""
    verdicts = _load_jsonl(VERDICTS_FILE)
    verdict = next(
        (v for v in verdicts if v["hypothesis_id"] == hypothesis_id),
        None,
    )
    if not verdict:
        raise HTTPException(status_code=404, detail="No verdict found for this hypothesis")
    return verdict


@router.get("/quarantine")
def list_quarantine_enrollments(creator_id: Optional[str] = None):
    """List quarantine enrollments."""
    enrollments = _load_jsonl(QUARANTINE_FILE)
    if creator_id:
        enrollments = [e for e in enrollments if e.get("creator_id") == creator_id]
    return {"enrollments": enrollments, "total": len(enrollments)}


@router.get("/policy")
def get_policy():
    """Public explanation of the anti-p-hacking and governance policy."""
    return {
        "title": "Hypothesis Testing Governance Policy",
        "summary": (
            "Creator hypotheses go through the identical validation pipeline that our "
            "own internal models passed. There is no separate, lighter-weight path. "
            "Most hypotheses should fail — that's the system working correctly."
        ),
        "validation_pipeline": {
            "stages": [
                "1. Minimum sample size (≥250 qualifying matches)",
                "2. Must beat naive baseline (base rate of the target outcome)",
                "3. Statistical significance (p ≤ 0.05, binomial test)",
                "4. FDR correction (Benjamini-Hochberg across ALL creator submissions)",
                "5. Calibration gate (ECE ≤ 0.10)",
            ],
            "note": "A failure at any stage produces a full report explaining why.",
        },
        "anti_p_hacking": {
            "mechanism": "Benjamini-Hochberg False Discovery Rate correction",
            "family": "All hypotheses submitted by one creator form a testing family",
            "implication": (
                "The more hypotheses you submit, the higher the bar each new one must "
                "clear. Submitting 50 variants and finding one significant is NOT finding "
                "an edge — the correction accounts for this. One well-thought-through "
                "hypothesis is more likely to pass than 50 random variations."
            ),
            "rate_limits": {
                "per_24_hours": 5,
                "per_7_days": 20,
                "purpose": "Prevent spray-and-pray submission patterns",
            },
            "visibility": "Submission counts are public. Transparency builds trust.",
        },
        "quarantine": {
            "duration": "90 days",
            "mechanism": "Same forward loop as internal models (cron every 4 hours)",
            "attestation": "Automatic commit-reveal (cryptographic proof predictions preceded kickoff)",
            "promotion_requirements": [
                "90 days elapsed",
                "Passed validation run",
                "≥30 paper trades",
                "Positive cumulative paper P&L",
            ],
            "no_exceptions": (
                "Nothing gets promoted without clearing quarantine first. "
                "This rule is the product; it has no exceptions."
            ),
        },
        "what_we_do_not_do": [
            "We never tune a creator's hypothesis automatically to make it look better",
            "We never provide a lighter-weight validation path for any hypothesis",
            "We never allow quarantine to be skipped or shortened",
            "We never suppress negative results in verdicts",
        ],
    }


def _next_steps(verdict) -> dict:
    """Determine next steps based on verdict outcome."""
    if verdict.verdict == VerdictStatus.PASSED:
        return {
            "action": "Enroll in quarantine",
            "endpoint": "POST /api/v1/creator/quarantine/enroll",
            "note": (
                "Your hypothesis cleared all validation gates. The next step is a "
                "90-day live quarantine — real predictions against real fixtures, with "
                "cryptographic pre-kickoff commitments. No model changes during quarantine."
            ),
        }
    else:
        return {
            "action": "Review verdict and iterate",
            "note": (
                f"Your hypothesis failed at: {verdict.reason}. "
                f"You may define a new hypothesis with different conditions, "
                f"but remember: each submission increases your FDR bar. "
                f"Consider what the failure tells you about your theory before resubmitting."
            ),
            "failed_stage": verdict.verdict.value,
        }
