"""CappedLiveFetcher — capped, reported live-fetch fallback for the CLI only.

Responsibility:
    Provide the ONLY place live API requests may occur, and only when required
    fixture/team data is absent from cache. Admits spend up to a configured cap,
    refuses a fetch that would breach the cap (setting cap_exceeded), and reports
    the spend incurred. Confined to the CLI package and never imported into the
    build/backtest path, which is strictly zero-API (Requirements 9.16, 12.3,
    12.4).

Scaffold only — the fetcher is implemented in task 11.2.
"""
