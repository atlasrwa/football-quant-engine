"""V3-only Telegram rendering and delivery."""
from __future__ import annotations

from src.research.prediction_engine.broadcast.delivery import TelegramTransport

def transport() -> TelegramTransport:
    t = TelegramTransport(
        token_env=("V3_TELEGRAM_BOT_TOKEN",),
        chat_env=("V3_TELEGRAM_CHAT_ID",),
    )
    # The shared transport warns whenever the credential name does not begin
    # FORECAST_BROADCAST_. V3 is deliberately dedicated under V3_* names, so
    # suppress that generic fallback announcement without changing routing.
    t._announced = True
    return t

def _pct(x: float) -> str:
    return f"{100*float(x):.1f}%"

def declaration_message(event: dict) -> str:
    mb = event["market_benchmark"]
    model = event["model"]
    lines = [
        "QFE V3 RESEARCH PILOT — MARKET DISAGREEMENT",
        "NOT VALIDATED / NOT ACTIONABLE",
        "",
        f"Test #{event['test_number']}/40",
        str(event["fixture"]),
        f"Kickoff: {event['kickoff_utc']}",
        "",
        f"{event['side']} {float(event['line']):.1f} {event['market_family'].upper()}",
        f"Entry snapshot: {float(event['price_decimal']):.2f}",
        f"Model: {_pct(model['p_selected'])}",
        f"Market no-vig: {_pct(mb['no_vig_selected'])}",
        f"Disagreement: {100*float(mb['model_minus_no_vig']):+.1f} pp",
        f"Raw break-even: {_pct(mb['raw_break_even_selected'])}",
        "",
        f"Observed: {event['market_observed_at_utc']}",
        f"Model version: {model['version']}",
        f"Evidence: {event['immutable_evidence']['sha256'][:12]}…",
    ]
    opening = mb.get("opening")
    if isinstance(opening, dict) and opening.get("p_novig_selected") is not None:
        lines.extend([
            "",
            f"Opening no-vig reference: {_pct(opening['p_novig_selected'])}",
        ])
    return "\n".join(lines)

def settlement_message(event: dict, declaration: dict) -> str:
    cb = event.get("closing_benchmark") or {}
    lines = [
        "QFE V3 RESEARCH PILOT — SETTLEMENT",
        "",
        f"Test #{declaration.get('test_number')}/40",
        str(declaration.get("fixture")),
        f"{declaration.get('side')} {float(declaration.get('line')):.1f} "
        f"{str(declaration.get('market_family')).upper()}",
        f"Result: {event.get('result')}",
        f"Settled value: {event.get('settled_value')}",
    ]
    if cb.get("closing_novig_selected") is not None:
        lines.extend([
            f"Entry no-vig: {_pct(declaration['market_benchmark']['no_vig_selected'])}",
            f"Close no-vig: {_pct(cb['closing_novig_selected'])}",
            f"Market move toward selection: {100*float(cb.get('movement_toward_selection',0)):+.1f} pp",
        ])
    return "\n".join(lines)

def send(text: str) -> tuple[bool, str]:
    return transport().send(text)
