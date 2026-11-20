"""Liquid-glass visual theme for the Amazon UK Listing Audit Bot.

Styling only: this module does not change application data, audit logic,
Playwright behaviour, or persistence.

Design: Apple-inspired glassmorphism with a "Navy & Teal" palette
(Deep Navy, Teal Green, Aqua Blue, Sunset Orange, Crimson Red), warmed
with Cream, Sage, Dusty Rose, Mustard and Deep Plum.
- Frosted glass panels: translucent fill, background blur + saturation,
  a brighter edge highlight and soft outer shadows.
- An aurora background (slow drifting colour light) behind everything.
- Motion: fade-and-rise entrances, shimmer title text, a spinning glow
  border on card hover, liquid sheen on buttons, scroll reveal.
  Every animation is switched off for people who ask their computer for
  reduced motion; glass turns solid for reduced transparency.

Only the colour tokens (PALETTES) differ between modes.

Public helpers (names unchanged; other files import them):
    apply_theme(mode)      inject the stylesheet; mode is "light" or "dark"
    render_header(...)     animated glass hero at the top of a page
    badge(text, kind)      small glass status pill (HTML string)
    render_feature_grid()  grid of glass cards (used on the Dashboard)
"""

from html import escape

import streamlit as st


# =========================================================
# 1. COLOUR TOKENS (the only part that differs per mode)
# =========================================================

PALETTES = {
    "light": {
        # Page (Cream) and aurora light
        "--bg": "#f6f0e4",
        "--glow-1": "rgba(16,187,195,0.28)",     # Aqua Blue
        "--glow-2": "rgba(254,162,79,0.24)",     # Sunset Orange
        "--glow-3": "rgba(143,166,143,0.26)",    # Sage Green
        "--glow-4": "rgba(196,124,138,0.20)",    # Dusty Rose
        "--grid-line": "rgba(5,26,45,0.04)",

        # Glass
        "--glass": "linear-gradient(135deg, rgba(255,255,255,0.74), rgba(255,255,255,0.44))",
        "--glass-strong": "linear-gradient(135deg, rgba(255,255,255,0.88), rgba(255,255,255,0.64))",
        "--glass-solid": "#fbf8f1",
        "--glass-input": "rgba(255,255,255,0.78)",
        "--glass-line": "rgba(5,26,45,0.10)",
        "--glass-highlight": "rgba(255,255,255,0.95)",
        "--sheen": "rgba(255,255,255,0.70)",
        "--sidebar": "linear-gradient(180deg, rgba(255,252,245,0.74), rgba(255,250,240,0.50))",

        # Text (Deep Navy)
        "--text": "#051a2d",
        "--text-muted": "#4d6073",

        # Brand colours as readable text / lines on this background
        "--accent-text": "#05666b",
        "--brand-soft": "rgba(6,129,135,0.12)",
        "--brand-line": "rgba(6,129,135,0.40)",
        "--brand-glow": "rgba(6,129,135,0.22)",

        # Shadows (navy-tinted, never pure black on cream)
        "--shadow-sm": "0 2px 10px rgba(5,26,45,0.06), 0 1px 2px rgba(5,26,45,0.04)",
        "--shadow-md": "0 12px 36px rgba(5,26,45,0.10), 0 2px 8px rgba(5,26,45,0.05)",
        "--shadow-hover": "0 22px 50px rgba(6,129,135,0.20), 0 6px 16px rgba(5,26,45,0.08)",

        # Tables are drawn by Streamlit on a canvas; no change in light mode.
        "--grid-filter": "none",
        "--scroll-thumb": "rgba(6,129,135,0.30)",

        # Message boxes
        "--alert-info": "rgba(89,113,138,0.13)",
        "--alert-success": "rgba(6,129,135,0.13)",
        "--alert-warning": "rgba(254,162,79,0.20)",
        "--alert-error": "rgba(166,14,53,0.11)",

        "--hero-base": "rgba(255,252,245,0.66)",

        # Badge text (darker on light glass for contrast)
        "--badge-ok": "#05666b",
        "--badge-warn": "#9a5410",
        "--badge-bad": "#a60e35",
        "--badge-info": "#3d5872",
    },
    "dark": {
        # Page (Deep Navy) and aurora light
        "--bg": "#03111f",
        "--glow-1": "rgba(6,129,135,0.46)",      # Teal Green
        "--glow-2": "rgba(91,58,98,0.50)",       # Deep Plum
        "--glow-3": "rgba(16,187,195,0.22)",     # Aqua Blue
        "--glow-4": "rgba(254,162,79,0.12)",     # Sunset Orange
        "--grid-line": "rgba(242,233,216,0.035)",

        "--glass": "linear-gradient(135deg, rgba(255,255,255,0.09), rgba(255,255,255,0.03))",
        "--glass-strong": "linear-gradient(135deg, rgba(255,255,255,0.13), rgba(255,255,255,0.05))",
        "--glass-solid": "#0a2236",
        # Fields are deliberately dark and almost solid, so white text is
        # always readable even if Streamlit paints something behind them.
        "--glass-input": "rgba(2,12,22,0.72)",
        "--glass-line": "rgba(242,233,216,0.12)",
        "--glass-highlight": "rgba(255,255,255,0.14)",
        "--sheen": "rgba(255,255,255,0.16)",
        "--sidebar": "linear-gradient(180deg, rgba(8,32,52,0.78), rgba(3,17,31,0.66))",

        # Text (Cream on navy)
        "--text": "#f2e9d8",
        "--text-muted": "#9fb2c4",

        "--accent-text": "#5fe0e6",
        "--brand-soft": "rgba(16,187,195,0.16)",
        "--brand-line": "rgba(16,187,195,0.45)",
        "--brand-glow": "rgba(16,187,195,0.30)",

        "--shadow-sm": "0 2px 12px rgba(0,0,0,0.35)",
        "--shadow-md": "0 14px 40px rgba(0,0,0,0.45)",
        "--shadow-hover": "0 24px 56px rgba(16,187,195,0.26), 0 8px 20px rgba(0,0,0,0.40)",

        # Streamlit now switches its own theme to dark (see
        # sync_streamlit_theme), so tables are already dark: no filter.
        "--grid-filter": "none",
        "--scroll-thumb": "rgba(95,224,230,0.32)",

        "--alert-info": "rgba(89,113,138,0.26)",
        "--alert-success": "rgba(6,129,135,0.26)",
        "--alert-warning": "rgba(254,162,79,0.18)",
        "--alert-error": "rgba(166,14,53,0.26)",

        "--hero-base": "rgba(4,20,36,0.82)",

        # Badge text (brighter on dark glass for contrast)
        "--badge-ok": "#5fe0d0",
        "--badge-warn": "#ffc27d",
        "--badge-bad": "#ff7d9c",
        "--badge-info": "#a9c1d9",
    },
}


