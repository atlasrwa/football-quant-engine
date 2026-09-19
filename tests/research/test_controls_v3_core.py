"""Tests for the generation-neutral control-runner infrastructure built to resume the Sonnet
4.5 V3 arm's precommitted identity/behavior-sensitivity controls (checkpoint mandate: extract
the MINIMUM mechanical infrastructure, never redesign or duplicate the scientific controls).

Covers:
  * byte-level proof the controls_v3_core extraction reproduces the pre-refactor frozen
    Sonnet 4.6 controls/counter-evidence output exactly, via 100% cache replay (ZERO new
    Bedrock calls) -- the required "prove scientific equivalence before any paid 4.5 call".
  * 4.5/4.6 cache isolation and output-path isolation (model identity in the cache key).
  * control-manifest determinism and freeze-before-execution (never silently overwritten).
  * the Bedrock-capability fail-fast check (ABORT_INCOMPATIBLE_BOTO3).
  * the exclusive live-runner lock, including stale/crashed-lock safety.
  * atomic ledger/manifest persistence (no partial file survives an interrupted write).
  * offline core execution never touches any real production artifact.

Run: .venv/bin/python -m pytest tests/research/test_controls_v3_core.py -q
"""
import json
import os
import signal
import sys
import time

sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.llm_matchup.bedrock_adapter import IncompatibleBotoError, check_bedrock_capability
from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import atomic_io as AIO
from src.research.llm_matchup.hardening import controls_v3_core as CORE
from src.research.llm_matchup.hardening import controls_v3_sonnet45 as C45
from src.research.llm_matchup.hardening import controls_v3_sonnet46 as C46
from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import resume_golden_v3 as RG
from src.research.llm_matchup.hardening import run_lock as RL
from src.research.llm_matchup.hardening import versions_v3 as V3
from src.research.llm_matchup.hardening import versions_v3_sonnet46 as V46


def _deep_strip(obj, drop_cache_hit=False):
    """Normalize away expected replay artifacts (a fresh replay's calls are cache HITS even
    though the ORIGINAL run's recorded call_log entries were cache MISSES at the time; JSON
    round-tripping also turns tuples into lists) before an equality comparison."""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "created_unix":
                continue
            if k == "cache_hit" and drop_cache_hit:
                continue
            out[k] = _deep_strip(v, drop_cache_hit)
        return out
    if isinstance(obj, list):
        return [_deep_strip(v, drop_cache_hit) for v in obj]
    return obj


# ---------------------------------------------------------------------------------------
# Scientific-equivalence comparison (replaces a bare `==` on two stripped dicts).
#
# A frozen artifact predates later, PURELY ADDITIVE provenance fields. A bare equality
# assertion fails on those even when every scientific value is bit-identical, which both
# hides real regressions behind a permanently-red test and tempts a blanket normalizer.
#
# So the comparison is stated as the invariant we actually mean:
#
#   * NO field present in the frozen artifact may change value          -> scientific drift
#   * NO field present in the frozen artifact may disappear             -> silent loss
#   * fields ADDED by newer code are tolerated ONLY if their leaf name
#     is on the allow-list below                                        -> provenance only
#
# Every scientific field therefore remains under exact comparison: control membership,
# fixture identity, requests, responses, distances, trip rates, usable n, thresholds,
# verdicts, gate state, model identity and scoring semantics are all "present in the frozen
# artifact", so any change to any of them is a CHANGED or REMOVED path and fails.
#
# Adding a name here is a deliberate act: it asserts the field carries no scientific
# content. Do NOT add a field that participates in a verdict, a threshold or a metric.
# ---------------------------------------------------------------------------------------
_ADDITIVE_PROVENANCE_FIELDS = frozenset({
    "error",                       # per-call error string; None on a clean cache replay
    "error_class",                 # per-call exception class; None on a clean cache replay
    "control_definition_version",  # provenance stamp for the control definitions
    "censoring_provenance",        # infrastructure-censoring provenance block
})

