"""Recommendation logic: DCF upside -> BUY / HOLD / SELL, reconciled with the verdict.

Bands (configurable): base-case upside >= +20% -> BUY; <= -20% -> SELL; else HOLD.
The bear/bull spread qualifies conviction, and any disagreement with the
watchlist verdict is stated explicitly — that tension is exactly what an
IC memo should surface, not smooth over.
"""

from __future__ import annotations

from dataclasses import dataclass

BUY_THRESHOLD = 0.20
SELL_THRESHOLD = -0.20

_VERDICT_TONE = {
    "do_work": "the watchlist engine already ranks this a Do Work name",
    "constructive": "the watchlist engine reads the operating story as Constructive",
    "watch": "the watchlist engine holds this at Watch",
    "avoid": "the watchlist engine flags this Avoid / Pass on operating grounds",
}


@dataclass
class Recommendation:
    stance: str            # BUY | HOLD | SELL | N/A
    headline: str
    conviction: str        # high | moderate | low | n/a
    reconciliation: str


def _conviction(upside: float, bear_upside: float | None, bull_upside: float | None) -> tuple[str, str]:
    if bear_upside is None or bull_upside is None:
        return "n/a", "Scenario range unavailable."
    spread = bull_upside - bear_upside
    if upside >= BUY_THRESHOLD and bear_upside >= -0.05:
        return "high", f"Even the bear case holds near breakeven ({bear_upside:+.0%})."
    if upside <= SELL_THRESHOLD and bull_upside <= 0.05:
        return "high", f"Even the bull case fails to reach upside ({bull_upside:+.0%})."
    if spread >= 0.80:
        return "low", f"Bear-to-bull spread is wide ({bear_upside:+.0%} to {bull_upside:+.0%}); the case hinges on the debated assumptions."
    return "moderate", f"Scenario range {bear_upside:+.0%} to {bull_upside:+.0%}."


def recommend(
    upside: float | None,
    bear_upside: float | None,
    bull_upside: float | None,
    verdict_key: str | None = None,
    formal: bool = True,
    formal_reason: str | None = None,
) -> Recommendation:
    """Return a formal recommendation only after all readiness gates pass."""
    if upside is None:
        return Recommendation(
            stance="N/A",
            headline="Insufficient data for a price-target recommendation.",
            conviction="n/a",
            reconciliation="Populate market cap / price data to enable the equity bridge.",
        )

    if not formal:
        reason = formal_reason or "The case has not completed analyst review."
        conviction, conviction_note = _conviction(upside, bear_upside, bull_upside)
        return Recommendation(
            stance="INDICATIVE",
            headline=(f"Auto-anchored calibration: mechanical extrapolation of TTM data implies "
                      f"{upside:+.0%} - NOT an investment view."),
            conviction="n/a",
            reconciliation=(f"{reason}. Complete the readiness checks before issuing a formal "
                            f"recommendation. {conviction_note}"),
        )

    if upside >= BUY_THRESHOLD:
        stance = "BUY"
    elif upside <= SELL_THRESHOLD:
        stance = "SELL"
    else:
        stance = "HOLD"

    headline = f"{stance}: base-case DCF implies {upside:+.0%} ({abs(upside) * 100:.0f}% {'upside' if upside >= 0 else 'downside'})."
    conviction, conviction_note = _conviction(upside, bear_upside, bull_upside)

    tone = _VERDICT_TONE.get(str(verdict_key), None)
    if tone is None:
        reconciliation = conviction_note
    else:
        aligned = (
            (stance == "BUY" and verdict_key in {"do_work", "constructive"})
            or (stance == "SELL" and verdict_key == "avoid")
            or (stance == "HOLD" and verdict_key in {"watch", "constructive"})
        )
        if aligned:
            reconciliation = f"DCF and watchlist agree: {tone}. {conviction_note}"
        else:
            reconciliation = (
                f"DCF ({stance}) and watchlist verdict disagree — {tone}. "
                f"The gap is the assumption set to debate before acting. {conviction_note}"
            )
    return Recommendation(stance=stance, headline=headline, conviction=conviction, reconciliation=reconciliation)
