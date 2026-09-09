"""First price-discovery study scaffolding (data preparation, not modelling).

This package turns the append-only prospective capture store into a
deterministic, leakage-safe research dataset of market-movement observations,
and reports descriptive coverage + the preregistered sample gate.

It does NOT fit any model and does NOT modify the champion. The research
question it prepares for is price discovery:

    Does information known at time t predict subsequent market movement?

Modules:
- ``dataset``  : CaptureStore -> de-vigged per-(book,market,selection,line)
  snapshots -> same-key vintage transitions (PriceDiscoveryRow), with line
  changes kept separate. Deterministic serialization.
- ``report``   : small-N descriptive stats + preregistered readiness gate.
"""

from src.research.experiments.price_discovery.dataset import (
    PROSPECTIVE_GATE,
    DevigMethod,
    PriceDiscoveryDataset,
    ReadinessGate,
    Transition,
    build_dataset,
)

__all__ = [
    "PROSPECTIVE_GATE",
    "DevigMethod",
    "PriceDiscoveryDataset",
    "ReadinessGate",
    "Transition",
    "build_dataset",
]
