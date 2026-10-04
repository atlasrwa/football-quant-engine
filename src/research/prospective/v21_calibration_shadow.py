"""Prospective QFE V2.1 corner-side calibration shadow.

Research-only. The frozen QFE V2 p_model is the reference and is never mutated.
No market prices or outcomes are accepted by prediction-record APIs.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.layer4.calibration_run import load_raw_rows
from src.research.layer4.calibrators import calibrator_from_spec
from src.research.models.v21_monotone_calibration import (
    PlattIsotonicBlend,
    assert_monotone_transform,
)

SHADOW_FREEZE_VERSION = "qfe-v21-corners-side-calibration-shadow-freeze-v1.1"
SHADOW_RECORD_VERSION = "qfe-v21-corners-side-calibration-shadow-record-v1.1"
ACTIVE_PROTOCOL = "SHADOW_PROTOCOL_V1_1.json"
ROLES = ("HOME", "AWAY")
LINES = (2.5, 3.5, 4.5, 5.5, 6.5, 7.5)
HORIZON_SECONDS = 21600


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text())
    if not isinstance(value, dict):
        raise ValueError(path)
    return value


def _sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _blend_from_spec(spec: dict[str, Any]) -> PlattIsotonicBlend:
    if spec.get("method") != "PLATT_ISOTONIC_BLEND":
        raise ValueError("unexpected challenger method")
    platt = calibrator_from_spec(spec["platt"])
    isotonic = calibrator_from_spec(spec["isotonic"])
    return PlattIsotonicBlend(
        platt=platt,
        isotonic=isotonic,
        alpha=float(spec["alpha"]),
    )


def build_shadow_freeze(repo_root: Path) -> dict[str, Any]:
    repo_root = Path(repo_root)
    protocol_path = repo_root / "research/qfe_v21_calibration" / ACTIVE_PROTOCOL
    protocol = _read_json(protocol_path)
    if protocol["version"] != "QFE_V21_CORNERS_SIDE_CALIBRATION_SHADOW_V1_1":
        raise ValueError("active shadow protocol mismatch")
    if int(
        protocol["prospective_record_contract"]["decision_horizon_seconds"]
    ) != HORIZON_SECONDS:
        raise ValueError("shadow horizon mismatch")

    exploratory = _read_json(
        repo_root / "research/qfe_v21_calibration/RESULT_V1.json"
    )
    if exploratory["result_hash"] != protocol["candidate"][
        "exploratory_result_hash"
    ]:
        raise ValueError("exploratory calibration result binding mismatch")

    layer4_freeze = _read_json(
        repo_root / "evidence/layer4/QFE_LAYER4_MODEL_FREEZE_V1.json"
    )
    if layer4_freeze["model_freeze_hash"] != protocol["reference"][
        "model_freeze_hash"
    ]:
        raise ValueError("Layer4 model freeze binding mismatch")

    calibration = _read_json(
        repo_root / "evidence/layer4/QFE_LAYER4_CALIBRATION_V1.json"
    )
    group = next(
        g for g in calibration["group_results"]
        if g["group"] == "CORNERS_SIDE"
    )
    if group["selected_candidate"] != "PLATT_GLOBAL":
        raise ValueError("unexpected frozen corner-side reference")
    reference_spec = group["final_refit_spec"]

    _, rows = load_raw_rows(repo_root)
    corner_rows = [
        r for r in rows
        if r["group"] == "CORNERS_SIDE"
    ]
    if not corner_rows:
        raise ValueError("missing corner-side calibration rows")
    probs = [float(r["raw_probability"]) for r in corner_rows]
    outcomes = [bool(r["outcome_over"]) for r in corner_rows]
    weights = [float(r["sample_weight"]) for r in corner_rows]
    challenger = PlattIsotonicBlend.fit(
        probs,
        outcomes,
        weights,
        alpha=0.25,
        eps=1e-6,
    )
    assert_monotone_transform(challenger)

    freeze = {
        "version": SHADOW_FREEZE_VERSION,
        "scientific_status": (
            "PROSPECTIVE_SHADOW_FROZEN_PRODUCTION_PMODEL_UNCHANGED"
        ),
        "bindings": {
            "shadow_protocol_hash": sha256_json(protocol),
            "exploratory_result_hash": exploratory["result_hash"],
            "layer4_model_freeze_hash": layer4_freeze["model_freeze_hash"],
            "layer4_calibration_run_hash": calibration[
                "calibration_run_hash"
            ],
        },
        "scope": {
            "group": "CORNERS_SIDE",
            "roles": list(ROLES),
            "lines": list(LINES),
            "decision_horizon_seconds": HORIZON_SECONDS,
        },
        "reference": {
            "method": "PLATT_GLOBAL",
            "calibrator_spec": reference_spec,
        },
        "challenger": {
            "method": "PLATT_ISOTONIC_BLEND",
            "alpha_platt": 0.75,
            "alpha_isotonic": 0.25,
            "calibrator_spec": challenger.to_spec(),
            "fit_unique_fixtures": len(
                {r["fixture_key"] for r in corner_rows}
            ),
            "fit_event_cells": len(corner_rows),
        },
        "stopping_rule": protocol["stopping_rule"],
        "evaluation": protocol["evaluation"],
        "boundaries": {
            "market_odds_used": False,
            "protected_V2_outcomes_used_for_design": False,
            "production_p_model_modified": False,
            "retrospective_shadow_backfill_allowed": False,
        },
        "implementation_sha256": {
            "shadow_module": _sha(
                repo_root
                / "src/research/prospective/v21_calibration_shadow.py"
            ),
            "challenger_module": _sha(
                repo_root
                / "src/research/models/v21_monotone_calibration.py"
            ),
            "protocol": _sha(protocol_path),
        },
    }
    freeze["shadow_freeze_hash"] = sha256_json(freeze)
    return freeze


def _calibrators(freeze: dict[str, Any]):
    reference = calibrator_from_spec(
        freeze["reference"]["calibrator_spec"]
    )
    challenger = _blend_from_spec(
        freeze["challenger"]["calibrator_spec"]
    )
    return reference, challenger


def _record_hash(body: dict[str, Any]) -> str:
    return sha256_json(body)


def build_fixture_record(
    *,
    freeze: dict[str, Any],
    fixture_key: str,
    kickoff_ts: int,
    prediction_cutoff_ts: int,
    generated_at_ts: int,
    raw_over_by_role: dict[str, dict[float, float]],
    prev_hash: str,
) -> dict[str, Any]:
    if freeze.get("version") != SHADOW_FREEZE_VERSION:
        raise ValueError("shadow freeze version mismatch")
    if not fixture_key:
        raise ValueError("fixture_key required")
    kickoff_ts = int(kickoff_ts)
    prediction_cutoff_ts = int(prediction_cutoff_ts)
    generated_at_ts = int(generated_at_ts)
    if prediction_cutoff_ts != kickoff_ts - HORIZON_SECONDS:
        raise ValueError("prediction cutoff must equal kickoff minus 21600 seconds")
    if not prediction_cutoff_ts <= generated_at_ts < kickoff_ts:
        raise ValueError(
            "generated_at must be at/after cutoff and strictly before kickoff"
        )
    if set(raw_over_by_role) != set(ROLES):
        raise ValueError("complete HOME/AWAY role surface required")

    reference, challenger = _calibrators(freeze)
    surfaces: dict[str, list[dict[str, float]]] = {}
    for role in ROLES:
        supplied = {
            float(line): float(probability)
            for line, probability in raw_over_by_role[role].items()
        }
        if set(supplied) != set(LINES):
            raise ValueError(
                f"complete registered corner-side lines required for {role}"
            )
        raw_probs = [supplied[line] for line in LINES]
        if any(not 0.0 < p < 1.0 for p in raw_probs):
            raise ValueError("raw probabilities must be strictly inside (0,1)")
        if any(
            raw_probs[i + 1] > raw_probs[i] + 1e-12
            for i in range(len(raw_probs) - 1)
        ):
            raise ValueError(f"raw {role} ladder is non-monotone")

        cells = []
        ref_probs = []
        chal_probs = []
        for line in LINES:
            raw = supplied[line]
            p_ref = float(reference.transform(raw, role=role))
            p_chal = float(challenger.transform(raw, role=role))
            ref_probs.append(p_ref)
            chal_probs.append(p_chal)
            cells.append(
                {
                    "line": line,
                    "raw_probability_over": raw,
                    "p_reference_over": p_ref,
                    "p_challenger_over": p_chal,
                }
            )
        for name, probs in (
            ("reference", ref_probs),
            ("challenger", chal_probs),
        ):
            if any(
                probs[i + 1] > probs[i] + 1e-12
                for i in range(len(probs) - 1)
            ):
                raise ValueError(f"{name} {role} ladder is non-monotone")
        surfaces[role] = cells

    body = {
        "version": SHADOW_RECORD_VERSION,
        "shadow_freeze_hash": freeze["shadow_freeze_hash"],
        "fixture_key": fixture_key,
        "kickoff_ts": kickoff_ts,
        "prediction_cutoff_ts": prediction_cutoff_ts,
        "generated_at_ts": generated_at_ts,
        "decision_horizon_seconds": HORIZON_SECONDS,
        "surfaces": surfaces,
        "prev_hash": str(prev_hash),
        "market_odds_used": False,
        "outcomes_used": False,
    }
    return {**body, "record_hash": _record_hash(body)}


def verify_ledger_rows(rows: list[dict[str, Any]]) -> str:
    prev = ""
    fixtures = set()
    for index, row in enumerate(rows):
        if row.get("prev_hash") != prev:
            raise ValueError(f"broken shadow prev_hash at row {index}")
        body = {k: v for k, v in row.items() if k != "record_hash"}
        expected = _record_hash(body)
        if row.get("record_hash") != expected:
            raise ValueError(f"broken shadow record_hash at row {index}")
        fixture = row.get("fixture_key")
        if fixture in fixtures:
            raise ValueError(f"duplicate shadow fixture: {fixture}")
        fixtures.add(fixture)
        if row.get("market_odds_used") is not False:
            raise ValueError("market odds entered shadow prediction ledger")
        if row.get("outcomes_used") is not False:
            raise ValueError("outcomes entered shadow prediction ledger")
        prev = expected
    return prev


class CalibrationShadowLedger:
    """Append-only hash-chained prospective shadow prediction ledger."""

    def __init__(self, path: Path, freeze: dict[str, Any]) -> None:
        self.path = Path(path)
        self.freeze = freeze
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._rows = self.read_all()
        self._head = verify_ledger_rows(self._rows)
        self._fixtures = {row["fixture_key"] for row in self._rows}

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        rows = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                value = json.loads(line)
                if not isinstance(value, dict):
                    raise ValueError("shadow ledger row must be an object")
                rows.append(value)
        return rows

    @property
    def chain_head(self) -> str:
        return self._head

    @property
    def n_records(self) -> int:
        return len(self._rows)

    def append_fixture(
        self,
        *,
        fixture_key: str,
        kickoff_ts: int,
        prediction_cutoff_ts: int,
        generated_at_ts: int,
        raw_over_by_role: dict[str, dict[float, float]],
    ) -> dict[str, Any]:
        if fixture_key in self._fixtures:
            raise ValueError(f"shadow fixture already committed: {fixture_key}")
        record = build_fixture_record(
            freeze=self.freeze,
            fixture_key=fixture_key,
            kickoff_ts=kickoff_ts,
            prediction_cutoff_ts=prediction_cutoff_ts,
            generated_at_ts=generated_at_ts,
            raw_over_by_role=raw_over_by_role,
            prev_hash=self._head,
        )
        payload = canonical_json(record) + "\n"
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        self._rows.append(record)
        self._fixtures.add(fixture_key)
        self._head = record["record_hash"]
        return record


def write_shadow_freeze(
    *,
    json_path: Path,
    markdown_path: Path,
    freeze: dict[str, Any],
) -> None:
    json_path = Path(json_path)
    markdown_path = Path(markdown_path)
    json_payload = canonical_json(freeze) + "\n"
    markdown = "\n".join(
        [
            "# QFE V2.1 — Corner-Side Calibration Shadow Freeze V1.1",
            "",
            f"Freeze hash: {freeze['shadow_freeze_hash']}",
            "",
            "Status: **PROSPECTIVE SHADOW FROZEN**",
            "",
            "- Production QFE V2 p_model remains unchanged.",
            "- Scope: CORNERS_SIDE HOME/AWAY, lines 2.5 through 7.5.",
            "- Decision horizon: T-6h (21,600 seconds).",
            "- Challenger: 75% Platt / 25% isotonic.",
            "- No market odds or outcomes enter prediction records.",
            "- Retrospective backfill is forbidden.",
            "",
        ]
    )
    for path, payload in (
        (json_path, json_payload),
        (markdown_path, markdown),
    ):
        if path.exists() and path.read_text() != payload:
            raise FileExistsError(path)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(payload)