# Streamlit's OWN widget colours for each mode. Streamlit paints text
# boxes and drop-downs with these, so they must change with the toggle
# (this is what kept the boxes white in dark mode).
STREAMLIT_COLOURS = {
    "light": {
        "base": "light",
        "primaryColor": "#068187",
        "backgroundColor": "#f6f0e4",
        "secondaryBackgroundColor": "#fbf8f1",
        "textColor": "#051a2d",
    },
    "dark": {
        "base": "dark",
        "primaryColor": "#10bbc3",
        "backgroundColor": "#03111f",
        "secondaryBackgroundColor": "#0a2236",
        "textColor": "#f2e9d8",
    },
}


def sync_streamlit_theme(mode):
    """
    Switch Streamlit's own colours to match the mode.
    Returns True when something changed (a rerun is then needed so the
    browser receives the new colours). Returns False if nothing changed
    or if this Streamlit version does not allow it (the CSS still works).

    Note: this setting is shared by everyone using this running app,
    which is fine for a bot used on one laptop.
    """

    changed = False

    try:
        from streamlit import config as streamlit_config

        for key, value in STREAMLIT_COLOURS[mode].items():

            name = "theme." + key

            if streamlit_config.get_option(name) != value:
                streamlit_config.set_option(name, value)
                changed = True

    except Exception:
        return False

    return changed


def _palette_css(mode):
    """Build the :root block of CSS variables for one mode."""

    palette = PALETTES.get(mode, PALETTES["light"])

    lines = "\n".join(f"    {name}: {value};" for name, value in palette.items())

    return f":root {{\n{lines}\n    color-scheme: {mode if mode in PALETTES else 'light'};\n}}"


# =========================================================
# 2. SHARED STYLESHEET (uses only the tokens above)
# =========================================================

THEME_CSS = r"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* Lets the glow border angle animate smoothly. */
@property --spin {
    syntax: "<angle>";
    initial-value: 0deg;
    inherits: false;
}

:root {
    /* Palette */
    --navy: #051a2d;
    --teal: #068187;
    --aqua: #10bbc3;
    --sunset: #fea24f;
    --crimson: #a60e35;
    --slate: #59718a;
    --plum: #5b3a62;
    --cream: #f2e9d8;

    /* Brand */
    --brand: var(--teal);
    --brand-2: var(--aqua);
    --brand-3: var(--sunset);
    --brand-ring: rgba(16, 187, 195, 0.40);

    /* Status */
    --ok: #10bbc3;
    --warn: #fea24f;
    --bad: #e0335f;
    --info: #7f9bb6;

    /* Glass recipe (Apple-style: blur + saturation) */
    --blur: blur(22px) saturate(170%);
    --blur-soft: blur(14px) saturate(150%);

    /* Shape */
    --r-sm: 12px;
    --r-md: 18px;
    --r-lg: 26px;
    --r-pill: 999px;

    /* Motion */
    --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
    --ease-spring: cubic-bezier(0.34, 1.56, 0.64, 1);
    --fast: 180ms;
    --mid: 320ms;
    --slow: 620ms;

    --font: -apple-system, BlinkMacSystemFont, "SF Pro Display", "SF Pro Text",
            "Inter", "Segoe UI", system-ui, sans-serif;
}

/* =========================================================
   KEYFRAMES
   ========================================================= */

@keyframes riseIn     { from { opacity: 0; transform: translateY(14px) scale(0.985); } to { opacity: 1; transform: none; } }
@keyframes fadeIn     { from { opacity: 0; } to { opacity: 1; } }
@keyframes aurora     { 0%   { transform: translate3d(0, 0, 0) rotate(0deg) scale(1); }
                        33%  { transform: translate3d(3%, -2%, 0) rotate(6deg) scale(1.06); }
                        66%  { transform: translate3d(-2%, 3%, 0) rotate(-4deg) scale(0.97); }
                        100% { transform: translate3d(0, 0, 0) rotate(0deg) scale(1); } }
@keyframes drift      { 0% { background-position: 0% 50%; } 50% { background-position: 100% 50%; } 100% { background-position: 0% 50%; } }
@keyframes textShine  { from { background-position: 120% 0; } to { background-position: -120% 0; } }
@keyframes sheen      { from { transform: translateX(-160%) skewX(-20deg); } to { transform: translateX(260%) skewX(-20deg); } }
@keyframes floatOrb   { 0%, 100% { transform: translate(0, 0); } 50% { transform: translate(-10px, 8px); } }
@keyframes spin       { to { --spin: 360deg; } }
@keyframes growX      { from { transform: scaleX(0); } to { transform: scaleX(1); } }
@keyframes ringPulse  { 0% { box-shadow: 0 0 0 0 rgba(224,51,95,0.45); } 70% { box-shadow: 0 0 0 8px rgba(224,51,95,0); } 100% { box-shadow: 0 0 0 0 rgba(224,51,95,0); } }
@keyframes scrollReveal { from { opacity: 0; transform: translateY(18px); } to { opacity: 1; transform: none; } }

