"""Fresh FDR family construction for the Asymmetric Matchup Engine.

Responsibility:
    Build a fresh multiple-testing family (via the reused ResearchFamilyBuilder)
    whose hypothesis count equals the number of target x direction x league
    models tested, with a deterministic family id derived only from this engine's
    run identity, dataset version, and model family. The family is fresh and is
    never inherited from any prior effort (Requirements 8.8, 8.10, 13.3).

Scaffold only — family construction is implemented in task 9.2.
"""
