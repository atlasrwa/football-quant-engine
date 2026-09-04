"""
One-off discovery: find TheStatsAPI competition ids + recent complete seasons for
the three TOP FLIGHTS in this family-transfer test (EPL, La Liga, Ligue 1).

EPL is already known (comp_3039) and its 25/26 season (sn_6125938) fixtures are
cached. La Liga and Ligue 1 top-flight comp ids are NOT in the codebase, so we
must discover them. This probes the competitions listing endpoint (cache-first,
allow 200/404/422 so a wrong shape does not abort and burn budget), then lists
seasons for each discovered comp.

Cache-first + quota-capped via thestatsapi_client. Zero budget on re-run.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import thestatsapi_client as api

# Known from scripts/pilotC_fixture_discovery.py COVERED_LEAGUES and crosswalk:
KNOWN = {
    "epl": ("comp_3039", "England Premier League"),
    # second tiers already in corpus (for reference, not fetched here)
    "champ": ("comp_8321", "England Championship"),
    "laliga2": ("comp_0976", "Spain La Liga 2"),
    "ligue2": ("comp_9777", "France Ligue 2"),
}


def probe_competitions_list(max_pages=20):
    """List competitions with pagination (per_page<=100). Returns list of comps."""
    comps = []
    page = 1
    while page <= max_pages:
        data, meta = api.get_json(
            "/football/competitions",
            params={"per_page": 100, "page": page},
            cache_key=f"competitions_list_p{page}",
            allow_status=(200, 404, 422, 400))
        if data is None or meta.get("http_status") != 200:
            break
        batch = data.get("data", data) if isinstance(data, dict) else data
        if not batch:
            break
        comps.extend(batch)
        md = (data.get("metadata") or data.get("meta") or {}) if isinstance(data, dict) else {}
        total_pages = md.get("total_pages") or md.get("last_page") or page
        print(f"  competitions page {page}/{total_pages}: +{len(batch)} (total {len(comps)})")
        if page >= int(total_pages):
            break
        page += 1
    return comps


def seasons_for(comp):
    data, meta = api.get_json(f"/football/competitions/{comp}/seasons",
                              cache_key=f"seasons_{comp}",
                              allow_status=(200, 404, 422))
    if data is None:
        return []
    return data.get("data", data) if isinstance(data, dict) else data


def main():
    print("budget before:", api.budget_snapshot().get("last_monthly_remaining"))

    # 1) EPL seasons (comp_3039) — comp known, list seasons to pick 2 most recent complete
    for tag, (comp, name) in KNOWN.items():
        if tag in ("champ", "laliga2", "ligue2"):
            continue  # already in corpus
        seasons = seasons_for(comp)
        print(f"\n=== {name} ({comp}) seasons ===")
        for s in seasons:
            print(f"  {s.get('id')}  {s.get('name')}  {s.get('year')} "
                  f"current={s.get('is_current')} start={s.get('start_year')} end={s.get('end_year')}")

    # 2) Discover La Liga / Ligue 1 comp ids from the competitions list
    comps = probe_competitions_list()
    if not comps:
        print("\ncompetitions list endpoint returned nothing; will need another route")
        print("budget after:", api.budget_snapshot().get("last_monthly_remaining"))
        return
    print(f"\ncompetitions listed: {len(comps)}")
    wanted = ("la liga", "laliga", "primera", "ligue 1", "ligue1", "premier league")
    for c in comps:
        nm = (c.get("name") or "").lower()
        country = (c.get("country") or c.get("country_name") or c.get("area") or "")
        if any(w in nm for w in wanted):
            print(f"  MATCH id={c.get('id')}  name={c.get('name')}  country={country}")
    print("\nbudget after:", api.budget_snapshot().get("last_monthly_remaining"))


if __name__ == "__main__":
    main()
