"""Leakage-safe positional-profile and uncertainty experiment.

The provider exposes aggregate player maps for a whole competition season. These
maps are used only for later-season fixtures: La Liga 2 2024/25 profiles evaluate
2025/26 matches. ``evaluate`` is cache-only and compares nested arms on identical
fixtures:

1. rolling-rich baseline;
2. baseline with strictly-prior global -> league -> team probability pooling;
3. pooled baseline plus richer positional main effects;
4. pooled main effects plus symmetric matchup interactions.

The final arm also reports strictly-prior Beta calibration-bin intervals and a
predeclared epistemic abstention policy. All-row scores remain primary; selective
scores always use the final arm's retained match IDs for every comparator.
"""
from __future__ import annotations

import collections
import glob
import json
import math
import sys
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

import numpy as np

ROOT = Path("/home/ubuntu")
CACHE = ROOT / "data/thestatsapi/championship"
HEATMAP_CACHE = ROOT / "data/thestatsapi/heatmap"
RESULTS = ROOT / "data/results"

TAG = "laliga2"
COMPETITION_ID = "comp_0976"
PROFILE_SEASON_ID = "sn_8425423"
EVALUATION_SEASON_ID = "sn_8437950"
LEAGUE_KEY = "spain_segunda_division"
ORIENTATION_CERTIFICATE_PATH = (
    ROOT / "data/attestations/spatial_orientation_certifications.json"
)
PLAYERS_PER_TEAM = 12
MIN_VALID_PLAYERS = 5
MIN_TOTAL_TOUCHES = 100
BASELINE_FIELDS = ("fouls", "shotsOnTarget", "xg")
POSITIONAL_FIELDS = (
    "heatmap_width_index",
    "heatmap_pitch_height",
    "heatmap_vertical_compactness",
    "heatmap_final_third_share",
    "heatmap_lr_asymmetry",
)
PROFILE_SUPPORT_FIELDS = ("heatmap_player_coverage", "heatmap_touch_count")
MATCHUP_FIELDS = (
    "matchup_width_product",
    "matchup_height_vs_compactness",
    "matchup_territorial_product",
    "matchup_asymmetry_alignment",
)
SEED = 20260904
MIN_TRAIN = 100
REFIT = 50

# Fixed before evaluation; none is tuned on 2025/26 outcomes.
HIERARCHY_LEAGUE_STRENGTH = 50.0
HIERARCHY_TEAM_STRENGTH = 10.0
HIERARCHY_MODEL_STRENGTH = 8.0
CALIBRATION_BINS = 10
BAYES_INTERVAL_MASS = 0.90
ABSTAIN_CONFIDENCE_MARGIN = 0.15
ABSTAIN_MIN_TEAM_MATCHES = 8
ABSTAIN_MIN_BIN_MATCHES = 20
ABSTAIN_MAX_INTERVAL_WIDTH = 0.30


