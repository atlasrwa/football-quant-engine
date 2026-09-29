from src.research.v31_pilot.telegram import declaration_message

def test_message_is_explicitly_shadow_and_unvalidated():
    event={'fixture':'A vs B','kickoff_utc':'2026-09-29T20:30:00Z','market_family':'btts','side':'YES','line':None,'price_decimal':2.0,
           'market_observed_at_utc':'2026-09-29T16:00:00Z','evidence_sha256':'a'*64,
           'model':{'p_selected':0.66,'version':'X','research_state':'POST_EXPOSURE_DEVELOPMENT_ONLY_NOT_PROMOTED'},
           'market_benchmark':{'no_vig_selected':0.50,'model_minus_no_vig':0.16,'raw_break_even_selected':0.50}}
    text=declaration_message(event)
    assert 'V3.1 RESEARCH SHADOW' in text
    assert 'NOT VALIDATED / NOT ACTIONABLE' in text
    assert 'Does not count toward frozen V3 tests 21–40' in text
