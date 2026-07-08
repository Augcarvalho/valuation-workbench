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
    "navy": "#1f2421",        # charcoal header/sidebar
    "navy_2": "#29322c",      # dark moss charcoal
    "navy_3": "#6f7f63",      # sage accent
    "ink": "#20221d",         # primary text
    "slate": "#4a4f45",       # secondary text
    "muted": "#74786e",       # tertiary / captions
    "muted_2": "#9c9a90",     # faint labels
    "line": "#d8d0c1",        # card / table borders
    "line_soft": "#e9e2d6",   # hairline separators
    "bg": "#f3f0e8",          # warm app canvas
    "panel": "#fffdf7",       # cards
    "panel_alt": "#f6f1e8",   # zebra / table head
    # Data / accents
    "blue": "#687a61",        # sage primary series
    "blue_2": "#9b6a4c",      # copper secondary series
    "gold": "#a8843f",        # editorial accent rule
    "teal": "#5e746a",        # muted institutional green-gray
    "sage": "#687a61",
    "sage_soft": "#edf1e8",
    "copper": "#9b6a4c",
    "oxblood": "#8f2f3b",
    "cream": "#f8f4ea",
    "charcoal": "#1f2421",
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