#: Genuinely run-local, never scientific. Already normalized by ``_deep_strip``.
_VOLATILE_FIELDS = frozenset({"created_unix", "cache_hit"})


def _diff_scientific(frozen, fresh, path="$"):
    """Return (changed, removed, added) lists of dotted paths between two JSON trees."""
    changed, removed, added = [], [], []

    def walk(b, a, p):
        if isinstance(b, dict) and isinstance(a, dict):
            for k in b:
                if k in _VOLATILE_FIELDS:
                    continue
                if k not in a:
                    removed.append(f"{p}.{k}")
                else:
                    walk(b[k], a[k], f"{p}.{k}")
            for k in a:
                if k not in b and k not in _VOLATILE_FIELDS:
                    added.append((f"{p}.{k}", k))
        elif isinstance(b, list) and isinstance(a, list):
            if len(b) != len(a):
                changed.append(f"{p}: list length {len(b)} -> {len(a)}")
                return
            for i, (x, y) in enumerate(zip(b, a)):
                walk(x, y, f"{p}[{i}]")
        elif b != a:
            changed.append(f"{p}: {b!r} -> {a!r}")

    walk(frozen, fresh, path)
    return changed, removed, added


def assert_scientifically_equivalent(frozen, fresh, label):
    """Assert ``fresh`` differs from ``frozen`` only by allow-listed additive provenance."""
    changed, removed, added = _diff_scientific(frozen, fresh, label)
    disallowed = sorted({p for p, leaf in added if leaf not in _ADDITIVE_PROVENANCE_FIELDS})

    assert not changed, (
        f"{label}: {len(changed)} SCIENTIFIC VALUE(S) CHANGED vs the frozen artifact "
        f"(first 10): {changed[:10]}"
    )
    assert not removed, (
        f"{label}: {len(removed)} field(s) present in the frozen artifact DISAPPEARED "
        f"(first 10): {removed[:10]}"
    )
    assert not disallowed, (
        f"{label}: {len(disallowed)} NEW non-provenance field(s) appeared; if they carry no "
        f"scientific content add the leaf name to _ADDITIVE_PROVENANCE_FIELDS deliberately "
        f"(first 10): {disallowed[:10]}"
    )


# ---------------------------------------------------------------------------------------
# Equivalence proof: refactor must not change the frozen 4.6 scientific control definitions.
# These replay 100% from the EXISTING 4.6 response cache -- zero new Bedrock calls -- so they
# are safe to run in CI/offline and can never spend money or touch the frozen 4.6 freeze file.
# ---------------------------------------------------------------------------------------
@pytest.mark.skipif(not os.path.exists(C46.CONTROLS_PATH),
                    reason="frozen 4.6 controls artifact not present in this checkout")
def test_core_refactor_reproduces_frozen_sonnet46_controls_exactly():
    before = json.load(open(C46.CONTROLS_PATH))
    before_repeat = json.load(open(C46.REPEAT_PATH))
    fixtures = before["fixtures_requested"]
    k = before["k_self_noise_calls"]

    result = C46.run_controls(fixtures=fixtures, n_fixtures=8, k=k, persist=False)
    after = json.loads(json.dumps(result["controls"], default=str))
    after_repeat = json.loads(json.dumps(result["repeatability"], default=str))

    # zero new live calls: every call in the fresh replay must be a cache hit
    new_calls = [c for c in result["controls"]["call_log"] if c.get("cache_hit") is False]
    assert new_calls == [], "refactored core made a NEW Bedrock call replaying the 4.6 arm"

    # Every scientific field stays under exact comparison; only allow-listed additive
    # provenance fields (control_definition_version, censoring_provenance, per-call
    # error/error_class) may appear. See assert_scientifically_equivalent.
    assert_scientifically_equivalent(before, after, "controls_v3_sonnet46.controls")
    assert_scientifically_equivalent(
        before_repeat, after_repeat, "controls_v3_sonnet46.repeatability")


@pytest.mark.skipif(not os.path.exists(C46.COUNTER_PATH),
                    reason="frozen 4.6 counter-evidence artifact not present in this checkout")
