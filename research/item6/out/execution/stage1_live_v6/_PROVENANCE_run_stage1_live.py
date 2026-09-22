"""Execute the authorized Item 6 Stage-1 LIVE run. Human authorization is EXTERNAL:
AUTHORIZED_EXECUTION_HEAD=b79051f45905095facc41f2bcad510bdc1de5728, ceiling $30.00.

Code root = the isolated detached worktree at the authorized HEAD.
Data root  = the same worktree (immutable corpus snapshot; packets verified to re-materialize
             byte-identically to the frozen V5 set before launch).
Out dir    = the MAIN checkout, so the evidence freeze can be committed on the branch.
No treatment logic lives here: it calls the committed live driver unchanged.
"""
import json, os, sys, time, traceback

W = "/home/ubuntu/.item6_exec_worktree"
OUT = "/home/ubuntu/research/item6/out/execution/stage1_live_v6"
AUTH = "b79051f45905095facc41f2bcad510bdc1de5728"
MANIFEST = "research/item6/ITEM6_STAGE1_RUN_MANIFEST_V6.json"

sys.path.insert(0, W)
os.chdir(W)
from src.research.item6.execution import live_driver as LD   # noqa: E402

os.makedirs(OUT, exist_ok=True)
t0 = time.time()
print(f"[stage1-live] start {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}", flush=True)
print(f"[stage1-live] root={W} out={OUT} authorized_head={AUTH} ceiling=30.00", flush=True)
try:
    summary = LD.run_live(MANIFEST, authorized_ceiling_usd=30.00,
                          authorized_execution_head=AUTH, out_dir=OUT, root=W, data_root=W)
    with open(f"{OUT}/RUN_LIVE_SUMMARY.json", "w") as f:
        json.dump(summary, f, indent=1, sort_keys=True, default=str)
    ok = sum(1 for r in summary["results"] if r.get("status") == "TRANSPORT_OK")
    print(f"[stage1-live] RUN_LIVE_COMPLETE results={len(summary['results'])} transport_ok={ok}",
          flush=True)
    print(f"[stage1-live] spend_ledger={json.dumps(summary['spend_ledger'])}", flush=True)
    print(f"[stage1-live] count_tokens={json.dumps(summary['count_tokens_counters'])}", flush=True)
except BaseException as e:                                  # noqa: BLE001
    traceback.print_exc()
    print(f"[stage1-live] RUN_LIVE_ABORTED {type(e).__name__}: {str(e)[:800]}", flush=True)
    raise
finally:
    # the spend ledger + attempt markers + receipts are written durably by the runner itself,
    # so a mid-run abort still leaves a reconcilable on-disk ledger.
    print(f"[stage1-live] elapsed_s={time.time() - t0:.1f}", flush=True)