/* =========================================================
   PAGE, AURORA BACKGROUND AND TYPE
   ========================================================= */

html, body, .stApp, .stApp button, .stApp input, .stApp textarea {
    font-family: var(--font) !important;
    -webkit-font-smoothing: antialiased;
}

.stApp {
    background: var(--bg) !important;
    color: var(--text) !important;
    /* Keeps the glow layers (z-index -1) behind the content without
       changing Streamlit's own layout. */
    isolation: isolate;
}

/* Slowly drifting coloured light behind all glass. Only "transform" is
   animated, which the graphics card handles cheaply. */
.stApp::before {
    content: "";
    position: fixed;
    inset: -25%;
    z-index: -1;
    pointer-events: none;
    background:
        radial-gradient(36% 32% at 18% 22%, var(--glow-1), transparent 70%),
        radial-gradient(32% 30% at 82% 18%, var(--glow-2), transparent 70%),
        radial-gradient(34% 34% at 72% 82%, var(--glow-3), transparent 70%),
        radial-gradient(28% 26% at 26% 78%, var(--glow-4), transparent 70%);
    animation: aurora 38s ease-in-out infinite;
}

/* A very faint grid, for depth. */
.stApp::after {
    content: "";
    position: fixed;
    inset: 0;
    z-index: -1;
    pointer-events: none;
    background-image:
        linear-gradient(var(--grid-line) 1px, transparent 1px),
        linear-gradient(90deg, var(--grid-line) 1px, transparent 1px);
    background-size: 44px 44px;
    mask-image: radial-gradient(ellipse at 50% 30%, #000 30%, transparent 80%);
    -webkit-mask-image: radial-gradient(ellipse at 50% 30%, #000 30%, transparent 80%);
}

[data-testid="stAppViewContainer"],
[data-testid="stMain"],
[data-testid="stHeader"],
[data-testid="stBottom"] > div {
    background: transparent !important;
}

[data-testid="stDecoration"] {
    background: linear-gradient(90deg, var(--crimson), var(--sunset), var(--aqua), var(--teal)) !important;
    height: 3px !important;
}

.block-container {
    max-width: 1440px;
    padding-top: 2.2rem;
    padding-bottom: 4rem;
    animation: riseIn var(--slow) var(--ease-out) both;
}

.stApp p, .stApp li, .stApp span, .stApp label,
[data-testid="stMarkdownContainer"], [data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p, [data-testid="stText"] {
    color: var(--text);
}

[data-testid="stWidgetLabel"] p {
    font-weight: 600 !important;
    font-size: 0.86rem !important;
    letter-spacing: -0.005em;
}

[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p,
.stApp small { color: var(--text-muted) !important; }

h1, h2, h3, h4 {
    font-family: var(--font) !important;
    letter-spacing: -0.025em !important;
    color: var(--text) !important;
}

h1 {
    font-weight: 800 !important;
    background: linear-gradient(110deg, var(--teal), var(--aqua), var(--sunset));
    background-size: 220% 220%;
    animation: drift 10s ease infinite;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
}

h2 { font-weight: 750 !important; }
h3, h4 { font-weight: 700 !important; }

/* Section headings get a glowing accent line that grows on hover. */
[data-testid="stHeading"] h3::after, .stApp h2::after {
    content: "";
    display: block;
    width: 34px;
    height: 3px;
    margin-top: 7px;
    border-radius: var(--r-pill);
    background: linear-gradient(90deg, var(--teal), var(--aqua), var(--sunset));
    box-shadow: 0 0 12px var(--brand-glow);
    transition: width var(--mid) var(--ease-out);
}

[data-testid="stHeading"]:hover h3::after, .stApp h2:hover::after { width: 84px; }

hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, var(--glass-line), transparent) !important;
}

a { color: var(--accent-text) !important; text-decoration: none; }
a:hover { text-decoration: underline; }

::selection { background: var(--brand-soft); }

/* =========================================================
   SIDEBAR (one large glass pane)
   ========================================================= */

[data-testid="stSidebar"] {
    background: var(--sidebar) !important;
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    border-right: 1px solid var(--glass-line) !important;
    box-shadow: inset -1px 0 0 var(--glass-highlight), 10px 0 40px rgba(0, 0, 0, 0.06);
}

[data-testid="stSidebar"] > div { background: transparent !important; }

/* The sidebar scrolls whenever its content is taller than the screen. */
[data-testid="stSidebarContent"] {
    height: 100% !important;
    max-height: 100vh !important;
    overflow-y: auto !important;
    overscroll-behavior: contain;
}

/* Tighter spacing so the whole sidebar fits on most screens. */
[data-testid="stSidebarUserContent"] { padding-bottom: 2rem !important; }
[data-testid="stSidebar"] hr { margin: 0.6rem 0 !important; }
[data-testid="stSidebar"] h1 { font-size: 1.45rem !important; padding-bottom: 0 !important; }

[data-testid="stSidebar"] [data-testid="stRadio"] > label p {
    font-size: 0.70rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--text-muted) !important;
}

/* Menu items: rounded pills that slide and glow. */
[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"] {
    width: 100%;
    padding: 0.42rem 0.85rem;
    margin: 0.06rem 0;
    border: 1px solid transparent;
    border-radius: var(--r-pill);
    transition: background var(--fast) ease, border-color var(--fast) ease,
                transform var(--mid) var(--ease-spring), box-shadow var(--fast) ease;
}

[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:hover {
    background: var(--glass);
    border-color: var(--glass-line);
    transform: translateX(4px);
}

[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) {
    background: linear-gradient(110deg, rgba(6,129,135,0.30), rgba(16,187,195,0.12));
    border-color: var(--brand-line);
    box-shadow: inset 0 1px 0 var(--glass-highlight), 0 8px 22px var(--brand-glow);
}

[data-testid="stSidebar"] [data-testid="stRadio"] label[data-baseweb="radio"]:has(input:checked) p {
    font-weight: 700 !important;
    color: var(--accent-text) !important;
}

/* =========================================================
   GLASS SURFACES (shared recipe)
   ========================================================= */

[data-testid="stMetric"],
[data-testid="stForm"],
[data-testid="stExpander"] details,
[data-testid="stVerticalBlockBorderWrapper"],
[data-testid="stFileUploaderDropzone"],
.feature-card {
    background: var(--glass) !important;
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    border: 1px solid var(--glass-line) !important;
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-sm);
}

/* ---------- Metric cards ---------- */

[data-testid="stMetric"] {
    position: relative;
    overflow: hidden;
    padding: 1.1rem 1.25rem;
    border-radius: var(--r-md);
    animation: riseIn 560ms var(--ease-out) both;
    transition: transform var(--mid) var(--ease-spring), box-shadow var(--mid) ease,
                border-color var(--mid) ease;
}

[data-testid="stColumn"]:nth-child(2) [data-testid="stMetric"] { animation-delay: 70ms; }
[data-testid="stColumn"]:nth-child(3) [data-testid="stMetric"] { animation-delay: 140ms; }
[data-testid="stColumn"]:nth-child(4) [data-testid="stMetric"] { animation-delay: 210ms; }

/* Palette stripe along the top of each metric card. */
[data-testid="stMetric"]::before {
    content: "";
    position: absolute;
    inset: 0 0 auto 0;
    height: 3px;
    background: linear-gradient(90deg, var(--crimson), var(--sunset), var(--aqua), var(--teal));
    background-size: 200% 100%;
    animation: drift 8s ease infinite;
    opacity: 0.9;
}

[data-testid="stMetric"]::after,
.feature-card::after,
.hero-shine {
    content: "";
    position: absolute;
    top: -40%;
    left: 0;
    width: 38%;
    height: 180%;
    background: linear-gradient(90deg, transparent, var(--sheen), transparent);
    transform: translateX(-160%) skewX(-20deg);
    pointer-events: none;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-6px);
    border-color: var(--brand-line) !important;
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-hover);
}