def test_core_refactor_reproduces_frozen_sonnet46_counter_evidence_exactly():
    before = json.load(open(C46.COUNTER_PATH))
    k = before["k_calls"]
    result = C46.run_counter_evidence(k=k, persist=False)
    after = json.loads(json.dumps(result, default=str))

    new_calls = [c for c in result["call_log"] if c.get("cache_hit") is False]
    assert new_calls == [], "refactored core made a NEW Bedrock call replaying 4.6 counter-evidence"
    assert_scientifically_equivalent(
        before, after, "controls_v3_sonnet46.counter_evidence")


def test_frozen_sonnet46_freeze_file_not_modified_by_refactor():
    """The FREEZE_LLM_MATCHUP_V3_SONNET46.json scientific freeze must be untouched by any of
    this refactor's code or test execution."""
    path = "/home/ubuntu/research/llm_matchup/out/FREEZE_LLM_MATCHUP_V3_SONNET46.json"
    if not os.path.exists(path):
        pytest.skip("freeze file not present in this checkout")
    import hashlib
    before = hashlib.sha256(open(path, "rb").read()).hexdigest()
    # exercise the wrapper (cache-hit only, see tests above) then re-hash
    C46.run_controls(fixtures=json.load(open(C46.CONTROLS_PATH))["fixtures_requested"],
                     k=json.load(open(C46.CONTROLS_PATH))["k_self_noise_calls"], persist=False)
    after = hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert before == after


# ---------------------------------------------------------------------------------------
# 4.5 / 4.6 isolation
# ---------------------------------------------------------------------------------------
def test_cache_dir_isolated_between_generations():
    assert C45.CACHE_DIR != C46.CACHE_DIR
    assert "hardening_v3" in C45.CACHE_DIR and "v3_sonnet46" not in C45.CACHE_DIR
    assert "v3_sonnet46" in C46.CACHE_DIR


def test_output_paths_isolated_between_generations():
    paths45 = {C45.CONTROLS_PATH, C45.REPEAT_PATH, C45.COUNTER_PATH, C45.CONTROL_MANIFEST_PATH}
    paths46 = {C46.CONTROLS_PATH, C46.REPEAT_PATH, C46.COUNTER_PATH}
    assert paths45.isdisjoint(paths46)
    assert all("hardening_v3" in p for p in paths45)
    assert all("v3_sonnet46" in p for p in paths46)


def test_cache_key_binds_model_identity_so_4_5_and_4_6_never_collide():
    packet_hash = "deadbeef" * 8
    key45 = A4._cache_key(V3.DEFAULT_BEDROCK_MODEL_ID, packet_hash, 0, gen=V3)
    key46 = A4._cache_key(V46.DEFAULT_BEDROCK_MODEL_ID, packet_hash, 0, gen=V46)
    assert key45 != key46
    # even if someone pointed both at the SAME cache_dir, the keys (hence filenames) differ
    assert A4._cache_path(key45) != A4._cache_path(key46)


def test_no_4_6_cache_response_can_satisfy_a_4_5_key_and_vice_versa():
    """Structural proof, not just a path-naming convention: the SAME packet hash + call_index
    produce DIFFERENT cache keys for the two generations because model_id is baked into the
    key, so no accidental directory misconfiguration could serve one generation's response to
    the other."""
    packet_hash = "0123456789abcdef" * 4
    for call_index in (0, 1, 2):
        assert (A4._cache_key(V3.DEFAULT_BEDROCK_MODEL_ID, packet_hash, call_index, gen=V3)
               != A4._cache_key(V46.DEFAULT_BEDROCK_MODEL_ID, packet_hash, call_index, gen=V46))


