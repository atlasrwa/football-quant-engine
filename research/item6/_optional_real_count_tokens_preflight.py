"""OPTIONAL real AWS CountTokens preflight for Item 6 Stage-1 (SEPARATE, explicit command).

This is NOT part of the ordinary (network-killed) unit suite and is NOT run by the readiness
amendment. It performs exactly ONE real AWS Bedrock `CountTokens` control call against the
frozen foundation-model id, using a point-in-time-safe fixture #1 skeleton request, to
demonstrate the live counting path end-to-end.

WHY THIS IS SAFE (and not a treatment):
  * CountTokens is a NON-GENERATIVE control operation: it returns only an input-token count,
    runs no inference, produces no model output, and (per AWS) incurs no generation charge;
  * it does NOT consume one of the 120 scientific treatment slots (the runner's paid-call
    ledger is untouched -- this script does not use the runner);
  * it uses the fixture #1 SKELETON request (empty evidence packet) -- point-in-time safe;
  * NO Converse / generation call follows. This script never calls converse().

It runs ONLY when explicitly enabled:  ITEM6_REAL_COUNT_TOKENS_PREFLIGHT=1
Otherwise it prints that it was skipped and requires authorization. If any uncertainty about
non-inference/billing arises, skip it -- the unit suite already proves the path with mocks.

Usage (explicit, outside pytest):
    ITEM6_REAL_COUNT_TOKENS_PREFLIGHT=1 python -m research.item6._optional_real_count_tokens_preflight
"""
from __future__ import annotations

import json
import os
import sys

ROOT = "/home/ubuntu"


def main() -> int:
    if os.environ.get("ITEM6_REAL_COUNT_TOKENS_PREFLIGHT") != "1":
        print(json.dumps({
            "performed": False,
            "reason": "requires explicit ITEM6_REAL_COUNT_TOKENS_PREFLIGHT=1",
            "note": ("This optional probe makes ONE real non-generative CountTokens call and "
                     "NO Converse call. It is a separate authorized command, not part of the "
                     "unit suite."),
        }, indent=1))
        return 0

    from src.research.item6.execution import request_builder as RB
    from src.research.item6.execution import token_counter as TC
    from src.research.item6.execution.live_transport import BedrockStage1Transport

    cohort = json.load(open(f"{ROOT}/research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"))
    fx = cohort["fixtures"][0]
    req = RB.canonical_request(fx, RB.load_frozen_system_text(ROOT), evidence_packet=None)
    payload = TC.build_count_tokens_input(req)

    transport = BedrockStage1Transport.from_frozen_config()
    # ONE real CountTokens call. NO converse() call anywhere.
    resp = transport.count_tokens(**payload)
    input_tokens = int(resp["inputTokens"])
    print(json.dumps({
        "performed": True,
        "operation": "bedrock-runtime:CountTokens",
        "is_inference_treatment": False,
        "converse_called": False,
        "count_model_id": transport.count_model_id,
        "converse_model_id": transport.converse_model_id,
        "fixture_id": fx["fixture_id"],
        "provider_counted_input_tokens": input_tokens,
        "n_treatment_slots_consumed": 0,
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
