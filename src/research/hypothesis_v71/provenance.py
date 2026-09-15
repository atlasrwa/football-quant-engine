"""V7.1 execution provenance & integrity (`v71_provenance_v1`). Sections 21-23 (closure).

Everything that must be TRUE the moment the confirmatory path runs, recomputed from disk at
preflight rather than trusted from a stale summary. Four independent commitments:

  1. SOURCE GRAPH   -- the actual code that will execute. The transitive first-party import
                       closure of the driver + the execution module is hashed. A source change
                       after freeze causes execution refusal even if no version constant was
                       bumped. (section 22 / mission item 5)
  2. UPSTREAM V7    -- every V7 artifact V7.1 actually consumes, recomputed and compared with
                       the immutable proof. A proof file that is itself unchanged while a file
                       it references has changed must NOT pass. (mission item 6)
  3. FRESH CONTENT  -- the fresh confirmatory corpus, bound at CONTENT level, not just fixture
                       ids: every provider field the engine may consume, the exact null
                       representation, and a normalized-record hash. (mission item 7)
  4. HISTORICAL PIT -- a deterministic content snapshot of the development corpus used to build
                       point-in-time profiles, so it cannot silently mutate between freeze and
                       execution. (mission item 7)

An AUTHORIZATION token binds 1-4 together with the freeze manifest, so the one-way door
requires BOTH the explicit flag AND an artifact whose expected hashes match the live ones.

ZERO SPEND. Static analysis + file hashing + record normalization only. Reads NO outcome:
every field bound here is an INPUT, never an effect, correlation, p-value or terminal state.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os

PROVENANCE_VERSION = "v71_provenance_v1"

ROOT = "/home/ubuntu"


# ======================================================================================
# generic hashing
# ======================================================================================
def sha_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def sha_obj(o) -> str:
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


# ======================================================================================
# 1. source graph -- the code that actually executes
# ======================================================================================
def _module_to_path(mod: str, root: str):
    rel = mod.replace(".", "/")
    for cand in (f"{rel}.py", f"{rel}/__init__.py"):
        if os.path.exists(os.path.join(root, cand)):
            return cand
    return None


def _first_party_imports(path: str, root: str):
    try:
        tree = ast.parse(open(os.path.join(root, path)).read())
    except (SyntaxError, UnicodeDecodeError, FileNotFoundError):
        return set()
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                out.add(node.module)
                for a in node.names:
                    out.add(f"{node.module}.{a.name}")
    return out


def source_closure(entry_paths, *, root: str = ROOT):
    """The transitive first-party file closure reachable from `entry_paths` by import analysis.

    This is the set of source files whose bytes determine what the confirmatory run does. It is
    derived MECHANICALLY, so a module added to the path later cannot silently escape the freeze
    (the D14 defect class, applied to the executable graph rather than a test-reachability set).
    """
    seen, stack = set(), list(entry_paths)
    for p in entry_paths:
        seen.add(p)
    while stack:
        cur = stack.pop()
        for mod in _first_party_imports(cur, root):
            p = _module_to_path(mod, root)
            if p and p not in seen and (p.startswith("src/research/hypothesis_v7")
                                        or p.startswith("research/hypothesis_engine")):
                seen.add(p)
                stack.append(p)
    return sorted(seen)


def source_graph_commitment(entry_paths, *, root: str = ROOT) -> dict:
    """A per-file SHA-256 map over the executable source closure, plus a single roll-up hash.

    `entry_paths` are the driver + execution-module files relative to `root`. The commitment
    binds the executor, every first-party module it transitively imports (the V7.1 package and
    the reused V7 primitives), the endpoint/estimator/engine code and the state code -- because
    all of them are on the import closure of the execution module.
    """
    files = source_closure(entry_paths, root=root)
    per_file = {f: sha_file(os.path.join(root, f)) for f in files
                if os.path.exists(os.path.join(root, f))}
    return {
        "provenance_version": PROVENANCE_VERSION,
        "entry_points": sorted(entry_paths),
        "n_source_files": len(per_file),
        "source_file_hashes": per_file,
        "source_graph_sha256": sha_obj(per_file),
        "derivation": "AST transitive first-party import closure from the entry points",
        "binds_version_constants_only": False,
        "reads_outcomes": False,
    }


def verify_source_graph(frozen: dict, *, root: str = ROOT):
    """Recompute the source graph and compare with a frozen commitment. Returns (ok, problems).

    A changed file, a new file on the closure, or a removed file all fail -- even when no
    version string moved.
    """
    live = source_graph_commitment(frozen["entry_points"], root=root)
    problems = []
    fh, lh = frozen["source_file_hashes"], live["source_file_hashes"]
    for f, h in sorted(fh.items()):
        if f not in lh:
            problems.append(f"source file removed since freeze: {f}")
        elif lh[f] != h:
            problems.append(f"source file changed since freeze: {f}")
    for f in sorted(set(lh) - set(fh)):
        problems.append(f"source file added to the executable closure since freeze: {f}")
    if live["source_graph_sha256"] != frozen["source_graph_sha256"] and not problems:
        problems.append("source graph roll-up hash differs")
    return (not problems, problems, live)


# ======================================================================================
# 2. upstream V7 inputs -- recomputed, not trusted
# ======================================================================================
def upstream_v7_commitment(consumed_paths, *, root: str = ROOT) -> dict:
    """Content hashes of every V7 (and other upstream) artifact V7.1 actually consumes.

    Bound INDEPENDENTLY of V7's own preregistration hashes: verifying the immutability proof
    file is unchanged is not enough, because the proof is a summary that could remain identical
    while a file it lists changed on disk. Here we hash the referenced files themselves.
    """
    per_file = {}
    for p in sorted(set(consumed_paths)):
        ap = os.path.join(root, p)
        per_file[p] = sha_file(ap) if os.path.exists(ap) else None
    return {
        "provenance_version": PROVENANCE_VERSION,
        "n_upstream_inputs": len(per_file),
        "upstream_input_hashes": per_file,
        "upstream_sha256": sha_obj(per_file),
        "note": ("recomputed from the referenced files, so a proof file that is itself "
                 "unchanged cannot mask a changed input it references"),
        "reads_outcomes": False,
    }


def verify_upstream_v7(frozen: dict, *, root: str = ROOT):
    live = upstream_v7_commitment(list(frozen["upstream_input_hashes"]), root=root)
    problems = []
    for f, h in sorted(frozen["upstream_input_hashes"].items()):
        if live["upstream_input_hashes"].get(f) != h:
            problems.append(f"upstream input changed since freeze: {f}")
    return (not problems, problems, live)


# ======================================================================================
# 3 + 4. fresh content commitment & historical PIT snapshot
# ======================================================================================
#: The provider fields the V7.1 engine may consume from a normalized record. Bound at content
#: level so the SAME 317 fixture ids containing DIFFERENT values is refused. This list is the
#: union of what the metric contract can read plus the structural identity fields.
def _record_content(rec, metric_contract) -> dict:
    """A deterministic, effect-free content view of one record: identity + every consumable
    field + the exact null representation (None stays None; it is never coerced)."""
    def _readable(metric):
        row = metric_contract.get(metric)
        if not row or not row.get("block"):
            return None
        blk, fld = row["block"], row["field"]
        if blk == "base":
            b = rec.base or {}
            return [b.get(fld), b.get(row.get("field_away"))]
        pair = (getattr(rec, blk, None) or {}).get(fld)
        return list(pair) if pair else None

    fields = {m: _readable(m) for m in sorted(metric_contract)}
    return {
        "fixture_id": str(rec.fixture_id),
        "season_id": str(rec.season_id),
        "competition": rec.competition,
        "competition_id": str(getattr(rec, "competition_id", "") or ""),
        "kickoff_unix": int(rec.kickoff_unix),
        "home_id": str(rec.home_id),
        "away_id": str(rec.away_id),
        "consumable_fields": fields,
    }


def content_commitment(records, metric_contract) -> dict:
    """A deterministic content commitment over a set of records.

    Binds each record's identity, kickoff, teams, and every provider field the engine can
    consume (with nulls preserved as null). Returns per-fixture normalized-record hashes and a
    single roll-up hash. Computes NOTHING derived: no mean, correlation, effect or terminal
    state is read.
    """
    per_fixture = {}
    for rec in records:
        content = _record_content(rec, metric_contract)
        per_fixture[str(rec.fixture_id)] = sha_obj(content)
    return {
        "provenance_version": PROVENANCE_VERSION,
        "n_records": len(per_fixture),
        "normalized_record_hashes": dict(sorted(per_fixture.items())),
        "content_sha256": sha_obj(per_fixture),
        "binds": ["fixture_id", "season_id", "competition", "competition_id",
                  "kickoff_unix", "home_id", "away_id", "every_consumable_provider_field",
                  "exact_null_representation"],
        "level": "NORMALIZED_RECORD_CONTENT",
        "reads_outcomes": False,
    }


def verify_content(frozen: dict, records, metric_contract):
    """Recompute the content commitment and compare. Same ids + different values must fail."""
    live = content_commitment(records, metric_contract)
    problems = []
    fh = frozen["normalized_record_hashes"]
    lh = live["normalized_record_hashes"]
    if set(fh) != set(lh):
        missing = sorted(set(fh) - set(lh))
        extra = sorted(set(lh) - set(fh))
        if missing:
            problems.append(f"{len(missing)} committed fixtures absent at execution")
        if extra:
            problems.append(f"{len(extra)} unexpected fixtures present at execution")
    changed = [f for f in sorted(set(fh) & set(lh)) if fh[f] != lh[f]]
    if changed:
        problems.append(f"{len(changed)} fixtures now contain different content")
    if live["content_sha256"] != frozen["content_sha256"] and not problems:
        problems.append("content roll-up hash differs")
    return (not problems, problems, live)


def version_stamp() -> dict:
    return {"provenance_version": PROVENANCE_VERSION,
            "commitments": ["source_graph", "upstream_v7", "fresh_content",
                            "historical_pit_snapshot"],
            "source_change_after_freeze_refuses_even_without_version_bump": True,
            "upstream_recomputed_not_trusted_from_proof": True,
            "fresh_bound_at_content_level_not_only_fixture_ids": True,
            "reads_outcomes": False}
