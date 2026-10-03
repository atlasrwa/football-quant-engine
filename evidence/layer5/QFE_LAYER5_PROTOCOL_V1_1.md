# QFE V2 Layer 5 — Market Surface / Disagreement Protocol V1.1

Protocol hash: `0e3928354f7da00e74c9bacd43b02cdace1556d0d8e11544f9ae0bb49fab2fe5`

Status: **PREREGISTERED V1.1 — PROTECTED STILL SEALED**

V1 (`ecb72d508f421fbbcd45e4623acc50df882c178af83743365ed4be4e2dcebf65`) is retained immutable but classified **ABORTED_PRE_PROTECTED_DESIGN_DEFECT** because bookmaker selection was not deterministic. No protected outcome or protected market-relative score had been opened.

## V1.1 repair

- Primary source: QFE prospective capture store using direct TheStatsAPI `mt_*` identity and QFE-owned observation timestamps.
- Fixed bookmaker hierarchy: `pinnacle → bet365 → betmgm-uk → paddy-power`.
- Bookmaker selection is based only on structural market availability.
- After a bookmaker and latest structurally complete bundle are selected, any odds/overround/de-vig/CDF-coherence failure causes **ABSTAIN**. There is no fallback to a lower-ranked bookmaker or older bundle.
- Legacy alerts/CLV stores are coverage-audit-only and are not blended into the protected market manifest.
- Legacy target-aware LLM/M0 feature matrices are forbidden as Layer 5 market evidence.
- Primary protected capture source does not contain team-corner concepts, so protected market-relative team-corner scoring is unsupported in V1.1 rather than synthesized.

All other V1 market-surface, support, reliability, cross-line and non-max-gap selection rules remain unchanged.
