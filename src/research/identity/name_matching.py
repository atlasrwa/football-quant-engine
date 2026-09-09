"""OFFLINE-ONLY name-similarity suggestions for identity resolution.

WARNING: Nothing in this module may be used in the production prediction path.
Fuzzy name matching is error-prone (e.g. "Manchester United" vs "Manchester
City"); it exists here solely to *suggest* candidate mappings for a human to
review. Accepted suggestions must be persisted as explicit ``ProviderRef``
links in a ``CanonicalRegistry`` before any join uses them.

To make misuse hard, ``suggest_mappings`` returns inert suggestion records
(never ProviderRef links), and every record carries ``requires_review=True``.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher


def _normalize(name: str) -> str:
    text = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return " ".join(text.lower().replace("-", " ").split())


def similarity(a: str, b: str) -> float:
    """Return a 0..1 similarity ratio between two names (normalized)."""
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


@dataclass(frozen=True)
class MappingSuggestion:
    """A *suggested* cross-provider mapping awaiting human review.

    This is NOT a binding. It must be reviewed and, if correct, persisted as an
    explicit link in the canonical registry.
    """
    left_provider: str
    left_id: str
    left_name: str
    right_provider: str
    right_id: str
    right_name: str
    score: float
    requires_review: bool = True


def suggest_mappings(
    left: list[tuple[str, str]],
    right: list[tuple[str, str]],
    *,
    left_provider: str,
    right_provider: str,
    threshold: float = 0.85,
) -> list[MappingSuggestion]:
    """Suggest candidate mappings by name similarity (offline review aid).

    Args:
        left: list of (provider_id, name) for the left provider.
        right: list of (provider_id, name) for the right provider.
        threshold: minimum similarity to emit a suggestion.

    Returns:
        Suggestions sorted by descending score. Ties and near-ties are all
        emitted so a reviewer can see ambiguity rather than the code silently
        picking one.
    """
    out: list[MappingSuggestion] = []
    for lid, lname in left:
        for rid, rname in right:
            score = similarity(lname, rname)
            if score >= threshold:
                out.append(MappingSuggestion(
                    left_provider=left_provider, left_id=lid, left_name=lname,
                    right_provider=right_provider, right_id=rid, right_name=rname,
                    score=round(score, 4),
                ))
    out.sort(key=lambda s: s.score, reverse=True)
    return out
