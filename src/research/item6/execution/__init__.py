"""ITEM 6 Stage-1 EXECUTION bindings (amendment closing authorization blockers B1-B5).

This package freezes the EXECUTION and SPEND semantics for the already-frozen Item 6
Stage-1 scientific apparatus. It changes NO scientific artifact: not the prompt, schema,
baseline-coverage spec, baseline-equivalence detector, formalizer, quality protocol, gate,
cohort, endpoints, denominators, Stage-2 firewall, or CHAMPION.

Modules:
  execution_status  - closed execution-status taxonomy + one-attempt-per-fixture policy (B3)
  request_builder   - deterministic canonical Converse request builder + per-request byte
                      budget; binds the frozen prompt body + mechanism tool schema (B1/B4)
  spend_guard       - durable monotonic pre-call monetary reservation ledger + hard stops (B4)
  runner            - minimal research-only live runner enforcing all frozen semantics

Every module is import-safe and performs NO network call on import. The live runner only
touches the network when explicitly handed a real Bedrock `converse` client AND after the
attempt marker, call-cap, and monetary-reservation checks pass.
"""
