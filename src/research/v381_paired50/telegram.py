from src.research.prediction_engine.broadcast.delivery import TelegramTransport
def send(text):
    t=TelegramTransport(token_env=('V3_TELEGRAM_BOT_TOKEN',),chat_env=('V3_TELEGRAM_CHAT_ID',)); t._announced=True; return t.send(text)
def _pct(x): return f'{100*float(x):.1f}%'
def paired_message(e):
    lines=['QFE V3.8.1 PAIRED-50 — V3.7 CONTROL vs V3.8 CHALLENGER','PROSPECTIVE SHADOW / NOT ACTIONABLE','',f"Paired disagreement #{e['disagreement_number']}",f"Cohort fixture #{e['fixture_number']}/50",e['fixture'],f"Kickoff: {e['kickoff_utc']}",'',f"{e['family'].upper()} @ line {e['line']:.1f}",f"Market no-vig: {_pct(e['market_p'])}",f"Price side shown: {e['market_side']} @ {e['market_price']:.2f}",'']
    for name in ('control','challenger'):
        d=e[name]; lines += [f"{name.upper()}: {d['side']} {e['line']:.1f}",f"  Model: {_pct(d['p_model'])} | Δ market: {100*d['delta']:+.1f} pp | Qualifies: {'YES' if d['qualifies'] else 'NO'}"]
    lines += ['',f"Vintage: {e['vintage']}",f"Pair freeze: {e['pair_freeze_hash'][:12]}…"]
    return '\n'.join(lines)

def paired_settlement(e,d):
    lines=['QFE V3.8.1 PAIRED-50 — SETTLEMENT','',f"Paired disagreement #{d['disagreement_number']}",f"Cohort fixture #{d['fixture_number']}/50",d['fixture'],f"{d['family'].upper()} @ line {d['line']:.1f}",f"Settled value: {e['value']}"]
    for name in ('control','challenger'):
        arm=d[name]; c=(e.get('clv') or {}).get(name,{})
        result=e['results'][name]
        lines += ['',f"{name.upper()}: {arm['side']} — {result}"]
        if c.get('status')=='OK':
            direction={'TOWARD_MODEL':'toward model','AWAY_FROM_MODEL':'away from model','FLAT':'flat'}[c['direction']]
            lines += [f"  Entry no-vig: {_pct(c['entry_market_p'])}",f"  Close no-vig: {_pct(c['closing_market_p'])}",f"  Market move: {c['market_move_pp']:+.1f} pp ({direction})",f"  Gap: {c['entry_model_market_gap_pp']:.1f} pp → {c['closing_model_market_gap_pp']:.1f} pp",f"  Gap closed: {c['gap_closed_pp']:+.1f} pp"]
        else:
            lines += [f"  Closing-line CLV: unavailable ({c.get('reason','NO_VALID_FINAL')})"]
    return '\n'.join(lines)
