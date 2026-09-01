"""Cached corpus loaders (zero-API) for the Rich and Broad corpora.

Responsibility:
    RichCorpusLoader loads the ~3,189-match TheStatsAPI corpus and
    BroadCorpusLoader loads the ~15,362-match FootyStats corpus, both from cache
    only. Loaders accept an injected data source that reads cache exclusively,
    must never import the live-fetch path, and preserve NULL != ZERO field
    semantics from the normalizer (Requirements 4.1, 4.2, 12.1, 12.2).

Scaffold only — loaders are implemented in task 2.1.
"""
