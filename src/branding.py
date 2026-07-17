"""Single source of truth for the institutional design system.

The palette, type scale, and signal colors defined here are shared by the
Streamlit dashboard, the Plotly/Matplotlib charts, and the exported board
pack so that every surface looks like one consistent finance product.

Aesthetic target: investment watchlist / special situations review.
The look is editorial and institutional: charcoal chrome, warm off-white
surfaces, sage/copper data colors, restrained gold rules, and oxblood risk.
"""

from __future__ import annotations

# --- Core palette -----------------------------------------------------------
PALETTE = {
    # Structure. The legacy "navy" names are kept so existing chart and layout
    # code can inherit the new direction without mechanical refactors.
    "navy": "#2F4F4F",        # dark slate header/sidebar
    "navy_2": "#243D3D",      # deeper dark slate chrome
    "navy_3": "#778899",      # slate-gray accent
    "ink": "#243333",         # primary text
    "slate": "#2F4F4F",       # secondary text
    "muted": "#687A82",       # tertiary / captions
    "muted_2": "#9AA6AB",     # faint labels
    "line": "#D3D3D3",        # card / table borders
    "line_soft": "#E8EEEE",   # hairline separators
    "bg": "#F4F7F7",          # neutral app canvas
    "panel": "#FFFFFF",       # cards
    "panel_alt": "#F0F4F4",   # zebra / table head
    # Data / accents
    "blue": "#20B2AA",        # primary teal
    "blue_2": "#2F4F4F",      # secondary dark slate
    "gold": "#778899",        # fourth-priority slate gray
    "teal": "#20B2AA",
    "sage": "#20B2AA",
    "sage_soft": "#E3F6F5",
    "copper": "#778899",
    "oxblood": "#8f2f3b",
    "cream": "#F4F7F7",
    "charcoal": "#2F4F4F",
    # Chart roles. Peers recede, the selected company leads, and operating
    # series remain distinct without borrowing traffic-light colors.
    "anchor": "#20B2AA",
    "peer": "#D3D3D3",
    "series_revenue": "#20B2AA",
    "series_ebitda": "#2F4F4F",
    "series_cash": "#778899",
    "series_margin": "#778899",
    "series_secondary": "#D3D3D3",
    "series_debt": "#2F4F4F",
    # Signals (muted, institutional)
    "green": "#4f7658",
    "green_soft": "#e8efe5",
    "amber": "#a8843f",
    "amber_soft": "#f4ead3",
    "red": "#8f2f3b",
    "red_soft": "#f2e1df",
}

# Traffic-light signal -> hex. Note the modeling layer emits "yellow".
SIGNAL_COLORS = {
    "green": PALETTE["green"],
    "yellow": PALETTE["amber"],
    "amber": PALETTE["amber"],
    "red": PALETTE["red"],
    "n/a": PALETTE["muted_2"],
}

SIGNAL_SOFT = {
    "green": PALETTE["green_soft"],
    "yellow": PALETTE["amber_soft"],
    "amber": PALETTE["amber_soft"],
    "red": PALETTE["red_soft"],
    "n/a": PALETTE["panel_alt"],
}

# Verdict tone -> hex (used by the headline conclusion banner).
VERDICT_COLORS = {
    # Watchlist vocabulary (current).
    "do_work": PALETTE["copper"],
    "constructive": PALETTE["green"],
    "watch": PALETTE["navy_3"],
    "avoid": PALETTE["red"],
    # Legacy monitoring vocabulary, kept for older artifacts.
    "outperforming": PALETTE["green"],
    "monitor": PALETTE["navy_3"],
    "under_review": PALETTE["amber"],
    "diligence_concern": PALETTE["red"],
}

# --- Typography -------------------------------------------------------------
FONT_SANS = '"Segoe UI", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif'
FONT_SERIF = 'Georgia, "Times New Roman", "Iowan Old Style", serif'
FONT_MONO = '"SFMono-Regular", "Cascadia Mono", Consolas, "Liberation Mono", monospace'

# Matplotlib-safe family list - Arial ships on Windows; DejaVu always present.
MPL_FONT_STACK = ["Arial", "DejaVu Sans"]


def signal_hex(signal: str) -> str:
    """Resolve a traffic-light signal string to a hex color."""
    return SIGNAL_COLORS.get(str(signal).lower(), PALETTE["muted_2"])
