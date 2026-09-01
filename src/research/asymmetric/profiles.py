"""Team_Profiler — continuous, identity-free, point-in-time team profiles.

Responsibility:
    Build for each team exactly one AttackingProfile and one DefensiveProfile as
    continuous feature vectors, computed point-in-time from a rolling-10 /
    expanding-fallback window keyed on team identity across both home and away
    matches and across all leagues. Team identity is used only as an aggregation
    key and never appears as a model feature. Marks profiles insufficient below
    the minimum history and records missing fields per feature.

Scaffold only — the TeamProfiler is implemented in task 3.
"""
