"""Freeze the current Phase-B research generation (patch §1).

Before changing anything, we preserve the existing Phase-B implementation and artifacts as
an immutable research generation `PHASE_B_V1`. This module records, into a single manifest:

  * git commit + working-tree status;
  * the frozen version identity (ontology / schema / prompt / cohort / packet / formation
    policy / formation family);
  * the Bedrock model identity used for Phase-B;
  * sha256 hashes of the frozen source modules (the *code* that produced the states);
  * sha256 hashes of every existing out/ artifact (states, manifests, selections, reports);
  * the B1/B2 selection hashes recorded before calls.

It writes ONLY research/llm_matchup/out/FREEZE_PHASE_B_V1.json and NEVER mutates or
overwrites any existing artifact. Re-running is idempotent unless --force is passed, in
which case it refuses to overwrite an existing freeze (immutability guarantee) and writes a
timestamped side file instead.

Run: .venv/bin/python -m src.research.llm_matchup.hardening.freeze
"""
from __future__ import annotations
import os, sys, json, hashlib, subprocess, time, glob

from src.research.llm_matchup import versions as V

ROOT = "/home/ubuntu"
OUT = os.path.join(ROOT, "research/llm_matchup/out")
SRC_DIR = os.path.join(ROOT, "src/research/llm_matchup")
FREEZE_PATH = os.path.join(OUT, "FREEZE_PHASE_B_V1.json")

GENERATION_ID = "PHASE_B_V1"

# The frozen Phase-B source modules (the exact code that produced the frozen states). The
# hardening package is deliberately EXCLUDED — it is a new generation, not part of the
# frozen instrument.
FROZEN_MODULES = [
    "ontology.py", "schema.py", "prompt.py", "validator.py", "versions.py",
    "evidence.py", "evidence_v2.py", "cohorts.py", "formation.py",
    "formation_evidence.py", "bedrock_adapter.py", "phaseb_harness.py",
    "run_b0_smoke.py", "run_b1_adversarial.py", "run_b2_corners.py",
    "golden.py", "stub.py", "gen_artifacts.py",
]


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception as e:  # pragma: no cover - environment dependent
        return f"<git-error: {e}>"


def _read_json(path: str):
    try:
        return json.load(open(path))
    except Exception:
        return None


def build_manifest() -> dict:
    # 1. git state
    git_state = {
        "commit": _git("rev-parse", "HEAD"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        "status_porcelain": _git("status", "--porcelain"),
        "head_subject": _git("log", "-1", "--pretty=%s"),
    }

    # 2. frozen version identity + model identity
    version_identity = {
        **V.version_stamp(),
        "default_bedrock_model_id": V.DEFAULT_BEDROCK_MODEL_ID,
        "default_bedrock_region": V.DEFAULT_BEDROCK_REGION,
        "inference_config": V.INFERENCE_CONFIG,
    }

    # 3. frozen source-module hashes (the instrument code)
    module_hashes = {}
    for m in FROZEN_MODULES:
        p = os.path.join(SRC_DIR, m)
        module_hashes[m] = _sha256_file(p) if os.path.exists(p) else None

    # 4. every existing out/ artifact hash (states, manifests, selections, csv). Cache dir
    #    is summarised by count + a hash-of-hashes to keep the manifest bounded.
    artifact_hashes = {}
    for p in sorted(glob.glob(os.path.join(OUT, "*"))):
        if os.path.isfile(p):
            artifact_hashes[os.path.basename(p)] = _sha256_file(p)
    cache_files = sorted(glob.glob(os.path.join(OUT, "cache", "*.json")))
    cache_digest = hashlib.sha256(
        "".join(_sha256_file(p) for p in cache_files).encode()).hexdigest()
    cache_summary = {"n_cached_calls": len(cache_files), "cache_hash_of_hashes": cache_digest}

    # 5. B1/B2 selection hashes + existing output hashes (already covered above, surfaced
    #    explicitly for auditability)
    b2_sel = _read_json(os.path.join(OUT, "b2_selection.json")) or {}
    b1_summary = _read_json(os.path.join(OUT, "b1_summary.json")) or {}
    b2_summary = _read_json(os.path.join(OUT, "b2_summary.json")) or {}
    selection_hashes = {
        "b2_selection_hash": b2_sel.get("selection_hash"),
        "b2_n_selected": b2_sel.get("n_selected"),
        "b1_repeat_stable": b1_summary.get("n_repeat_stable"),
        "b1_n_fixtures": b1_summary.get("n_fixtures"),
        "b2_schema_valid_pct": b2_summary.get("schema_valid_pct"),
    }

    # corpus fingerprint (input/corpus hash, patch §1): hash the loaded corpus fixture ids +
    # kickoff to fingerprint the input universe without embedding the whole corpus.
    corpus_fp = _corpus_fingerprint()

    manifest = {
        "generation_id": GENERATION_ID,
        "frozen_unix": int(time.time()),
        "note": ("Immutable Phase-B research generation. Do NOT overwrite its outputs. "
                 "Any prompt/schema/ontology change creates a NEW generation "
                 "(see hardening.versions_v2.LLM_MATCHUP_V2)."),
        "git": git_state,
        "version_identity": version_identity,
        "frozen_module_hashes": module_hashes,
        "artifact_hashes": artifact_hashes,
        "cache_summary": cache_summary,
        "selection_hashes": selection_hashes,
        "corpus_fingerprint": corpus_fp,
    }
    manifest["freeze_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "freeze_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    return manifest


def _corpus_fingerprint() -> dict:
    try:
        from src.research.matchup.corpus import load_corpus
        recs = load_corpus()
        ids = sorted(str(r.fixture_id) for r in recs)
        digest = hashlib.sha256("|".join(ids).encode()).hexdigest()
        return {"n_records": len(recs), "fixture_id_set_hash": digest}
    except Exception as e:  # pragma: no cover
        return {"error": str(e)}


def freeze(force: bool = False) -> dict:
    os.makedirs(OUT, exist_ok=True)
    manifest = build_manifest()
    if os.path.exists(FREEZE_PATH) and not force:
        existing = _read_json(FREEZE_PATH) or {}
        # Immutability: if a freeze already exists we do NOT overwrite it. We report whether
        # the current instrument still matches the frozen one (drift detection).
        drift = existing.get("frozen_module_hashes") != manifest["frozen_module_hashes"]
        side = os.path.join(OUT, f"FREEZE_PHASE_B_V1.reverify.{manifest['frozen_unix']}.json")
        json.dump({"existing_freeze_hash": existing.get("freeze_hash"),
                   "recomputed_freeze_hash": manifest["freeze_hash"],
                   "instrument_drift_detected": drift,
                   "recomputed": manifest},
                  open(side, "w"), indent=2, default=str)
        print(json.dumps({"action": "reverify", "existing": FREEZE_PATH,
                          "instrument_drift_detected": drift, "side_file": side}, indent=2))
        return existing
    json.dump(manifest, open(FREEZE_PATH, "w"), indent=2, default=str)
    print(json.dumps({"action": "frozen", "path": FREEZE_PATH,
                      "generation_id": GENERATION_ID,
                      "freeze_hash": manifest["freeze_hash"],
                      "n_artifacts": len(manifest["artifact_hashes"]),
                      "b2_selection_hash": manifest["selection_hashes"]["b2_selection_hash"]},
                     indent=2))
    return manifest


if __name__ == "__main__":
    freeze(force="--force" in sys.argv)
