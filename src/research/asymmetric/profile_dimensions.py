"""Named profile dimensions and the reduced-profile map.

Responsibility:
    Define the five named attacking dimensions (width, central_penetration,
    volume_vs_quality, set_piece_reliance, directness) and five named defensive
    dimensions (block_orientation, aerial_vs_ground, shot_suppression,
    gk_contribution, discipline) together with their source raw fields, and the
    Broad_Corpus reduced-profile map. Encodes audit-grounded constraints such as
    building gk_contribution from saves/high_claims (not goals_prevented) and
    flagging central_penetration as reduced-confidence for the Championship.

Scaffold only — dimensions are implemented in task 3.1.
"""
