"""Research-only contextual-matchup feature layer.

ISOLATED from production commitment generation. Consumes the dual-provider research
datasets (FootyStats corpus + TheStatsAPI rich adapted corpus) and produces
point-in-time-safe matchup/context features with full provenance.

Nothing in this package is imported by the champion, the forecast broadcaster, the
forward loop, or any publication path. It exists solely for chronological OOS
research comparing a contextual-matchup CHALLENGER against the frozen Pilot-C champion.
"""