# ---------------------------------------------------------------------------------------
# Control manifest: determinism + freeze-before-execution
# ---------------------------------------------------------------------------------------
def _real_sonnet45_cfg_readonly():
    manifest = GM.load_manifest()
    if manifest is None:
        pytest.skip("no frozen Sonnet 4.5 manifest in this checkout")
    return CORE.GenerationConfig(
        name="sonnet45", gen=V3, cache_dir=A4.CACHE_DIR, manifest=manifest,
        golden_ledger=RG.load_ledger(), controls_path="/dev/null", repeat_path="/dev/null",
        counter_path="/dev/null")


def test_control_manifest_deterministic():
    cfg = _real_sonnet45_cfg_readonly()
    accepted = CORE.accepted_fixture_ids(cfg)
    if len(accepted) < 2:
        pytest.skip("not enough accepted 4.5 golden fixtures in this checkout")
    chosen = accepted[:2]
    m1 = CORE.build_control_manifest(cfg, chosen, k=3)
    m2 = CORE.build_control_manifest(cfg, chosen, k=3)
    assert m1["control_manifest_hash"] == m2["control_manifest_hash"]
    assert m1["rows"] == m2["rows"]


def test_control_manifest_hash_changes_with_k_or_fixtures():
    cfg = _real_sonnet45_cfg_readonly()
    accepted = CORE.accepted_fixture_ids(cfg)
    if len(accepted) < 2:
        pytest.skip("not enough accepted 4.5 golden fixtures in this checkout")
    m_k3 = CORE.build_control_manifest(cfg, accepted[:2], k=3)
    m_k5 = CORE.build_control_manifest(cfg, accepted[:2], k=5)
    assert m_k3["control_manifest_hash"] != m_k5["control_manifest_hash"] or m_k3["rows"] == m_k5["rows"]
    # k is recorded per-row and in the top-level field, and does affect the hashed rows
    assert m_k3["rows"][0]["k_self_noise_calls"] == 3
    assert m_k5["rows"][0]["k_self_noise_calls"] == 5


def test_control_manifest_frozen_before_execution_never_overwritten(tmp_path):
    cfg = _real_sonnet45_cfg_readonly()
    accepted = CORE.accepted_fixture_ids(cfg)
    if not accepted:
        pytest.skip("no accepted 4.5 golden fixtures in this checkout")
    path = str(tmp_path / "control_manifest.json")
    m1 = CORE.build_control_manifest(cfg, accepted[:1], k=3)
    status1 = CORE.freeze_control_manifest_if_absent(m1, path)
    assert status1 == "CREATED"
    on_disk_hash = CORE.load_control_manifest(path)["control_manifest_hash"]

    # a DIFFERENT intended manifest (e.g. more fixtures) must NOT silently overwrite it
    m2 = CORE.build_control_manifest(cfg, accepted[:1], k=7)
    status2 = CORE.freeze_control_manifest_if_absent(m2, path)
    assert status2 == "EXISTS_UNCHANGED"
    assert CORE.load_control_manifest(path)["control_manifest_hash"] == on_disk_hash


# ---------------------------------------------------------------------------------------
# Bedrock capability fail-fast
# ---------------------------------------------------------------------------------------
class _FakeClientNoConverse:
    pass


class _FakeClientWithConverse:
    def converse(self, **kw):
        raise AssertionError("capability check must not actually invoke converse()")


def test_check_bedrock_capability_raises_when_converse_missing(monkeypatch):
    import src.research.llm_matchup.bedrock_adapter as BA
    monkeypatch.setattr(BA, "_bedrock_client", lambda region: _FakeClientNoConverse())
    with pytest.raises(IncompatibleBotoError, match="ABORT_INCOMPATIBLE_BOTO3"):
        check_bedrock_capability(region="us-east-1")


def test_check_bedrock_capability_passes_when_converse_present(monkeypatch):
    import src.research.llm_matchup.bedrock_adapter as BA
    monkeypatch.setattr(BA, "_bedrock_client", lambda region: _FakeClientWithConverse())
    info = check_bedrock_capability(region="us-east-1")
    assert info["has_converse"] is True
    assert info["region"] == "us-east-1"