[data-testid="stMetric"]:hover::after { animation: sheen 1s var(--ease-out); }

[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] p {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: var(--text-muted) !important;
}

[data-testid="stMetricValue"], [data-testid="stMetricValue"] div {
    font-weight: 750 !important;
    letter-spacing: -0.035em;
    color: var(--text) !important;
    /* Size to the card and wrap, instead of cutting off with "...". */
    font-size: clamp(1.25rem, 1.8vw, 1.9rem) !important;
    line-height: 1.15 !important;
    white-space: normal !important;
    overflow: visible !important;
    text-overflow: clip !important;
    overflow-wrap: anywhere;
}

/* ---------- Forms, bordered containers ---------- */

[data-testid="stForm"] {
    padding: 1.4rem;
    border-radius: var(--r-lg);
    animation: riseIn 520ms var(--ease-out) both;
}

[data-testid="stVerticalBlockBorderWrapper"] {
    border-radius: var(--r-md) !important;
}

/* ---------- Expanders ---------- */

[data-testid="stExpander"] details {
    border-radius: var(--r-md) !important;
    overflow: hidden;
    transition: border-color var(--fast) ease, box-shadow var(--mid) ease;
}

[data-testid="stExpander"] details:hover {
    border-color: var(--brand-line) !important;
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-md);
}

[data-testid="stExpander"] summary {
    color: var(--text) !important;
    font-weight: 600;
    background: transparent !important;
    transition: color var(--fast) ease;
}

[data-testid="stExpander"] summary:hover { color: var(--accent-text) !important; }

/* =========================================================
   BUTTONS (glass pills; primary is a glowing teal gradient)
   ========================================================= */

.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] > button,
[data-testid="stLinkButton"] > a,
[data-testid="stFileUploaderDropzone"] button {
    position: relative;
    overflow: hidden;
    min-height: 2.6rem;
    padding: 0.45rem 1.2rem !important;
    border-radius: var(--r-pill) !important;
    border: 1px solid var(--glass-line) !important;
    background: var(--glass-strong) !important;
    backdrop-filter: var(--blur-soft);
    -webkit-backdrop-filter: var(--blur-soft);
    color: var(--text) !important;
    font-weight: 650 !important;
    letter-spacing: -0.005em;
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-sm);
    transition: transform var(--mid) var(--ease-spring), box-shadow var(--mid) ease,
                border-color var(--fast) ease, color var(--fast) ease !important;
}

.stButton > button p, .stDownloadButton > button p,
[data-testid="stFormSubmitButton"] > button p { color: inherit !important; }

.stButton > button::after,
.stDownloadButton > button::after,
[data-testid="stFormSubmitButton"] > button::after {
    content: "";
    position: absolute;
    top: -40%;
    left: 0;
    width: 30%;
    height: 180%;
    background: linear-gradient(90deg, transparent, var(--sheen), transparent);
    transform: translateX(-160%) skewX(-20deg);
    pointer-events: none;
}

.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] > button:hover,
[data-testid="stLinkButton"] > a:hover,
[data-testid="stFileUploaderDropzone"] button:hover {
    transform: translateY(-2px);
    border-color: var(--brand-line) !important;
    color: var(--accent-text) !important;
    box-shadow: inset 0 1px 0 var(--glass-highlight), 0 12px 28px var(--brand-glow);
}

