from __future__ import annotations
from src.research.prediction_engine.broadcast.delivery import TelegramTransport

def send(text: str):
    t = TelegramTransport(token_env=("V3_TELEGRAM_BOT_TOKEN",), chat_env=("V3_TELEGRAM_CHAT_ID",))
    t._announced = True
    return t.send(text)

def pct(x: float) -> str:
    return f"{100 * float(x):.1f}%"

def declaration(event: dict) -> str:
    c = event["components"]
    w = event["ensemble_weights"]
    return "\n".join([
        "QFE TEAM CORNERS V1 — MARKET DISAGREEMENT",
        "PROSPECTIVE RESEARCH / NOT VALIDATED",
        "",
        f"Disagreement #{event['disagreement_number']}",
        f"Cohort fixture #{event['fixture_number']}/50",
        event["fixture"],
        f"Kickoff: {event['kickoff_utc']}",
        "",
        f"{event['team_name']} — {event['side']} {event['line']:.1f} TEAM CORNERS",
        f"Entry: {event['price_decimal']:.3f}",
        f"Model: {pct(event['p_model'])}",
        f"Market no-vig: {pct(event['p_market'])}",
        f"Disagreement: {100 * event['delta']:+.1f} pp",
        f"Raw break-even: {pct(event['raw_break_even'])}",
        "",
        f"Expected team corners μ: {event['mu']:.2f}",
        f"Components μ: hierarchical {c['hierarchical_attack_defence_mu']:.2f} | decay {c['decay_profile_mu']:.2f} | pressure {c['ridge_pressure_mu']:.2f}",
        f"Ensemble weights: {100*w['hierarchical_attack_defence']:.0f}/{100*w['decay_profile']:.0f}/{100*w['ridge_pressure']:.0f}",
        f"Vintage: {event['vintage']}",
        f"Model: {event['model_version']}",
        f"Freeze: {event['model_freeze_sha256'][:12]}…",
    ])

def settlement(event: dict, declaration_event: dict) -> str:
    lines = [
        "QFE TEAM CORNERS V1 — SETTLEMENT",
        "",
        f"Disagreement #{declaration_event['disagreement_number']}",
        f"Cohort fixture #{declaration_event['fixture_number']}/50",
        declaration_event["fixture"],
        f"{declaration_event['team_name']} — {declaration_event['side']} {declaration_event['line']:.1f} TEAM CORNERS",
        f"Result: {event['result']}",
        f"Settled team corners: {event['value']}",
    ]
    clv = event.get("clv") or {}
    if clv.get("status") == "OK":
        lines += [
            "",
            f"Entry no-vig: {pct(clv['entry_market_p'])}",
            f"Final-window no-vig: {pct(clv['closing_market_p'])}",
            f"Market move toward selection: {100*clv['movement_toward_selection']:+.1f} pp",
        ]
    else:
        lines += ["", f"Final-window benchmark: unavailable ({clv.get('reason','NO_VALID_FINAL')})"]
    return "\n".join(lines)
