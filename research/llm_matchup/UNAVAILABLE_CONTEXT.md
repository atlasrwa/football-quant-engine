# Unavailable / Unproven Context ("What We Still Cannot Know")

Epistemic discipline (brief §59): information the target engine would benefit from but which
cannot currently be reconstructed PIT-safely. We do not approximate these with questionable
proxies; each is surfaced as an explicit UNKNOWN and gated closed.

| Context | Status | Reason | What would unlock it |
|---|---|---|---|
| **Formation (pre-match)** | `FORMATION_UNKNOWN` | cached lineups have `formation`+`confirmed:true` but **no announcement timestamp**; cannot prove pre-kickoff | a lineup announcement timestamp < kickoff, or a scheduled-lineup feed |
| **Injuries / availability** | `INJURY_STATUS_UNKNOWN` | no injury feed in either audited provider; absence ≠ injury | a PIT-safe injury/availability source with status categories |
| **Weather** | OUT OF SCOPE | no weather source in audited providers | stadium geolocation + historical hourly weather + kickoff ts + PIT source + own OOS ablation |
| **Per-interval score state** | `score_state_conditioning = UNAVAILABLE` | cached `/stats` lacks minute-by-minute running score; only half/regulation aggregates in the fixture object | an interval/timeline score source to split 2H behavior into leading/level/trailing |
| **Neutral venue** | `UNKNOWN` in v1 (but fixture `is_neutral` EXISTS) | field present, not yet wired into the builder | wire `is_neutral` → `context_flags.neutral_venue` (safe v1.1) |
| **Referee identity/tendency (TSA universe)** | partial | referee tendency proven CLEAR on the FootyStats champion corpus (`research/contextual_matchup`), not yet joined into this TSA packet | join `refereeID` + PIT referee card tendency into the packet |
| **Player-level match history / lineup deltas** | not used | no proven PIT vintage; would require confirmed pre-match lineup timing (see formation) | same as formation + player match-history vintage |
| **Exact-formation / exact-opponent cohorts** | inert tiers | formation UNKNOWN; exact-opponent samples too sparse to be reliable | formation unlock + more seasons |

## Consequences honestly stated
- The v1 tactical signal is **behavioral** (crosses, box entries, shot profile, contact,
  2H shift), not formation-based — by necessity, and consistent with "formation is not style".
- 2H-escalation mechanisms are **confounded by score state** and must be reported at reduced
  confidence until interval score-state conditioning exists.
- The strongest known unused signal (referee, already CLEAR for cards) is a **fast follow**:
  it lives in the champion's own corpus and only needs joining into this packet.