.stButton > button:hover::after,
.stDownloadButton > button:hover::after,
[data-testid="stFormSubmitButton"] > button:hover::after { animation: sheen 900ms var(--ease-out); }

.stButton > button:active,
.stDownloadButton > button:active,
[data-testid="stFormSubmitButton"] > button:active {
    transform: translateY(0) scale(0.97);
    transition-duration: 90ms !important;
}

.stButton > button[kind="primary"],
.stDownloadButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] > button[kind="primary"] {
    color: #ffffff !important;
    border: 1px solid rgba(255, 255, 255, 0.24) !important;
    background: linear-gradient(115deg, #05666b, var(--teal) 30%, var(--aqua) 70%, #05666b) !important;
    background-size: 220% 220% !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.35), 0 10px 26px rgba(6, 129, 135, 0.40);
}

.stButton > button[kind="primary"]:hover,
.stDownloadButton > button[kind="primary"]:hover,
[data-testid="stFormSubmitButton"] > button[kind="primary"]:hover {
    color: #ffffff !important;
    background-position: 100% 50% !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.40), 0 16px 36px rgba(16, 187, 195, 0.50);
}

.stButton > button:disabled,
[data-testid="stFormSubmitButton"] > button:disabled {
    opacity: 0.45;
    transform: none !important;
    box-shadow: none !important;
    cursor: not-allowed;
}

/* =========================================================
   TEXT BOXES, DROP-DOWNS, TEXT AREAS
   Streamlit paints the INNER layers of each field with the white
   "secondaryBackgroundColor" from config.toml. That is what made the
   boxes white in dark mode. Fix: make every inner layer see-through,
   then paint only the outer frame with the theme colour.
   ========================================================= */

/* 1. Every layer inside a field: see-through. */
.stApp [data-baseweb="input"] *,
.stApp [data-baseweb="base-input"],
.stApp [data-baseweb="textarea"] *,
.stApp [data-baseweb="select"] > div *,
.stApp [data-testid="stTextInputRootElement"] *,
.stApp [data-testid="stNumberInputContainer"] * {
    background-color: transparent !important;
}

/* 2. The outer frame: theme glass (dark in dark mode). */
.stApp [data-baseweb="input"],
.stApp [data-baseweb="textarea"],
.stApp [data-baseweb="select"] > div,
.stApp [data-testid="stNumberInputContainer"] {
    background: var(--glass-input) !important;
    border: 1px solid var(--glass-line) !important;
    border-radius: var(--r-sm) !important;
    box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.06);
    transition: border-color var(--fast) ease, box-shadow var(--fast) ease !important;
}

/* Safety net: paint the typing areas themselves, whatever wraps them. */
.stApp [data-testid="stTextArea"] textarea,
.stApp [data-testid="stTextInput"] input,
.stApp [data-testid="stNumberInput"] input {
    background-color: var(--glass-input) !important;
}

/* A number box's own text field sits inside the frame: no second frame. */
.stApp [data-testid="stNumberInputContainer"] [data-baseweb="input"] {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
}

.stApp [data-baseweb="input"]:hover, .stApp [data-baseweb="textarea"]:hover,
.stApp [data-baseweb="select"] > div:hover {
    border-color: var(--brand-line) !important;
}

.stApp [data-baseweb="input"]:focus-within, .stApp [data-baseweb="textarea"]:focus-within,
.stApp [data-baseweb="select"] > div:focus-within {
    border-color: var(--aqua) !important;
    box-shadow: 0 0 0 4px var(--brand-soft) !important;
}

/* 3. Text colour inside fields. */
.stApp input, .stApp textarea, .stApp [data-baseweb="select"] div {
    color: var(--text) !important;
    -webkit-text-fill-color: var(--text) !important;
    caret-color: var(--aqua);
}

/* Example text in an empty box: clearly faint and italic, so an empty
   box never looks filled in. */
.stApp input::placeholder, .stApp textarea::placeholder {
    color: var(--text-muted) !important;
    -webkit-text-fill-color: var(--text-muted) !important;
    opacity: 0.55 !important;
    font-style: italic;
}

/* Chrome autofill paints fields pale yellow/white: cover it. */
.stApp input:-webkit-autofill,
.stApp input:-webkit-autofill:hover,
.stApp input:-webkit-autofill:focus {
    -webkit-box-shadow: 0 0 0 1000px var(--glass-solid) inset !important;
    -webkit-text-fill-color: var(--text) !important;
    transition: background-color 9999s ease 0s;
}

.stApp [data-baseweb="select"] svg,
.stApp [data-baseweb="input"] svg { fill: var(--text-muted) !important; color: var(--text-muted) !important; }

/* Number box +/- buttons */
.stApp [data-testid="stNumberInputStepDown"],
.stApp [data-testid="stNumberInputStepUp"] {
    color: var(--text) !important;
    border-radius: 8px;
}

.stApp [data-testid="stNumberInputStepDown"]:hover,
.stApp [data-testid="stNumberInputStepUp"]:hover { background-color: var(--brand-soft) !important; }

/* Drop-down lists open outside the app, so style them directly. */
[data-baseweb="popover"] > div,
[data-baseweb="popover"] ul,
[data-baseweb="menu"],
[role="listbox"] {
    background: var(--glass-solid) !important;
    border-radius: var(--r-sm) !important;
}

[data-baseweb="popover"] ul, [data-baseweb="menu"] {
    border: 1px solid var(--glass-line) !important;
    box-shadow: var(--shadow-md) !important;
    padding: 4px !important;
}

[data-baseweb="popover"] li,
[data-baseweb="popover"] li * ,
[role="option"], [role="option"] * {
    color: var(--text) !important;
    background-color: transparent;
}

[data-baseweb="popover"] li { border-radius: 8px; transition: background var(--fast) ease; }

[data-baseweb="popover"] li:hover,
[data-baseweb="popover"] li[aria-selected="true"],
[role="option"]:hover, [role="option"][aria-selected="true"] { background: var(--brand-soft) !important; }

