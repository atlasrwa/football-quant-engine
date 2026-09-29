from __future__ import annotations
from src.research.prediction_engine.broadcast.delivery import TelegramTransport

def transport():
    t=TelegramTransport(token_env=('V3_TELEGRAM_BOT_TOKEN',),chat_env=('V3_TELEGRAM_CHAT_ID',)); t._announced=True; return t

def _pct(x): return f'{100*float(x):.1f}%'

def declaration_message(event: dict) -> str:
    mb=event['market_benchmark']; model=event['model']; family=event['market_family']
    market_label=(f"{event['side']} BTTS" if family=='btts' else f"{event['side']} {float(event['line']):.1f} GOALS")
    lines=['QFE V3.1 RESEARCH SHADOW — MARKET DISAGREEMENT','NOT VALIDATED / NOT ACTIONABLE','Does not count toward frozen V3 tests 21–40','',str(event['fixture']),f"Kickoff: {event['kickoff_utc']}",'',market_label,
           f"Entry snapshot: {float(event['price_decimal']):.2f}",f"Model: {_pct(model['p_selected'])}",f"Market no-vig: {_pct(mb['no_vig_selected'])}",
           f"Disagreement: {100*float(mb['model_minus_no_vig']):+.1f} pp",f"Raw break-even: {_pct(mb['raw_break_even_selected'])}",'',
           f"Observed: {event['market_observed_at_utc']}",f"Model version: {model['version']}",f"Research state: {model['research_state']}",f"Evidence: {event['evidence_sha256'][:12]}…"]
    return '\n'.join(lines)

def settlement_message(event: dict, declaration: dict) -> str:
    line='' if declaration['market_family']=='btts' else f" {float(declaration['line']):.1f}"
    return '\n'.join(['QFE V3.1 RESEARCH SHADOW — SETTLEMENT',str(declaration['fixture']),f"{declaration['side']}{line} {declaration['market_family'].upper()}",
                      f"Result: {event['result']}",f"Regulation score: {event['home_goals']}-{event['away_goals']}",'NOT VALIDATED / NOT ACTIONABLE'])

def send(text): return transport().send(text)