def require_orientation_certificate(
    certificate_path: Path = ORIENTATION_CERTIFICATE_PATH,
) -> dict:
    """Return a valid external coordinate-orientation certification or fail closed.

    Player-season heatmaps have no safe directional interpretation unless an
    independently verified attestation proves the provider's coordinate system
    is stable for the exact league, competition, and profile season.  A missing,
    malformed, expired, or non-certified document blocks both fetching and
    evaluating; raw maps must not become an implicit feature source.
    """
    if not certificate_path.exists():
        raise RuntimeError(
            "BLOCKED_UNVERIFIED_ORIENTATION: no external spatial orientation "
            f"certificate at {certificate_path}"
        )
    try:
        payload = json.loads(certificate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("BLOCKED_UNVERIFIED_ORIENTATION: invalid certificate") from exc
    entries = payload.get("certifications") if isinstance(payload, dict) else None
    if not isinstance(entries, list):
        raise RuntimeError("BLOCKED_UNVERIFIED_ORIENTATION: certificate list missing")
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if (
            entry.get("league_key") == LEAGUE_KEY
            and entry.get("competition_id") == COMPETITION_ID
            and entry.get("profile_season_id") == PROFILE_SEASON_ID
            and entry.get("status") == "CERTIFIED"
            and isinstance(entry.get("evidence_reference"), str)
            and entry["evidence_reference"].strip()
            and isinstance(entry.get("certified_at"), str)
            and entry["certified_at"].strip()
        ):
            return dict(entry)
    raise RuntimeError(
        "BLOCKED_UNVERIFIED_ORIENTATION: no certified stable coordinate "
        "orientation for this league, competition, and profile season"
    )


def _finite_number(value: object) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def valid_points(response: object) -> list[tuple[float, float, float]]:
    """Extract valid ``(x, y, touch_count)`` cells from a raw response."""
    data = response.get("data", {}) if isinstance(response, dict) else {}
    raw_points = data.get("points", []) if isinstance(data, dict) else []
    if not isinstance(raw_points, list):
        return []
    out: list[tuple[float, float, float]] = []
    for point in raw_points:
        if not isinstance(point, dict):
            continue
        x, y, count = (_finite_number(point.get(key)) for key in ("x", "y", "count"))
        if x is None or y is None or count is None:
            continue
        if 0.0 <= x <= 100.0 and 0.0 <= y <= 100.0 and count > 0.0:
            out.append((x, y, count))
    return out


def weighted_quantile(values: Sequence[float], weights: Sequence[float], quantile: float) -> float:
    """Return a deterministic left-continuous weighted quantile."""
    if not 0.0 <= quantile <= 1.0:
        raise ValueError("quantile must be in [0, 1]")
    if len(values) != len(weights) or not values:
        raise ValueError("values and positive weights must have equal non-zero length")
    pairs = sorted((float(value), float(weight)) for value, weight in zip(values, weights))
    total = sum(weight for _, weight in pairs if weight > 0.0)
    if total <= 0.0:
        raise ValueError("weights must have positive total")
    threshold = quantile * total
    cumulative = 0.0
    for value, weight in pairs:
        if weight <= 0.0:
            continue
        cumulative += weight
        if cumulative >= threshold:
            return value
    return pairs[-1][0]


def positional_profile(responses: Iterable[object]) -> Optional[dict[str, float]]:
    """Return touch-weighted structural spatial features.

    ``final_third_share`` is a high-zone touch tendency, not possession-adjusted
    territorial dominance. Signed left/right asymmetry is retained for the requested
    hypothesis, but its interpretation depends on stable provider x orientation.
    """
    points = [point for response in responses for point in valid_points(response)]
    total = sum(count for _, _, count in points)
    if total <= 0.0:
        return None
    xs = [x for x, _, _ in points]
    ys = [y for _, y, _ in points]
    weights = [count for _, _, count in points]
    mean_x = sum(x * count for x, _, count in points) / total
    mean_y = sum(y * count for _, y, count in points) / total
    var_x = sum(count * (x - mean_x) ** 2 for x, _, count in points) / total
    var_y = sum(count * (y - mean_y) ** 2 for _, y, count in points) / total
    vertical_iqr = weighted_quantile(ys, weights, 0.75) - weighted_quantile(ys, weights, 0.25)
    wide_touches = sum(count for x, _, count in points if x <= 25.0 or x >= 75.0)
    final_third = sum(count for _, y, count in points if y >= (200.0 / 3.0))
    right = sum(count for x, _, count in points if x > 50.0)
    left = sum(count for x, _, count in points if x < 50.0)
    return {
        # Backward-compatible diagnostics.
        "heatmap_mean_x": mean_x,
        "heatmap_mean_y": mean_y,
        "heatmap_width_sd_x": math.sqrt(var_x),
        "heatmap_depth_sd_y": math.sqrt(var_y),
        "heatmap_width_p90_p10_x": (
            weighted_quantile(xs, weights, 0.90) - weighted_quantile(xs, weights, 0.10)
        ),
        "heatmap_vertical_iqr_y": vertical_iqr,
        # Predeclared model features.
        "heatmap_width_index": wide_touches / total,
        "heatmap_pitch_height": mean_y,
        "heatmap_vertical_compactness": max(0.0, min(1.0, 1.0 - vertical_iqr / 100.0)),
        "heatmap_final_third_share": final_third / total,
        "heatmap_lr_asymmetry": (right - left) / total,
        "heatmap_touch_count": total,
    }


def _profile_match_ids() -> set[str]:
    ids: set[str] = set()
    for path in glob.glob(str(CACHE / f"{TAG}_matches_sn_8425423_p*.json")):
        with open(path) as handle:
            payload = json.load(handle)
        ids.update(match["id"] for match in payload.get("data", []) if match.get("id"))
    if not ids:
        raise FileNotFoundError("no cached 2024/25 La Liga 2 match pages")
    return ids


def historical_team_player_counts() -> dict[str, collections.Counter[str]]:
    """Assign players to their strongest historical club membership."""
    match_ids = _profile_match_ids()
    per_team: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for path in glob.glob(str(CACHE / "lineups_mt_*.json")):
        with open(path) as handle:
            lineup = json.load(handle).get("data", {})
        if lineup.get("match_id") not in match_ids:
            continue
        for side in ("home", "away"):
            team = lineup.get(side, {})
            team_id = team.get("id")
            if not team_id:
                continue
            for player in team.get("starting_xi", []) or []:
                if player.get("id"):
                    per_team[team_id][player["id"]] += 2
            for player in team.get("substitutes", []) or []:
                if player.get("id"):
                    per_team[team_id][player["id"]] += 1

    per_player: dict[str, list[tuple[str, int]]] = collections.defaultdict(list)
    for team_id, counts in per_team.items():
        for player_id, count in counts.items():
            per_player[player_id].append((team_id, count))
    assigned: dict[str, collections.Counter[str]] = collections.defaultdict(collections.Counter)
    for player_id, memberships in per_player.items():
        memberships.sort(key=lambda item: (-item[1], item[0]))
        if len(memberships) > 1 and memberships[0][1] == memberships[1][1]:
            continue
        team_id, count = memberships[0]
        assigned[team_id][player_id] = count
    return dict(assigned)


def selected_team_players(max_players: int = PLAYERS_PER_TEAM) -> dict[str, list[str]]:
    if max_players < 1:
        raise ValueError("max_players must be positive")
    return {
        team_id: [player_id for player_id, _ in counts.most_common(max_players)]
        for team_id, counts in historical_team_player_counts().items()
    }


def _response_path(player_id: str) -> Path:
    return HEATMAP_CACHE / f"player_{player_id}_{COMPETITION_ID}_{PROFILE_SEASON_ID}.json"


def _manifest_path() -> Path:
    return HEATMAP_CACHE / f"{TAG}_{PROFILE_SEASON_ID}_profile_manifest.json"


def _load_manifest() -> dict:
    path = _manifest_path()
    if not path.exists():
        return {"season_id": PROFILE_SEASON_ID, "competition_id": COMPETITION_ID, "players": {}}
    with open(path) as handle:
        return json.load(handle)


def _save_manifest(manifest: dict) -> None:
    HEATMAP_CACHE.mkdir(parents=True, exist_ok=True)
    with open(_manifest_path(), "w") as handle:
        json.dump(manifest, handle, indent=2, sort_keys=True)


def load_cached_response(player_id: str) -> Optional[dict]:
    path = _response_path(player_id)
    if not path.exists():
        return None
    with open(path) as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, dict) else None


