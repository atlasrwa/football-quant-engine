# V5A2 — Transport Preflight Report

**ZERO SPEND.** No Bedrock client was used to make a request; the preflight was exercised
against the real local environments and against stub clients.

---

## 1. Defect D4, stated plainly

V5A.1's authorized execution made three calls, each of which died with:

```
AttributeError: 'BedrockRuntime' object has no attribute 'converse'
```

The driver ran under the **system interpreter** (`/usr/bin/python3`), whose boto3 is
**1.34.46** — a version predating the Converse API entirely. $0 was spent, the
consecutive-transport-failure rule fired correctly, and the entire authorized window was
consumed by an environment mistake that was knowable before the first call.

The V3 run had hit the same class of problem. The V5A.1 authorization explicitly said not to
repeat it. **It was repeated because nothing in the apparatus actually checked** — the
requirement lived in the authorization prose.

> **A requirement that is not asserted is not a requirement.**

## 2. The check

`v5a2_transport.preflight(client)` raises `TransportPreflightFailure` **before any request is
constructed**, and `_execute_v5a2.py` calls it while `spend_usd == 0.0`.

The gate is `hasattr(client, "converse")` — **the property the driver actually depends on**,
not a version-string comparison. A version comparison is a *proxy* for the capability, and
proxies are how D4 happened.

The environment is recorded in the execution log regardless of outcome, so a later reader
can attribute any result to an interpreter:

```
python_executable, python_version, boto3_version, boto3_path,
botocore_version, botocore_path, client_type,
has_converse, has_converse_stream
```

## 3. Empirical verification

Run against the two real interpreters on this machine and against stub clients:

| Environment | boto3 | `has_converse` | Preflight |
|---|---|---|---|
| `/usr/bin/python3` (the V5A.1 failure environment) | **1.34.46** | False | **REJECTED at $0.00** |
| `/home/ubuntu/.venv/bin/python3` (approved) | 1.43.93 | True | **ACCEPTED** |
| stub client with only `invoke_model` | — | False | **REJECTED** |
| stub client with `converse` | — | True | **ACCEPTED** |

The actual boto3 1.34.46 that caused D4 is rejected pre-spend. This is not a simulation of
the failure — it is the failure environment, refused.

`test_transport_preflight_rejects_client_without_converse` asserts the check works against a
stub, so the guarantee does not depend on keeping an obsolete boto3 installed.

## 4. Transport accounting (§17)

`TransportAccounting` separates three outcomes V5A.1's log could not tell apart:

| Outcome | Counted as | Can cost money |
|---|---|---|
| never reached the provider | `n_transport_failures` | no |
| reached provider, returned | `n_charged` | yes |
| ceiling would be exceeded | not attempted | no |

`spend_usd` and `n_charged` move together, so a transport failure can never inflate the
spend estimate, and `n_consecutive_transport_failures` resets on the first successful call.
`test_transport_accounting_never_charges_a_failed_call` asserts both.

## 5. Execution-path assertions

`_execute_v5a2.py` is written and hashed into the preregistration **before** authorization,
so the human authorizes a known driver rather than one written afterwards. It refuses to run
without `--i-have-authorization` and prints the cost model instead.

Before the first paid call, at zero spend, it:

1. re-verifies every V5A.2 module hash against the preregistration;
2. re-verifies every **frozen upstream** module hash (V2/V3/V5A/V5A.1 modules), so reaching
   into frozen territory aborts the run;
3. re-verifies `schema_v3`'s content hash;
4. re-verifies every packet hash **and** the serialized request bytes for all 38 calls;
5. re-verifies the CHAMPION artifact hash;
6. runs the transport preflight.

Any failure aborts at **$0.00**. Per call it consults the frozen
`v5a2_evaluator.classify_stop`, and it writes each raw response to disk **before** scoring
it, so a scoring bug can never destroy paid data.

### On the cost guard, stated precisely

There are two cost controls and they are not equally strong.

- **Primary:** the post-call rule `V5A2_STOP_COST_CEILING` in `classify_stop`, evaluated
  after every charged call against actual cumulative spend.
- **Terminal, secondary:** a pre-call check that refuses to *start* a call the run could not
  afford at worst case.

The secondary guard is deliberately weak by construction, and the report should not imply
otherwise: the preregistered ceiling already prices **all 38 calls at the full
`max_tokens`**, so cumulative spend can only approach it if real usage outruns the
calibration. It therefore fires late in a run or not at all. It projects using the larger of
the preregistered input estimate and the **largest input actually observed so far**, because
a calibration that runs low is precisely how a ceiling gets crossed — but it remains a belt
over the braces, not the braces.

`V5A2_TRANSPORT_PREFLIGHT_VALIDATED`
