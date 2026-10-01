from src.research.prediction_engine.broadcast.delivery import TelegramTransport
def send(text):
    t=TelegramTransport(token_env=('V3_TELEGRAM_BOT_TOKEN',),chat_env=('V3_TELEGRAM_CHAT_ID',)); t._announced=True; return t.send(text)
def _pct(x): return f'{100*float(x):.1f}%'
def paired_message(e):
    lines=['QFE V3.8 PAIRED-50 — V3.7 CONTROL vs V3.8 CHALLENGER','PROSPECTIVE SHADOW / NOT ACTIONABLE','',f"Fixture #{e['fixture_number']}/50",e['fixture'],f"Kickoff: {e['kickoff_utc']}",'',f"{e['family'].upper()} @ line {e['line']:.1f}",f"Market no-vig: {_pct(e['market_p'])}",f"Price side shown: {e['market_side']} @ {e['market_price']:.2f}",'']
    for name in ('control','challenger'):
        d=e[name]; lines += [f"{name.upper()}: {d['side']} {e['line']:.1f}",f"  Model: {_pct(d['p_model'])} | Δ market: {100*d['delta']:+.1f} pp | Qualifies: {'YES' if d['qualifies'] else 'NO'}"]
    lines += ['',f"Vintage: {e['vintage']}",f"Pair freeze: {e['pair_freeze_hash'][:12]}…"]
    return '\n'.join(lines)