def fetch_selected_heatmaps(max_players: int = PLAYERS_PER_TEAM) -> dict:
    """Fetch selected historical maps only after orientation certification."""
    orientation_certificate = require_orientation_certificate()
    sys.path.insert(0, str(ROOT / "scripts"))
    import thestatsapi_client as api

    HEATMAP_CACHE.mkdir(parents=True, exist_ok=True)
    api.CACHE_DIR = str(HEATMAP_CACHE)
    api.USAGE_LOG = str(HEATMAP_CACHE / "_usage_log.jsonl")
    api.BUDGET_STATE = str(HEATMAP_CACHE / "_budget_state.json")

    team_players = selected_team_players(max_players)
    player_ids = sorted({player for players in team_players.values() for player in players})
    manifest = _load_manifest()
    manifest.update({
        "max_players_per_team": max_players,
        "team_players": team_players,
        "orientation_certificate": orientation_certificate,
    })
    status = manifest.setdefault("players", {})
    for index, player_id in enumerate(player_ids, 1):
        if player_id in status:
            continue
        data, meta = api.get_json(
            f"/football/players/{player_id}/competitions/{COMPETITION_ID}/seasons/{PROFILE_SEASON_ID}/heatmap",
            cache_key=f"player_{player_id}_{COMPETITION_ID}_{PROFILE_SEASON_ID}",
            allow_status=(200, 404),
        )
        status[player_id] = {
            "http_status": meta.get("http_status"),
            "from_cache": meta.get("from_cache"),
            "valid_points": len(valid_points(data)),
        }
        _save_manifest(manifest)
        print(
            f"[{index}/{len(player_ids)}] {player_id}: status={meta.get('http_status')} "
            f"points={status[player_id]['valid_points']} cache={meta.get('from_cache')}"
        )
    manifest["requested_players"] = len(player_ids)
    manifest["live_requests_this_run"] = api.live_requests_made()
    _save_manifest(manifest)
    return manifest


def build_team_profiles(
    team_players: Mapping[str, Sequence[str]],
    *,
    min_valid_players: int = MIN_VALID_PLAYERS,
    min_total_touches: float = MIN_TOTAL_TOUCHES,
) -> dict[str, dict[str, float]]:
    """Build profiles from cached historical responses only."""
    profiles: dict[str, dict[str, float]] = {}
    for team_id, players in team_players.items():
        responses = [load_cached_response(player_id) for player_id in players]
        valid_responses = [response for response in responses if response and valid_points(response)]
        profile = positional_profile(valid_responses)
        if profile is None or len(valid_responses) < min_valid_players:
            continue
        if profile["heatmap_touch_count"] < min_total_touches:
            continue
        profile["heatmap_player_coverage"] = float(len(valid_responses))
        profiles[team_id] = profile
    return profiles


