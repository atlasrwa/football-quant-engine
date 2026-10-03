from src.research.evaluation.similar_oof import SimilarContextConfig,GOALS_FEATURES,CORNERS_FEATURES

def test_similarity_contract_is_fixed_and_target_specific():
    assert SimilarContextConfig().k_neighbors==75
    assert GOALS_FEATURES != CORNERS_FEATURES
    assert all("market" not in x for x in GOALS_FEATURES+CORNERS_FEATURES)