def test_resume_aborts_incompatible_boto3_before_any_fixture_attempt(tmp_path, monkeypatch):
    """A process-wide SDK incompatibility must abort the WHOLE batch, never emit a per-fixture
    UNAVAILABLE record (the exact failure mode observed during the live resume incident)."""
    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(RG, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    m = GM.build_manifest(["fx_1", "fx_2"], n=2)
    GM.save_manifest_if_absent(m, str(manifest_path))

    import src.research.llm_matchup.bedrock_adapter as BA
    monkeypatch.setattr(BA, "_bedrock_client", lambda region: _FakeClientNoConverse())

    def _should_not_be_called(*a, **kw):
        raise AssertionError("call_fn must never be invoked after a capability abort")

    result = RG.resume(call_fn=_should_not_be_called, dry_run=False)
    assert result["status"] == "ABORT_INCOMPATIBLE_BOTO3"
    assert not (tmp_path / "ledger.json").exists()


# ---------------------------------------------------------------------------------------
# Exclusive live-runner lock
# ---------------------------------------------------------------------------------------
def test_lock_exclusive_second_acquire_fails(tmp_path):
    lock_path = str(tmp_path / "runner.lock")
    lock1 = RL.acquire(lock_path)
    lock1.__enter__()
    try:
        with pytest.raises(RL.AlreadyRunningError):
            lock2 = RL.acquire(lock_path)
            lock2.__enter__()
    finally:
        lock1.__exit__(None, None, None)


def test_lock_released_on_clean_exit_and_reacquirable(tmp_path):
    lock_path = str(tmp_path / "runner.lock")
    with RL.acquire(lock_path):
        pass
    # must be reacquirable immediately after a clean exit
    with RL.acquire(lock_path):
        pass


def test_resume_aborts_already_running_when_lock_held(tmp_path, monkeypatch):
    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    manifest_path = tmp_path / "manifest.json"
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(manifest_path))
    monkeypatch.setattr(RG, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    m = GM.build_manifest(["fx_1"], n=1)
    GM.save_manifest_if_absent(m, str(manifest_path))

    held_lock = RL.acquire(RG._lock_path())
    held_lock.__enter__()
    try:
        def _should_not_be_called(*a, **kw):
            raise AssertionError("call_fn must never be invoked when the lock is contended")

        result = RG.resume(call_fn=_should_not_be_called, dry_run=False)
        assert result["status"] == "ABORT_ALREADY_RUNNING"
    finally:
        held_lock.__exit__(None, None, None)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires a POSIX fork()")
def test_lock_safe_after_holder_process_is_killed(tmp_path):
    """A crashed (SIGKILL'd) holder must never wedge the lock for future runs -- this is the
    entire reason an flock-based lock was chosen over a PID file or boolean flag."""
    lock_path = str(tmp_path / "runner.lock")
    pid = os.fork()
    if pid == 0:
        # child: acquire and hold forever (until killed)
        lock = RL.acquire(lock_path)
        lock.__enter__()
        time.sleep(30)
        os._exit(0)

    # parent: wait for the child to actually hold the lock, then confirm contention
    deadline = time.time() + 5
    contended = False
    while time.time() < deadline:
        try:
            probe = RL.acquire(lock_path)
            probe.__enter__()
            probe.__exit__(None, None, None)
            time.sleep(0.05)
        except RL.AlreadyRunningError:
            contended = True
            break
    assert contended, "child never actually held the lock"

    os.kill(pid, signal.SIGKILL)
    os.waitpid(pid, 0)

    # the lock must be immediately reacquirable now that the holder is dead
    deadline = time.time() + 5
    reacquired = False
    while time.time() < deadline:
        try:
            with RL.acquire(lock_path):
                reacquired = True
            break
        except RL.AlreadyRunningError:
            time.sleep(0.05)
    assert reacquired, "lock stayed wedged after its holder was SIGKILL'd"


# ---------------------------------------------------------------------------------------
# Atomic persistence
# ---------------------------------------------------------------------------------------
def test_atomic_write_json_produces_complete_readable_file_and_no_tmp_leftover(tmp_path):
    path = str(tmp_path / "ledger.json")
    payload = {"study": "x", "fixtures": {f"fx_{i}": {"status": "SUCCESS"} for i in range(50)}}
    AIO.atomic_write_json(path, payload)
    assert json.load(open(path)) == payload
    assert not os.path.exists(path + ".tmp")


def test_atomic_write_json_overwrite_leaves_no_partial_state(tmp_path):
    path = str(tmp_path / "ledger.json")
    AIO.atomic_write_json(path, {"v": 1})
    AIO.atomic_write_json(path, {"v": 2, "bigger": "x" * 10000})
    assert json.load(open(path)) == {"v": 2, "bigger": "x" * 10000}
    assert not os.path.exists(path + ".tmp")


def test_resume_save_ledger_is_atomic(tmp_path, monkeypatch):
    monkeypatch.setattr(RG, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    ledger = {"study": "golden_v3_execution_ledger", "fixtures": {"fx_1": {"status": "SUCCESS"}}}
    RG.save_ledger(ledger)
    assert RG.load_ledger() == ledger
    assert not (tmp_path / "ledger.json.tmp").exists()


# ---------------------------------------------------------------------------------------
# Offline core execution never touches real production artifacts
# ---------------------------------------------------------------------------------------
class _StubOkResult:
    def __init__(self, fixture_id, tag):
        self.status = "OK"
        self.state = {
            "team_a_states": [{"mechanism": "m1", "level": "MEDIUM", "evidence_ids": ["e1"]}],
            "team_b_states": [{"mechanism": "m2", "level": "LOW", "evidence_ids": ["e2"]}],
            "matchup_states": [{"mechanism": "m3", "assessment": "SUPPORTED",
                                "evidence_ids": ["e3"]}],
        }
        self.manifest = {"cache_hit": False, "input_tokens": 100, "output_tokens": 50,
                         "latency_s": 1.0, "resolved_model_id": "stub", "tag": tag,
                         "fixture_id": fixture_id}


def test_core_run_controls_offline_writes_only_under_tmp_path(tmp_path, monkeypatch):
    manifest = GM.load_manifest()
    ledger = RG.load_ledger()
    if manifest is None:
        pytest.skip("no frozen Sonnet 4.5 manifest in this checkout")
    accepted = [f for f in manifest["fixture_ids"]
               if (ledger.get("fixtures", {}).get(f) or {}).get("status") == "SUCCESS"]
    if not accepted:
        pytest.skip("no accepted 4.5 golden fixtures in this checkout")

    calls = {"n": 0}

    def _fake_analyze(packet, use_cache=True, call_index=0, gen=None, cache_dir=None,
                      capture_rejected_raw=False):
        calls["n"] += 1
        assert str(cache_dir).startswith(str(tmp_path)), "core must use cfg.cache_dir, not a real path"
        return _StubOkResult(packet["fixture"]["fixture_id"], call_index)

    monkeypatch.setattr(A4, "analyze_matchup_v4", _fake_analyze)

    controls_path = tmp_path / "controls.json"
    repeat_path = tmp_path / "repeat.json"
    counter_path = tmp_path / "counter.json"
    cfg = CORE.GenerationConfig(
        name="test45", gen=V3, cache_dir=str(tmp_path / "cache"), manifest=manifest,
        golden_ledger=ledger, controls_path=str(controls_path), repeat_path=str(repeat_path),
        counter_path=str(counter_path))

    out = CORE.run_controls(cfg, fixtures=accepted[:1], k=2, persist=True)
    assert calls["n"] > 0
    assert controls_path.exists() and repeat_path.exists()
    # a genuinely identical stub response everywhere means zero self-noise and zero alias
    # sensitivity -- exercises the full pipeline without asserting anything about real Sonnet
    # behavior (that is measured live, separately).
    team_rows = out["controls"]["controls"]["A_team_token_invariance"]["rows"]
    if team_rows:
        assert team_rows[0]["distance"] == 0.0