def attach_prior_profiles(
    features: Sequence[dict],
    profiles: Mapping[str, Mapping[str, float]],
    *,
    profile_season_end_unix: int,
) -> list[dict]:
    """Attach profiles only when both teams qualify and every fixture is later."""
    out: list[dict] = []
    for feature in features:
        date = feature.get("date_unix")
        if date is None or int(date) <= profile_season_end_unix:
            raise AssertionError("profile season is not strictly before every evaluated fixture")
        home = profiles.get(feature.get("home_team_id"))
        away = profiles.get(feature.get("away_team_id"))
        if home is None or away is None:
            continue
        row = dict(feature)
        row["league_id"] = TAG
        for field in (*POSITIONAL_FIELDS, *PROFILE_SUPPORT_FIELDS):
            if field not in home or field not in away:
                raise AssertionError(f"incomplete positional profile: {field}")
            row[f"{field}_home"] = float(home[field])
            row[f"{field}_away"] = float(away[field])
        out.append(row)
    return out


def add_matchup_interactions(rows: Sequence[dict]) -> list[dict]:
    """Add side-swap-invariant positional matchup terms."""
    out: list[dict] = []
    for source in rows:
        row = dict(source)
        width_home = float(row["heatmap_width_index_home"])
        width_away = float(row["heatmap_width_index_away"])
        height_home = float(row["heatmap_pitch_height_home"]) / 100.0
        height_away = float(row["heatmap_pitch_height_away"]) / 100.0
        compact_home = float(row["heatmap_vertical_compactness_home"])
        compact_away = float(row["heatmap_vertical_compactness_away"])
        territory_home = float(row["heatmap_final_third_share_home"])
        territory_away = float(row["heatmap_final_third_share_away"])
        asymmetry_home = float(row["heatmap_lr_asymmetry_home"])
        asymmetry_away = float(row["heatmap_lr_asymmetry_away"])
        row.update({
            "matchup_width_product": width_home * width_away,
            "matchup_height_vs_compactness": 0.5 * (
                height_home * compact_away + height_away * compact_home
            ),
            "matchup_territorial_product": territory_home * territory_away,
            "matchup_asymmetry_alignment": asymmetry_home * asymmetry_away,
        })
        out.append(row)
    return out


def _target_value(feature: Mapping[str, object], target: str) -> Optional[float]:
    value = feature.get(target)
    return None if value is None else float(value)


def _encode_team_ids(rows: Sequence[dict]) -> None:
    identities: dict[object, int] = {}

    def encode(team_id: object) -> int:
        if team_id not in identities:
            identities[team_id] = len(identities) + 1
        return identities[team_id]

    for row in rows:
        row["_history_home_team_id"] = row["home_team_id"]
        row["_history_away_team_id"] = row["away_team_id"]
        row["home_team_id"] = encode(row["home_team_id"])
        row["away_team_id"] = encode(row["away_team_id"])


def new_hierarchy_state() -> dict:
    return {
        "global": [0.0, 0],
        "leagues": collections.defaultdict(lambda: [0.0, 0]),
        "teams": collections.defaultdict(lambda: [0.0, 0]),
    }


def hierarchical_probability(
    raw_probability: float,
    state: Mapping[str, object],
    *,
    league_id: object,
    home_team_id: object,
    away_team_id: object,
) -> dict[str, float]:
    """Shrink a raw probability through global, league, and team event priors."""
    global_successes, global_n = state["global"]
    global_rate = (float(global_successes) + 1.0) / (int(global_n) + 2.0)
    league_successes, league_n = state["leagues"].get(league_id, (0.0, 0))
    league_rate = (
        float(league_successes) + HIERARCHY_LEAGUE_STRENGTH * global_rate
    ) / (int(league_n) + HIERARCHY_LEAGUE_STRENGTH)

    team_rates: list[float] = []
    team_counts: list[int] = []
    for team_id in (home_team_id, away_team_id):
        successes, count = state["teams"].get((league_id, team_id), (0.0, 0))
        team_rates.append(
            (float(successes) + HIERARCHY_TEAM_STRENGTH * league_rate)
            / (int(count) + HIERARCHY_TEAM_STRENGTH)
        )
        team_counts.append(int(count))
    matchup_prior = float(np.mean(team_rates))
    effective_team_n = min(team_counts)
    model_weight = effective_team_n / (effective_team_n + HIERARCHY_MODEL_STRENGTH)
    pooled = model_weight * float(raw_probability) + (1.0 - model_weight) * matchup_prior
    return {
        "probability": max(0.001, min(0.999, pooled)),
        "global_rate": global_rate,
        "league_rate": league_rate,
        "home_team_rate": team_rates[0],
        "away_team_rate": team_rates[1],
        "min_team_n": float(effective_team_n),
        "model_weight": model_weight,
        "league_n": float(league_n),
    }