/* Tooltips */
[data-baseweb="tooltip"], [data-baseweb="tooltip"] * {
    background: var(--glass-solid) !important;
    color: var(--text) !important;
}

/* =========================================================
   UPLOAD BOX
   ========================================================= */

[data-testid="stFileUploaderDropzone"] {
    border: 1.5px dashed var(--brand-line) !important;
    border-radius: var(--r-md) !important;
    transition: border-color var(--fast) ease, transform var(--mid) var(--ease-spring),
                box-shadow var(--mid) ease;
}

[data-testid="stFileUploaderDropzone"]:hover {
    border-color: var(--aqua) !important;
    transform: scale(1.008);
    box-shadow: inset 0 1px 0 var(--glass-highlight), 0 12px 30px var(--brand-glow);
}

[data-testid="stFileUploaderDropzoneInstructions"] span,
[data-testid="stFileUploaderDropzoneInstructions"] small,
[data-testid="stFileUploaderDropzone"] svg,
[data-testid="stFileUploaderFile"] *,
[data-testid="stFileUploaderFileName"] { color: var(--text) !important; }

[data-testid="stFileUploaderFile"] { background: transparent !important; }

/* =========================================================
   MESSAGE BOXES (st.info / success / warning / error)
   Streamlit draws them in its own light colours, so they get
   tinted glass here. The :has() rules pick the kind.
   ========================================================= */

[data-testid="stAlert"] {
    border-radius: var(--r-md);
    animation: riseIn 380ms var(--ease-out) both;
}

[data-testid="stAlertContainer"],
[data-testid="stAlert"] > div {
    background: var(--alert-info) !important;
    backdrop-filter: var(--blur-soft);
    -webkit-backdrop-filter: var(--blur-soft);
    border: 1px solid var(--glass-line) !important;
    border-left: 4px solid var(--info) !important;
    border-radius: var(--r-md) !important;
    box-shadow: inset 0 1px 0 var(--glass-highlight);
}

[data-testid="stAlertContainer"]:has([data-testid="stAlertContentSuccess"]),
[data-testid="stAlert"] > div:has([data-testid="stAlertContentSuccess"]) {
    background: var(--alert-success) !important;
    border-left-color: var(--ok) !important;
}

[data-testid="stAlertContainer"]:has([data-testid="stAlertContentWarning"]),
[data-testid="stAlert"] > div:has([data-testid="stAlertContentWarning"]) {
    background: var(--alert-warning) !important;
    border-left-color: var(--warn) !important;
}

[data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]),
[data-testid="stAlert"] > div:has([data-testid="stAlertContentError"]) {
    background: var(--alert-error) !important;
    border-left-color: var(--bad) !important;
}

[data-testid="stAlert"] p, [data-testid="stAlert"] span,
[data-testid="stAlert"] li, [data-testid="stAlert"] div {
    color: var(--text) !important;
}

/* Progress bar: glowing palette gradient that flows. */
[data-testid="stProgress"] > div > div > div > div {
    background: linear-gradient(90deg, var(--teal), var(--aqua), var(--sunset), var(--teal)) !important;
    background-size: 220% 100% !important;
    animation: drift 2.6s linear infinite;
    border-radius: var(--r-pill);
    box-shadow: 0 0 14px var(--brand-ring);
}

/* =========================================================
   TABLES, JSON, CODE, IMAGES
   ========================================================= */

[data-testid="stDataFrame"], [data-testid="stTable"] {
    border: 1px solid var(--glass-line);
    border-radius: var(--r-md);
    overflow: hidden;
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-sm);
    animation: fadeIn 420ms ease both;
    transition: box-shadow var(--mid) ease, transform var(--mid) var(--ease-out);
}

[data-testid="stDataFrame"]:hover, [data-testid="stTable"]:hover {
    transform: translateY(-2px);
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-md);
}

[data-testid="stDataFrame"] canvas,
[data-testid="stJson"] { filter: var(--grid-filter); }

[data-testid="stCode"] pre, .stApp pre {
    background: var(--glass-solid) !important;
    border: 1px solid var(--glass-line);
    border-radius: var(--r-sm);
}

.stApp pre code, .stApp pre span { background: transparent !important; }

/* Product and A+ images: rounded, lift on hover. */
[data-testid="stImage"] img, [data-testid="stImageContainer"] img {
    border-radius: var(--r-sm);
    box-shadow: var(--shadow-sm);
    transition: transform var(--mid) var(--ease-spring), box-shadow var(--mid) ease;
}

[data-testid="stImage"] img:hover, [data-testid="stImageContainer"] img:hover {
    transform: translateY(-3px) scale(1.03);
    box-shadow: var(--shadow-hover);
}

/* Scroll reveal: expanders and tables fade up as they scroll into view
   (only in browsers that support it; others just show them). */
@supports (animation-timeline: view()) {
    [data-testid="stExpander"], [data-testid="stDataFrame"] {
        animation: scrollReveal linear both;
        animation-timeline: view();
        animation-range: entry 0% entry 30%;
    }
}

/* =========================================================
   HERO HEADER (large glass panel with gradient edge)
   ========================================================= */

.hero {
    position: relative;
    isolation: isolate;
    overflow: hidden;
    padding: 2.1rem 2.3rem 1.9rem 2.3rem;
    margin-bottom: 1.7rem;
    border-radius: var(--r-lg);
    border: 1px solid transparent;
    /* Glass fill inside, glowing palette gradient on the edge. */
    background:
        var(--glass-strong) padding-box,
        linear-gradient(var(--hero-base), var(--hero-base)) padding-box,
        linear-gradient(130deg, rgba(6,129,135,0.80), rgba(16,187,195,0.45),
                        rgba(254,162,79,0.60), rgba(166,14,53,0.45)) border-box;
    backdrop-filter: var(--blur);
    -webkit-backdrop-filter: var(--blur);
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-md);
    animation: riseIn 700ms var(--ease-out) both;
}

