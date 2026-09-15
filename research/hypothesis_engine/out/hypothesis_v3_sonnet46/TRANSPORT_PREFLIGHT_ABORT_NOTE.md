# Aborted transport preflight — preserved, not deleted

The first invocation of `_run_v3.py` used the system interpreter (`/usr/bin/python3`,
boto3 1.34.46), which predates the Bedrock `converse` API. All 12 attempted calls raised
`AttributeError: 'BedrockRuntime' object has no attribute 'converse'` **before any request
reached AWS**.

    calls attempted      12
    calls that reached the model   0
    input tokens billed  0
    output tokens billed 0
    cost                 $0.0000

No valid paid inference occurred, so the preregistration's post-authorization freeze
(which binds "after the first valid paid inference") had not yet engaged. Nothing
scientific was changed: the fix is the interpreter only
(`/home/ubuntu/.venv/bin/python`, boto3 1.43.93 — the same environment the frozen V2 run
used). Manifest, packets, prompt, schema, contract, thresholds and stop rule are untouched
and re-verified by the runner's preflight.

The 12 censored records are preserved verbatim in
`hypothesis_states.ABORTED_TRANSPORT_PREFLIGHT.jsonl`. They are NOT part of the battery:
they contacted no model and carry no model behaviour. The battery proper begins with a
clean `hypothesis_states.jsonl` so that all 56 frozen calls execute rather than 12 being
skipped by resume logic for an environmental reason.