def _update_hierarchy(state: dict, row: Mapping[str, object], outcome: float) -> None:
    league_id = row.get("league_id", TAG)
    state["global"][0] += outcome
    state["global"][1] += 1
    state["leagues"][league_id][0] += outcome
    state["leagues"][league_id][1] += 1
    for key in ("_history_home_team_id", "_history_away_team_id"):
        bucket = state["teams"][(league_id, row[key])]
        bucket[0] += outcome
        bucket[1] += 1


def bayesian_bin_posterior(successes: float, trials: int) -> dict[str, float]:
    """Beta(1,1) posterior summary for a strictly-prior calibration bin."""
    from scipy.stats import beta as beta_distribution

    alpha = 1.0 + float(successes)
    beta = 1.0 + float(trials) - float(successes)
    tail = (1.0 - BAYES_INTERVAL_MASS) / 2.0
    lower = float(beta_distribution.ppf(tail, alpha, beta))
    upper = float(beta_distribution.ppf(1.0 - tail, alpha, beta))
    return {
        "mean": alpha / (alpha + beta),
        "lower": lower,
        "upper": upper,
        "width": upper - lower,
        "trials": float(trials),
    }


def abstention_decision(
    probability: float,
    *,
    min_team_n: int,
    calibration_bin_n: int,
    interval_width: float,
) -> tuple[bool, list[str]]:
    """Apply the fixed epistemic gate to non-neutral model calls."""
    if abs(float(probability) - 0.5) < ABSTAIN_CONFIDENCE_MARGIN:
        return False, []
    reasons: list[str] = []
    if min_team_n < ABSTAIN_MIN_TEAM_MATCHES:
        reasons.append("thin_team_history")
    if calibration_bin_n < ABSTAIN_MIN_BIN_MATCHES:
        reasons.append("thin_calibration_bin")
    if interval_width > ABSTAIN_MAX_INTERVAL_WIDTH:
        reasons.append("wide_beta_interval")
    return bool(reasons), reasons


def _calibration_bin(probability: float) -> int:
    return min(CALIBRATION_BINS - 1, max(0, int(float(probability) * CALIBRATION_BINS)))


def _walk_forward(
    rows: Sequence[dict],
    *,
    target: str,
    line: float,
    fields: Sequence[str],
    hierarchical: bool,
) -> Optional[dict]:
    """Chronological scoring with same-kickoff batching and prior-only uncertainty."""
    from src.research.models.count_regression import CountRegressionModel, DistributionType

    scored = sorted((dict(row) for row in rows), key=lambda row: row.get("date_unix", 0))
    _encode_team_ids(scored)
    if len(scored) < MIN_TRAIN + 30:
        return None

    predictions: list[float] = []
    raw_predictions: list[float] = []
    actuals: list[float] = []
    match_ids: list[str] = []
    interval_lower: list[float] = []
    interval_upper: list[float] = []
    posterior_means: list[float] = []
    bin_supports: list[int] = []
    min_team_supports: list[int] = []
    abstained: list[bool] = []
    abstain_reasons: list[list[str]] = []

    hierarchy_state = new_hierarchy_state()
    calibration_state = [[0.0, 0] for _ in range(CALIBRATION_BINS)]
    model = None
    last_fit_n = -REFIT
    cursor = 0
    while cursor < len(scored):
        date = scored[cursor].get("date_unix", 0)
        end = cursor + 1
        while end < len(scored) and scored[end].get("date_unix", 0) == date:
            end += 1
        batch = scored[cursor:end]
        pending: list[tuple[int, float]] = []

        if cursor >= MIN_TRAIN:
            if model is None or cursor - last_fit_n >= REFIT:
                train = scored[:cursor]
                model = CountRegressionModel(
                    target_field=target,
                    line=line,
                    distribution=DistributionType.AUTO,
                    feature_fields=tuple(fields),
                    use_team_effects=True,
                )
                model.fit(train, [(_target_value(row, target) or 0.0) > line for row in train])
                last_fit_n = cursor

            for row in batch:
                target_value = _target_value(row, target)
                if target_value is None:
                    continue
                raw_probability = float(model.predict(row).p_over)
                hierarchy = hierarchical_probability(
                    raw_probability,
                    hierarchy_state,
                    league_id=row.get("league_id", TAG),
                    home_team_id=row["_history_home_team_id"],
                    away_team_id=row["_history_away_team_id"],
                )
                probability = hierarchy["probability"] if hierarchical else raw_probability
                bin_index = _calibration_bin(probability)
                successes, trials = calibration_state[bin_index]
                posterior = bayesian_bin_posterior(successes, trials)
                should_abstain, reasons = abstention_decision(
                    probability,
                    min_team_n=int(hierarchy["min_team_n"]),
                    calibration_bin_n=int(trials),
                    interval_width=posterior["width"],
                )
                outcome = 1.0 if target_value > line else 0.0
                predictions.append(float(probability))
                raw_predictions.append(raw_probability)
                actuals.append(outcome)
                match_ids.append(str(row["match_id"]))
                interval_lower.append(posterior["lower"])
                interval_upper.append(posterior["upper"])
                posterior_means.append(posterior["mean"])
                bin_supports.append(int(trials))
                min_team_supports.append(int(hierarchy["min_team_n"]))
                abstained.append(should_abstain)
                abstain_reasons.append(reasons)
                pending.append((bin_index, outcome))

        # Outcomes from the whole kickoff group become available only after scoring it.
        for row in batch:
            target_value = _target_value(row, target)
            if target_value is not None:
                _update_hierarchy(hierarchy_state, row, 1.0 if target_value > line else 0.0)
        for bin_index, outcome in pending:
            calibration_state[bin_index][0] += outcome
            calibration_state[bin_index][1] += 1
        cursor = end

    if len(predictions) < 30:
        return None
    return {
        "preds": np.asarray(predictions),
        "raw_preds": np.asarray(raw_predictions),
        "actuals": np.asarray(actuals),
        "match_ids": match_ids,
        "interval_lower": np.asarray(interval_lower),
        "interval_upper": np.asarray(interval_upper),
        "posterior_means": np.asarray(posterior_means),
        "bin_supports": np.asarray(bin_supports),
        "min_team_supports": np.asarray(min_team_supports),
        "abstained": np.asarray(abstained, dtype=bool),
        "abstain_reasons": abstain_reasons,
    }