.hero::before, .hero::after {
    content: "";
    position: absolute;
    z-index: -1;
    border-radius: 50%;
    pointer-events: none;
}

.hero::before {
    width: 260px; height: 260px; right: -80px; top: -130px;
    background: radial-gradient(circle, rgba(16,187,195,0.42), transparent 70%);
    animation: floatOrb 9s ease-in-out infinite;
}

.hero::after {
    width: 190px; height: 190px; right: 22%; bottom: -115px;
    background: radial-gradient(circle, rgba(254,162,79,0.36), transparent 70%);
    animation: floatOrb 12s ease-in-out infinite reverse;
}

.hero-shine { animation: sheen 9s var(--ease-out) 1.4s infinite; }

.hero-eyebrow {
    display: inline-flex;
    align-items: center;
    gap: 0.45rem;
    margin: 0 0 0.7rem 0;
    padding: 0.28rem 0.75rem;
    border-radius: var(--r-pill);
    background: var(--brand-soft);
    border: 1px solid var(--brand-line);
    color: var(--accent-text) !important;
    font-size: 0.68rem;
    font-weight: 700;
    letter-spacing: 0.14em;
    text-transform: uppercase;
}

.hero-eyebrow::before {
    content: "";
    width: 6px; height: 6px;
    border-radius: 50%;
    background: var(--aqua);
    box-shadow: 0 0 10px var(--aqua);
}

/* Title with a slow light shimmer passing through the letters. */
.hero-title {
    margin: 0 0 0.45rem 0;
    font-size: clamp(1.6rem, 3vw, 2.3rem);
    font-weight: 800;
    letter-spacing: -0.035em;
    line-height: 1.15;
    color: var(--text) !important;
    background: linear-gradient(100deg, var(--text) 0%, var(--text) 42%,
                var(--aqua) 50%, var(--sunset) 54%, var(--text) 62%, var(--text) 100%);
    background-size: 250% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    -webkit-text-fill-color: transparent;
    animation: textShine 7s ease-in-out 0.8s infinite;
}

.hero-title::after { display: none !important; }

.hero-sub {
    max-width: 820px;
    margin: 0;
    color: var(--text-muted) !important;
    font-size: 0.97rem;
    line-height: 1.6;
}

/* The five-colour palette strip under the hero text. */
.hero-palette {
    display: flex;
    gap: 6px;
    margin-top: 1.1rem;
}

.hero-palette span {
    width: 34px;
    height: 6px;
    border-radius: var(--r-pill);
    transform-origin: left center;
    animation: growX 600ms var(--ease-out) both;
}

.hero-palette span:nth-child(1) { background: var(--crimson); animation-delay: 300ms; }
.hero-palette span:nth-child(2) { background: var(--sunset);  animation-delay: 380ms; }
.hero-palette span:nth-child(3) { background: var(--aqua);    animation-delay: 460ms; }
.hero-palette span:nth-child(4) { background: var(--teal);    animation-delay: 540ms; }
.hero-palette span:nth-child(5) { background: var(--slate);   animation-delay: 620ms; }

/* =========================================================
   BADGES (glass pills with a glowing dot)
   ========================================================= */

.badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    margin: 0 0.3rem 0.3rem 0;
    padding: 0.3rem 0.8rem;
    border-radius: var(--r-pill);
    border: 1px solid transparent;
    backdrop-filter: var(--blur-soft);
    -webkit-backdrop-filter: var(--blur-soft);
    font-size: 0.73rem;
    font-weight: 700;
    letter-spacing: 0.01em;
    white-space: nowrap;
    box-shadow: inset 0 1px 0 var(--glass-highlight);
    animation: riseIn 360ms var(--ease-out) both;
    transition: transform var(--fast) var(--ease-spring), box-shadow var(--fast) ease;
}

.badge::before {
    content: "";
    width: 6px; height: 6px;
    border-radius: 50%;
    background: currentColor;
    box-shadow: 0 0 8px currentColor;
}

.badge:hover { transform: translateY(-2px) scale(1.04); }

.badge-ok   { color: var(--badge-ok);   background: rgba(16,187,195,0.14); border-color: rgba(16,187,195,0.38); }
.badge-warn { color: var(--badge-warn); background: rgba(254,162,79,0.17); border-color: rgba(254,162,79,0.45); }
.badge-bad  { color: var(--badge-bad);  background: rgba(166,14,53,0.14);  border-color: rgba(224,51,95,0.42);
              animation: riseIn 360ms var(--ease-out) both, ringPulse 2.2s ease-out 0.5s 2; }
.badge-info { color: var(--badge-info); background: rgba(89,113,138,0.16); border-color: rgba(89,113,138,0.40); }

/* =========================================================
   FEATURE CARDS (Dashboard) with spinning glow border on hover
   ========================================================= */

.feature-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
    gap: 1rem;
    margin: 0.5rem 0 1.2rem 0;
}

.feature-card {
    position: relative;
    overflow: hidden;
    padding: 1.05rem 1.15rem;
    border-radius: var(--r-md);
    animation: riseIn 520ms var(--ease-out) both;
    transition: transform var(--mid) var(--ease-spring), box-shadow var(--mid) ease,
                border-color var(--mid) ease;
}

/* A light that travels around the card edge while hovered. */
.feature-card::before {
    content: "";
    position: absolute;
    inset: 0;
    padding: 1.5px;
    border-radius: inherit;
    background: conic-gradient(from var(--spin), transparent 0 62%,
                var(--aqua) 74%, var(--sunset) 86%, transparent 100%);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude;
    opacity: 0;
    pointer-events: none;
    transition: opacity var(--mid) ease;
    animation: spin 3.2s linear infinite paused;
}

