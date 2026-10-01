from __future__ import annotations
from src.research.prediction_engine.broadcast.delivery import TelegramTransport

def send(text):
    t=TelegramTransport(token_env=('V3_TELEGRAM_BOT_TOKEN',),chat_env=('V3_TELEGRAM_CHAT_ID',)); t._announced=True; return t.send(text)
def pct(x): return f'{100*float(x):.1f}%'
def declaration(e):
    return '\n'.join(['QFE V3.7 FUTURE-50 — MARKET DISAGREEMENT','PROSPECTIVE SHADOW / NOT ACTIONABLE','',f"Fixture #{e['fixture_number']}/50",e['fixture'],f"Kickoff: {e['kickoff_utc']}",'',f"{e['side']} {e['line']:.1f} {e['family'].upper()}",f"Entry: {e['price_decimal']:.2f}",f"Model: {pct(e['p_model'])}",f"Market no-vig: {pct(e['p_market'])}",f"Disagreement: {100*e['delta']:+.1f} pp",f"Raw break-even: {pct(e['raw_break_even'])}",'',f"Vintage: {e['vintage']}",f"Model: {e['model_version']}",f"Freeze: {e['freeze_hash'][:12]}…"])
def settlement(e,d):
    lines=['QFE V3.7 FUTURE-50 — SETTLEMENT','',f"Fixture #{d['fixture_number']}/50",d['fixture'],f"{d['side']} {d['line']:.1f} {d['family'].upper()}",f"Result: {e['result']}",f"Settled value: {e['value']}"]
    c=e.get('clv') or {}
    if c.get('status')=='OK':
        direction={'TOWARD_MODEL':'toward model','AWAY_FROM_MODEL':'away from model','FLAT':'flat'}[c['direction']]
        lines += ['',f"Entry no-vig: {pct(c['entry_market_p'])}",f"Close no-vig: {pct(c['closing_market_p'])}",f"Market move: {c['market_move_pp']:+.1f} pp ({direction})",f"Model-market gap: {c['entry_model_market_gap_pp']:.1f} pp → {c['closing_model_market_gap_pp']:.1f} pp",f"Gap closed: {c['gap_closed_pp']:+.1f} pp"]
    else:
        lines += ['',f"Closing-line CLV: unavailable ({c.get('reason','NO_VALID_FINAL')})"]
    return '\n'.join(lines)