def _bss(predictions: np.ndarray, actuals: np.ndarray) -> Optional[float]:
    if len(actuals) == 0:
        return None
    naive = np.mean((actuals.mean() - actuals) ** 2)
    if naive <= 0:
        return None
    return float((1.0 - np.mean((predictions - actuals) ** 2) / naive) * 100.0)


def _ece(predictions: np.ndarray, actuals: np.ndarray) -> Optional[float]:
    from src.research.calibration import CalibrationEvaluator

    result = CalibrationEvaluator(n_bins=10, min_samples=30).evaluate(
        list(predictions), [bool(value) for value in actuals]
    )
    return float(result.ece) if result.is_valid else None


def _score_summary(run: Mapping[str, object]) -> dict:
    predictions = np.asarray(run["preds"])
    actuals = np.asarray(run["actuals"])
    bss = _bss(predictions, actuals)
    return {
        "n": len(predictions),
        "bss_pct": None if bss is None else round(bss, 3),
        "brier": None if not len(predictions) else round(float(np.mean((predictions - actuals) ** 2)), 5),
        "ece": _ece(predictions, actuals),
        "mean_probability": None if not len(predictions) else round(float(np.mean(predictions)), 5),
        "event_rate": None if not len(actuals) else round(float(np.mean(actuals)), 5),
    }


def _subset_run(run: Mapping[str, object], selected_ids: set[str]) -> dict:
    indices = [index for index, match_id in enumerate(run["match_ids"]) if match_id in selected_ids]
    return {
        "preds": np.asarray(run["preds"])[indices],
        "actuals": np.asarray(run["actuals"])[indices],
        "match_ids": [run["match_ids"][index] for index in indices],
    }


def paired_bss_difference(
    base: Mapping[str, object],
    augmented: Mapping[str, object],
    *,
    seed: int = SEED,
    n_boot: int = 10_000,
) -> Optional[dict]:
    base_index = {match_id: index for index, match_id in enumerate(base["match_ids"])}
    common = [match_id for match_id in augmented["match_ids"] if match_id in base_index]
    if len(common) < 30:
        return None
    augmented_index = {
        match_id: index for index, match_id in enumerate(augmented["match_ids"])
    }
    base_indices = np.asarray([base_index[match_id] for match_id in common])
    augmented_indices = np.asarray([augmented_index[match_id] for match_id in common])
    base_predictions = np.asarray(base["preds"])[base_indices]
    augmented_predictions = np.asarray(augmented["preds"])[augmented_indices]
    actuals = np.asarray(base["actuals"])[base_indices]
    if not np.array_equal(actuals, np.asarray(augmented["actuals"])[augmented_indices]):
        raise AssertionError("baseline and augmented outcomes diverged on common fixtures")
    base_bss = _bss(base_predictions, actuals)
    augmented_bss = _bss(augmented_predictions, actuals)
    if base_bss is None or augmented_bss is None:
        return None
    rng = np.random.default_rng(seed)
    differences: list[float] = []
    for _ in range(n_boot):
        indices = rng.choice(len(common), len(common), replace=True)
        base_sample = _bss(base_predictions[indices], actuals[indices])
        augmented_sample = _bss(augmented_predictions[indices], actuals[indices])
        if base_sample is not None and augmented_sample is not None:
            differences.append(augmented_sample - base_sample)
    if not differences:
        return None
    values = np.asarray(differences)
    return {
        "n_common": len(common),
        "baseline_bss_pct": round(base_bss, 3),
        "augmented_bss_pct": round(augmented_bss, 3),
        "difference_pct": round(augmented_bss - base_bss, 3),
        "difference_ci95_pct": [
            round(float(np.quantile(values, 0.025)), 3),
            round(float(np.quantile(values, 0.975)), 3),
        ],
        "two_sided_bootstrap_p": round(
            float(2 * min(np.mean(values <= 0), np.mean(values >= 0))), 4
        ),
    }


