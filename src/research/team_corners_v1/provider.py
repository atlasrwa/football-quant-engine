from __future__ import annotations
import datetime as dt
import json
import time

from src.research.prospective.api_contract import Endpoint, ProspectiveClientConfig
from src.research.prospective.capture import ProspectiveApiClient, payload_hash
from .config import CACHE, REQUEST_CAP, MONTHLY_RESERVE, MIN_INTERVAL

class BudgetStop(RuntimeError):
    pass

def _atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)

def _ts(value):
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()

class Provider:
    def __init__(self):
        cfg = ProspectiveClientConfig(rate_limit_seconds=MIN_INTERVAL, max_retries=2, timeout_seconds=30)
        self.client = ProspectiveApiClient(config=cfg)
        self.requests = 0
    def _guard(self):
        if self.requests >= REQUEST_CAP:
            raise BudgetStop("request cap reached")
        rl = self.client.last_rate_limit
        remaining = getattr(rl, "monthly_remaining", None) if rl else None
        if remaining not in (None, -1) and int(remaining) <= MONTHLY_RESERVE:
            raise BudgetStop("monthly reserve reached")

    def _get(self, endpoint, kind, entity, params=None, **path):
        self._guard()
        started = time.time()
        payload = self.client.get(endpoint, params=params, **path)
        received = time.time()
        self.requests += 1
        if payload is None:
            return None, received, "", started
        ph = payload_hash(payload)
        target = CACHE / kind / entity / f"{int(received)}_{ph}.json"
        if not target.exists():
            _atomic(target, payload)
        return payload, received, ph, started

    def upcoming(self, competition_id, hours=48):
        now = time.time()
        end = now + hours * 3600
        payload, observed, ph, started = self._get(
            Endpoint.MATCHES, "upcoming", competition_id,
            params={
                "status": "scheduled", "competition_id": competition_id,
                "date_from": dt.datetime.fromtimestamp(now, dt.timezone.utc).date().isoformat(),
                "date_to": dt.datetime.fromtimestamp(end, dt.timezone.utc).date().isoformat(),
                "per_page": 100,
            },
        )
        out = []
        for match in list((payload or {}).get("data", [])):
            try:
                ts = _ts(match["utc_date"])
                if not (now <= ts <= end):
                    continue
                neutral = match.get("is_neutral") if isinstance(match.get("is_neutral"), bool) else None
                out.append({
                    "match_id": str(match["id"]), "competition_id": str(match["competition_id"]),
                    "season_id": str(match["season_id"]), "ts": ts, "kickoff_ts": ts,
                    "utc_date": str(match["utc_date"]), "kickoff": str(match["utc_date"]),
                    "home_id": str(match["home_team"]["id"]), "home_name": str(match["home_team"].get("name") or ""),
                    "away_id": str(match["away_team"]["id"]), "away_name": str(match["away_team"].get("name") or ""),
                    "is_neutral": neutral, "context": {"is_neutral": neutral},
                    "provider_observed_at": observed, "provider_request_started_at": started,
                    "provider_payload_hash": ph,
                })
            except Exception:
                continue
        return sorted(out, key=lambda x: (x["ts"], x["match_id"]))
    def odds(self, match_id):
        return self._get(Endpoint.MATCH_ODDS, "odds", match_id, match_id=match_id)

    def detail(self, match_id):
        return self._get(Endpoint.MATCH_DETAIL, "match_detail", match_id, match_id=match_id)

    def stats(self, match_id):
        return self._get(Endpoint.MATCH_STATS, "stats", match_id, match_id=match_id)
