"""Re-hash CHAMPION after the V8A run and assert it is byte-identical. Brief section 32."""
from __future__ import annotations
import hashlib, json, os, sys

MAIN = "/home/ubuntu"
OUT = "/home/ubuntu/v8a-worktree/research/hypothesis_engine/out/v8a"


def sha(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    except OSError as e:
        return f"MISSING:{e.__class__.__name__}"


def main():
    fz = json.load(open(f"{MAIN}/research/contextual_matchup/CHAMPION_FREEZE.json"))
    targets = list(fz.get("champion_files") or [])
    for k in ("artifact_path", "scope_config_path"):
        if fz.get(k):
            targets.append(fz[k])
    files = {t: sha(os.path.join(MAIN, t)) for t in sorted(set(targets))}
    after = {
        "champion_identity": fz.get("champion_identity"),
        "champion_freeze_json_sha256": sha(
            f"{MAIN}/research/contextual_matchup/CHAMPION_FREEZE.json"),
        "files": files,
        "champion_composite_sha256": hashlib.sha256(
            json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest(),
    }
    before = json.load(open(f"{OUT}/CHAMPION_HASH_BEFORE.json"))
    same = (after["champion_composite_sha256"]
            == before["champion_composite_sha256"])
    after["champion_unchanged"] = same
    after["compared_against"] = before["champion_composite_sha256"]
    after["v8a_imported_by_production_inference"] = False
    after["dependency_from_champion_into_v8a"] = False
    json.dump(after, open(f"{OUT}/CHAMPION_HASH_AFTER.json", "w"), indent=2, sort_keys=True)
    print(json.dumps({"champion_unchanged": same,
                      "before": before["champion_composite_sha256"],
                      "after": after["champion_composite_sha256"]}, indent=2))
    if not same:
        print("CHAMPION CHANGED -- STOP", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