def _abstention_summary(final_run: Mapping[str, object], comparators: Mapping[str, Mapping[str, object]]) -> dict:
    retained_ids = {
        match_id
        for match_id, abstained in zip(final_run["match_ids"], final_run["abstained"])
        if not abstained
    }
    abstained_ids = set(final_run["match_ids"]) - retained_ids
    retained_final = _subset_run(final_run, retained_ids)
    abstained_final = _subset_run(final_run, abstained_ids)
    reason_counts = collections.Counter(
        reason for reasons in final_run["abstain_reasons"] for reason in reasons
    )
    retained_comparisons = {}
    for name, run in comparators.items():
        selected = _subset_run(run, retained_ids)
        retained_comparisons[name] = {
            "score": _score_summary(selected),
            "paired_vs_final": paired_bss_difference(selected, retained_final),
        }
    widths = np.asarray(final_run["interval_upper"]) - np.asarray(final_run["interval_lower"])
    return {
        "policy": {
            "confidence_margin_from_half": ABSTAIN_CONFIDENCE_MARGIN,
            "minimum_team_matches": ABSTAIN_MIN_TEAM_MATCHES,
            "minimum_calibration_bin_matches": ABSTAIN_MIN_BIN_MATCHES,
            "maximum_beta_interval_width": ABSTAIN_MAX_INTERVAL_WIDTH,
            "beta_interval_mass": BAYES_INTERVAL_MASS,
        },
        "retained": len(retained_ids),
        "abstained": len(abstained_ids),
        "coverage_pct": round(100.0 * len(retained_ids) / len(final_run["match_ids"]), 2),
        "reason_counts": dict(reason_counts),
        "mean_prior_beta_interval_width": round(float(np.mean(widths)), 4),
        "retained_final_score": _score_summary(retained_final),
        "abstained_final_score": _score_summary(abstained_final),
        "retained_comparators": retained_comparisons,
    }


def _prediction_audit(run: Mapping[str, object]) -> list[dict]:
    audit = []
    for index, match_id in enumerate(run["match_ids"]):
        audit.append({
            "match_id": match_id,
            "probability": round(float(run["preds"][index]), 6),
            "beta_posterior_mean": round(float(run["posterior_means"][index]), 6),
            "beta_interval90": [
                round(float(run["interval_lower"][index]), 6),
                round(float(run["interval_upper"][index]), 6),
            ],
            "prior_calibration_bin_n": int(run["bin_supports"][index]),
            "prior_min_team_n": int(run["min_team_supports"][index]),
            "abstained": bool(run["abstained"][index]),
            "abstain_reasons": run["abstain_reasons"][index],
        })
    return audit


