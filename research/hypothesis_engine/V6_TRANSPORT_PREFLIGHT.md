# V6 — Transport Preflight Report (§29)

**Zero spend.** `v6_transport` reuses the frozen `v5a2_transport` preflight verbatim (same `TransportPreflightFailure`, `TransportAccounting`, `environment_report` objects — asserted in `test_transport_reuses_v5a2`).

## 1. What the preflight verifies

- **`hasattr(client, "converse")`** — the capability the driver actually depends on, checked on the client object, not a version string (a version compare is a proxy, and proxies are how defect D4 happened). Raises `TransportPreflightFailure` before the first paid call, at zero spend.
- **Model id format** — `us.anthropic.claude-sonnet-4-6` is a cross-region inference-profile id; the format is checked, a malformed id aborts.
- **Interpreter / boto3 / botocore** version and path, recorded for attribution.

`TransportAccounting` distinguishes attempted / charged / transport-failure, so a transport failure can never inflate spend; the consecutive-failure counter resets on a charged call.

## 2. GetInferenceProfile is deliberately NOT called (§29)

§29 permits omitting the `bedrock:GetInferenceProfile` describe call when the execution role lacks that permission AND invocation through the frozen profile has been demonstrated. Both hold:

- the id is an inference-profile id; describing it requires `bedrock:GetInferenceProfile`, not assumed held;
- invocation through this exact profile was demonstrated by V5A.1's six paid Converse calls (billed responses returned).

A describe call would verify metadata the invocation path does not consult; the invocation is the stronger evidence and it exists. `preflight_profile_note()` records what is and is not verified. **This is a documented limitation, not a silent omission.**

## 3. The current environment — the D4 guard is working

`environment_report()` in this workspace:

```
python_executable : /usr/bin/python3
python_version    : 3.12.3
boto3_version     : 1.34.46
botocore_version  : 1.34.46
```

boto3 **1.34.46 predates the Converse API** (first in 1.35.0). This is exactly defect D4 from V5A.1. Therefore `v6_transport.preflight(client)` against a real client here **raises `TransportPreflightFailure` and would abort the run at zero spend** — which is the intended behaviour. The apparatus refuses to burn an authorization on `AttributeError`s.

**Implication for spend authorization:** before any paid run, the driver must execute under an interpreter whose boto3 is ≥ 1.35.0 (so `hasattr(client, "converse")` is true). The preflight enforces this mechanically; no code change is needed, only the correct execution environment. Until then, the preflight’s refusal is correct and protective, not a defect in V6.

## 4. Verified (test suite)

| test | result |
|---|---|
| `test_transport_preflight_rejects_client_without_converse` | raises ✓ |
| `test_transport_preflight_accepts_converse_capable_client` | passes, `get_inference_profile_called=False` ✓ |
| `test_transport_accounting_never_charges_a_failed_call` | spend stays 0 on failure ✓ |
| `test_transport_reuses_v5a2` | same objects ✓ |
