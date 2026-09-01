"""Interaction_Model — two-direction fixture modelling.

Responsibility:
    Model each fixture as exactly two Directions (A-attack vs B-defence and
    B-attack vs A-defence), each a separately fitted DirectionalCountModel, never
    collapsed into a single symmetric feature. Builds the linear predictor from
    the attacker's attacking dimensions, the defender's defensive dimensions, and
    named interaction cross-terms, adding the referee card-rate conditioning term
    for the cards target. Produces per-side full predictive distributions for
    corners, cards, goals, and shots on target with named driving features
    surfaced.

Scaffold only — the InteractionModel and referee conditioning are implemented in
task 5.
"""