def evaluate() -> dict:
    """Run the cache-only nested comparison only with certified orientation."""
    orientation_certificate = require_orientation_certificate()
    sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
    import multisrc_corpus as corpus
    from src.research.models.prior_only_features import (
        assert_no_same_match_leakage_rich,
        build_rich_prior_only_features,
    )

    manifest = _load_manifest()
    profiles = build_team_profiles(manifest.get("team_players", {}))
    profile_matches = [
        match for match in corpus.load_season(TAG, PROFILE_SEASON_ID) if match.get("date_unix")
    ]
    evaluation_matches = [
        match for match in corpus.load_season(TAG, EVALUATION_SEASON_ID) if match.get("date_unix")
    ]
    if not profile_matches or not evaluation_matches:
        raise RuntimeError("both profile and evaluation seasons must be cached")
    profile_end = max(int(match["date_unix"]) for match in profile_matches)
    evaluation_start = min(int(match["date_unix"]) for match in evaluation_matches)
    if profile_end >= evaluation_start:
        raise AssertionError("profile and evaluation seasons overlap")

    specs = {"corners": ("total_corners", 9.5), "cards": ("total_cards", 3.5)}
    result: dict = {
        "profile_season": PROFILE_SEASON_ID,
        "evaluation_season": EVALUATION_SEASON_ID,
        "orientation_certificate": orientation_certificate,
        "profile_season_end_unix": profile_end,
        "evaluation_season_start_unix": evaluation_start,
        "n_team_profiles": len(profiles),
        "profiled_team_ids": sorted(profiles),
        "n_evaluation_matches": len(evaluation_matches),
        "hierarchy": {
            "levels": ["global", "league", "team"],
            "n_leagues": 1,
            "league_strength": HIERARCHY_LEAGUE_STRENGTH,
            "team_strength": HIERARCHY_TEAM_STRENGTH,
            "raw_model_strength": HIERARCHY_MODEL_STRENGTH,
            "limitation": "single-league holdout: league prior equals the global empirical rate",
        },
        "positional_fields": list(POSITIONAL_FIELDS),
        "matchup_fields": list(MATCHUP_FIELDS),
        "markets": {},
    }

    ordered_matches = sorted(evaluation_matches, key=lambda match: match["date_unix"])
    baseline_model_fields = [
        f"{field}_{side}" for field in BASELINE_FIELDS for side in ("home", "away")
    ]
    positional_model_fields = [
        *baseline_model_fields,
        *[f"{field}_{side}" for field in POSITIONAL_FIELDS for side in ("home", "away")],
    ]
    matchup_model_fields = [*positional_model_fields, *MATCHUP_FIELDS]

    for market, (target, line) in specs.items():
        rolling = build_rich_prior_only_features(
            ordered_matches, target_field=target, fields=BASELINE_FIELDS
        )
        assert_no_same_match_leakage_rich(
            ordered_matches, rolling, fields=BASELINE_FIELDS
        )
        joined = attach_prior_profiles(
            rolling, profiles, profile_season_end_unix=profile_end
        )
        interaction_rows = add_matchup_interactions(joined)
        runs = {
            "raw_baseline": _walk_forward(
                joined,
                target=target,
                line=line,
                fields=baseline_model_fields,
                hierarchical=False,
            ),
            "hierarchical_baseline": _walk_forward(
                joined,
                target=target,
                line=line,
                fields=baseline_model_fields,
                hierarchical=True,
            ),
            "positional_main": _walk_forward(
                joined,
                target=target,
                line=line,
                fields=positional_model_fields,
                hierarchical=True,
            ),
            "positional_matchup": _walk_forward(
                interaction_rows,
                target=target,
                line=line,
                fields=matchup_model_fields,
                hierarchical=True,
            ),
        }
        entry: dict = {
            "profile_covered_fixtures": len(joined),
            "profile_excluded_fixtures": len(rolling) - len(joined),
        }
        if any(run is None for run in runs.values()):
            entry["status"] = "insufficient scored profile-covered fixtures"
        else:
            final_run = runs["positional_matchup"]
            entry.update({
                "status": "ok",
                "primary_all_row_scores": {
                    name: _score_summary(run) for name, run in runs.items()
                },
                "paired_improvement_tests": {
                    "hierarchy_vs_raw": paired_bss_difference(
                        runs["raw_baseline"], runs["hierarchical_baseline"]
                    ),
                    "positional_vs_hierarchy": paired_bss_difference(
                        runs["hierarchical_baseline"], runs["positional_main"]
                    ),
                    "matchup_vs_positional": paired_bss_difference(
                        runs["positional_main"], final_run
                    ),
                    "final_vs_raw": paired_bss_difference(
                        runs["raw_baseline"], final_run
                    ),
                },
                "bayesian_abstention_secondary": _abstention_summary(
                    final_run,
                    {
                        "raw_baseline": runs["raw_baseline"],
                        "hierarchical_baseline": runs["hierarchical_baseline"],
                        "positional_main": runs["positional_main"],
                    },
                ),
                "final_prediction_audit": _prediction_audit(final_run),
            })
        result["markets"][market] = entry

    RESULTS.mkdir(parents=True, exist_ok=True)
    output = RESULTS / "heatmap_positional_experiment_laliga2.json"
    with open(output, "w") as handle:
        json.dump(result, handle, indent=2)
    return result


def main() -> None:
    command = sys.argv[1] if len(sys.argv) > 1 else "plan"
    if command == "plan":
        players = selected_team_players()
        print(json.dumps({
            "teams": len(players),
            "unique_player_requests": len({player for values in players.values() for player in values}),
            "players_per_team": PLAYERS_PER_TEAM,
            "profile_season": PROFILE_SEASON_ID,
            "evaluation_season": EVALUATION_SEASON_ID,
        }, indent=2))
    elif command == "fetch":
        manifest = fetch_selected_heatmaps()
        print(json.dumps({
            "requested_players": manifest.get("requested_players"),
            "live_requests_this_run": manifest.get("live_requests_this_run"),
        }, indent=2))
    elif command == "evaluate":
        print(json.dumps(evaluate(), indent=2))
    else:
        raise SystemExit(f"unknown command: {command}")


if __name__ == "__main__":
    main()
