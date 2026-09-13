"""Pre-Phase-C hardening package (research-only).

This package implements the PRE-PHASE-C HARDENING PATCH. It is strictly UPSTREAM of
predictive evaluation: it does not touch the probability engine, champion, calibration,
thresholds, publication or prospective logic (patch §2). It only hardens the LLM
MEASUREMENT INSTRUMENT.

Design rules honoured throughout:
  * The frozen Phase-B generation (PHASE_B_V1) is never overwritten. Any prompt/schema/
    ontology change creates a NEW generation (LLM_MATCHUP_V2) with fresh version stamps
    and hashes (patch §1, §28).
  * Fail-closed validation is preserved and only ever strengthened (patch §43, §44).
  * No Phase-C outcomes are read or used to tune anything (patch §52, §57).
  * All artifacts are written under research/llm_matchup/out/ only.
"""
