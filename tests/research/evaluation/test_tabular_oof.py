from src.research.evaluation.tabular_oof import TabularConfig, TABULAR_OOF_VERSION


def test_tabular_config_identity_is_deterministic():
    assert TabularConfig().identity_hash == TabularConfig().identity_hash
    assert TABULAR_OOF_VERSION == "qfe-layer3-tabular-oof-v1"