.feature-card:hover::before { opacity: 1; animation-play-state: running; }

.feature-card:hover {
    transform: translateY(-6px);
    border-color: transparent !important;
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-hover);
}

.feature-card:hover::after { animation: sheen 1.1s var(--ease-out); }

.feature-title {
    margin: 0 0 0.35rem 0;
    color: var(--text) !important;
    font-weight: 700;
    font-size: 0.96rem;
    letter-spacing: -0.015em;
}

.feature-text {
    margin: 0 0 0.7rem 0;
    color: var(--text-muted) !important;
    font-size: 0.84rem;
    line-height: 1.5;
}

/* =========================================================
   TOGGLES, CHECKBOXES, TABS, SCROLLBAR, FOCUS
   ========================================================= */

[data-testid="stCheckbox"] label:hover p,
[data-testid="stToggle"] label:hover p { color: var(--accent-text) !important; }

[data-testid="stTabs"] [role="tablist"] {
    gap: 4px;
    padding: 4px;
    border-radius: var(--r-pill);
    background: var(--glass);
    border: 1px solid var(--glass-line);
    width: fit-content;
}

[data-testid="stTabs"] [data-baseweb="tab-highlight"],
[data-testid="stTabs"] [data-baseweb="tab-border"] { display: none; }

[data-testid="stTabs"] button[role="tab"] {
    border-radius: var(--r-pill);
    padding: 0.35rem 1rem;
    background: transparent;
    transition: background var(--fast) ease, color var(--fast) ease;
}

[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: var(--glass-strong);
    box-shadow: inset 0 1px 0 var(--glass-highlight), var(--shadow-sm);
}

::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-thumb {
    background: var(--scroll-thumb);
    border-radius: var(--r-pill);
    border: 2px solid transparent;
    background-clip: padding-box;
}
::-webkit-scrollbar-track { background: transparent; }

:focus-visible {
    outline: 3px solid var(--brand-ring) !important;
    outline-offset: 2px !important;
}

/* =========================================================
   ACCESSIBILITY AND PERFORMANCE FALLBACKS
   ========================================================= */

/* Browsers without blur support get a more solid panel. */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
    [data-testid="stMetric"], [data-testid="stForm"], [data-testid="stExpander"] details,
    [data-testid="stSidebar"], .feature-card, .hero {
        background: var(--glass-solid) !important;
    }
}

/* People who ask for less transparency get solid panels. */
@media (prefers-reduced-transparency: reduce) {
    [data-testid="stMetric"], [data-testid="stForm"], [data-testid="stExpander"] details,
    [data-testid="stSidebar"], .feature-card, .hero, .badge,
    .stButton > button, [data-testid="stFormSubmitButton"] > button {
        background: var(--glass-solid) !important;
        backdrop-filter: none !important;
        -webkit-backdrop-filter: none !important;
    }
}

/* People who ask for less motion get no movement. */
@media (prefers-reduced-motion: reduce) {
    *, *::before, *::after {
        animation-duration: 0.01ms !important;
        animation-iteration-count: 1 !important;
        transition-duration: 0.01ms !important;
        scroll-behavior: auto !important;
    }
}

@media (max-width: 768px) {
    .block-container { padding: 1.2rem 1rem 3rem 1rem; }
    .hero { padding: 1.4rem 1.25rem; border-radius: var(--r-md); }
    [data-testid="stMetric"] { padding: 0.9rem; }
    .stApp::after { display: none; }
}
"""


# =========================================================
# 3. PUBLIC HELPERS (names and arguments unchanged)
# =========================================================

def apply_theme(mode="light"):
    """
    Inject the theme. Call once, directly after st.set_page_config().
    mode: "light" or "dark" (anything else falls back to light).
    """

    mode = mode if mode in PALETTES else "light"

    # Rerun once (never twice in a row) when Streamlit's colours changed.
    just_reran = st.session_state.pop("_theme_rerun", False)

    if sync_streamlit_theme(mode) and not just_reran:
        st.session_state["_theme_rerun"] = True
        st.rerun()

    st.markdown(
        "<style>\n" + _palette_css(mode) + "\n" + THEME_CSS + "\n</style>",
        unsafe_allow_html=True
    )


def render_header(title, subtitle="", eyebrow="AMAZON UK  •  LISTING INTELLIGENCE"):
    """Render the animated glass hero header. Text is HTML-escaped for safety."""

    st.markdown(
        f"""
        <section class="hero">
            <div class="hero-shine"></div>
            <p class="hero-eyebrow">{escape(str(eyebrow))}</p>
            <div class="hero-title">{escape(str(title))}</div>
            <p class="hero-sub">{escape(str(subtitle))}</p>
            <div class="hero-palette"><span></span><span></span><span></span><span></span><span></span></div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def badge(text, kind="info"):
    """Return a safe HTML badge; kind must be ok, warn, bad, or info."""

    safe_kind = kind if kind in {"ok", "warn", "bad", "info"} else "info"

    return f'<span class="badge badge-{safe_kind}">{escape(str(text))}</span>'


def render_feature_grid(items):
    """
    Draw a grid of glass cards.
    items: list of (title, description, status_text, badge_kind).
    Cards appear one after another (staggered animation).
    """

    cards = []

    for index, (title, description, status_text, kind) in enumerate(items):

        cards.append(
            f'<div class="feature-card" style="animation-delay:{index * 45}ms">'
            f'<p class="feature-title">{escape(str(title))}</p>'
            f'<p class="feature-text">{escape(str(description))}</p>'
            f'{badge(status_text, kind)}'
            f'</div>'
        )

    st.markdown(
        '<div class="feature-grid">' + "".join(cards) + "</div>",
        unsafe_allow_html=True
    )
