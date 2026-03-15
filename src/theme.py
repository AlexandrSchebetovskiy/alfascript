"""
theme.py — Visual theme definitions and persistence.

Provides:
- THEMES_DATA   — dict of all CSS variable palettes keyed by "{vstyle}_{vmode}".
- load_appearance()  — read vstyle + vmode from theme.json.
- save_appearance()  — write vstyle + vmode to theme.json.
"""

import json
from paths import THEME_FILE


# ---------------------------------------------------------------------------
# Theme palette registry
# ---------------------------------------------------------------------------
# Keys are "{vstyle}_{vmode}". Values are dicts of CSS variable names → values.
# These are passed to both index.html (Jinja) and log.html for colour sync.

THEMES_DATA: dict[str, dict[str, str]] = {
    "default_dark":   {"bg": "#0f1117", "glass": "#1a1d2e", "border": "#2a2d3e", "accent": "#7c3aed", "text": "#e2e8f0", "text_dim": "#64748b", "green": "#22c55e", "yellow": "#eab308", "red": "#ef4444"},
    "default_light":  {"bg": "#f1f5fb", "glass": "#ffffff",  "border": "#e2e8f0", "accent": "#7c3aed", "text": "#0f172a", "text_dim": "#64748b", "green": "#059669", "yellow": "#d97706", "red": "#dc2626"},
    "latte_light":    {"bg": "#fdf8f0", "glass": "rgba(255,251,243,.88)", "border": "rgba(180,83,9,.15)",   "accent": "#b45309", "text": "#1c0f00", "text_dim": "#78350f", "green": "#15803d", "yellow": "#a16207", "red": "#b91c1c"},
    "ocean_light":    {"bg": "#e0f2fe", "glass": "rgba(255,255,255,.85)", "border": "rgba(3,105,161,.18)",  "accent": "#0369a1", "text": "#0c1a2e", "text_dim": "#075985", "green": "#0d6e3a", "yellow": "#a16207", "red": "#b91c1c"},
    "frost_dark":     {"bg": "#0d1520", "glass": "rgba(30,41,59,.72)",    "border": "rgba(148,163,184,.2)", "accent": "#818cf8", "text": "#f1f5f9", "text_dim": "#94a3b8", "green": "#10b981", "yellow": "#f59e0b", "red": "#ef4444"},
    "frost_light":    {"bg": "#e8eeff", "glass": "rgba(255,255,255,.7)",  "border": "rgba(199,210,254,.8)", "accent": "#7c3aed", "text": "#1e293b", "text_dim": "#475569", "green": "#059669", "yellow": "#d97706", "red": "#dc2626"},
    "meadow_light":   {"bg": "#f0fdf4", "glass": "rgba(255,255,255,.85)", "border": "rgba(22,163,74,.18)",  "accent": "#16a34a", "text": "#052e16", "text_dim": "#166534", "green": "#16a34a", "yellow": "#a16207", "red": "#b91c1c"},
    "ember_dark":     {"bg": "#0d0200", "glass": "rgba(20,8,0,.82)",      "border": "rgba(251,146,60,.18)", "accent": "#fb923c", "text": "#fef3c7", "text_dim": "#d4a574", "green": "#65a30d", "yellow": "#eab308", "red": "#ef4444"},
    "ember_light":    {"bg": "#fff7ed", "glass": "#ffffff",                "border": "#fed7aa",              "accent": "#ea580c", "text": "#431407", "text_dim": "#9a3412", "green": "#15803d", "yellow": "#ca8a04", "red": "#dc2626"},
    "sakura_dark":    {"bg": "#12020a", "glass": "rgba(30,5,20,.84)",     "border": "rgba(249,168,212,.2)", "accent": "#ec4899", "text": "#fce7f3", "text_dim": "#f9a8d4", "green": "#34d399", "yellow": "#fbbf24", "red": "#f87171"},
    "sakura_light":   {"bg": "#fff5f9", "glass": "rgba(255,255,255,.72)", "border": "rgba(249,168,212,.65)","accent": "#db2777", "text": "#500724", "text_dim": "#9d174d", "green": "#059669", "yellow": "#d97706", "red": "#dc2626"},
    "void_dark":      {"bg": "#08090a", "glass": "#0d0e0f",               "border": "rgba(255,255,255,.07)","accent": "#94a3b8", "text": "#e2e8f0", "text_dim": "#475569", "green": "#22c55e", "yellow": "#eab308", "red": "#ef4444"},
    "void_light":     {"bg": "#fafafa", "glass": "#ffffff",                "border": "#e5e7eb",              "accent": "#6b7280", "text": "#111827", "text_dim": "#6b7280", "green": "#059669", "yellow": "#d97706", "red": "#dc2626"},
    "matrix_dark":    {"bg": "#000500", "glass": "rgba(0,5,0,.9)",        "border": "rgba(0,255,65,.16)",   "accent": "#00ff41", "text": "#00ff41", "text_dim": "#00aa2a", "green": "#00ff41", "yellow": "#ffe600", "red": "#ff3333"},
    "matrix_light":   {"bg": "#f0fdf4", "glass": "#ffffff",                "border": "#a7f3d0",              "accent": "#16a34a", "text": "#052e16", "text_dim": "#166534", "green": "#059669", "yellow": "#ca8a04", "red": "#dc2626"},
    "sunset_dark":    {"bg": "#0a0108", "glass": "rgba(15,3,5,.7)",       "border": "rgba(245,158,11,.18)", "accent": "#f59e0b", "text": "#fef3c7", "text_dim": "#fbbf24", "green": "#65a30d", "yellow": "#eab308", "red": "#ef4444"},
    "sunset_light":   {"bg": "#fff7ed", "glass": "#ffffff",                "border": "#fde68a",              "accent": "#d97706", "text": "#451a03", "text_dim": "#92400e", "green": "#15803d", "yellow": "#ca8a04", "red": "#dc2626"},
    "neon_dark":      {"bg": "#080014", "glass": "rgba(18,0,34,.82)",     "border": "rgba(232,121,249,.2)", "accent": "#e879f9", "text": "#fdf4ff", "text_dim": "#d8b4fe", "green": "#4ade80", "yellow": "#facc15", "red": "#fb7185"},
    "abyss_dark":     {"bg": "#010810", "glass": "rgba(1,14,32,.84)",     "border": "rgba(34,211,238,.16)", "accent": "#22d3ee", "text": "#e0f2fe", "text_dim": "#7dd3fc", "green": "#22c55e", "yellow": "#fbbf24", "red": "#f87171"},
    "blood_dark":     {"bg": "#0c0003", "glass": "rgba(18,0,6,.84)",      "border": "rgba(244,63,94,.17)",  "accent": "#f43f5e", "text": "#fff1f2", "text_dim": "#fda4af", "green": "#4ade80", "yellow": "#fbbf24", "red": "#f43f5e"},
    "aurora_dark":    {"bg": "#01080f", "glass": "rgba(1,12,26,.76)",     "border": "rgba(16,185,129,.18)", "accent": "#10b981", "text": "#ecfdf5", "text_dim": "#6ee7b7", "green": "#10b981", "yellow": "#fbbf24", "red": "#f87171"},
    "coal_dark":      {"bg": "#0b0b0b", "glass": "rgba(16,16,16,.92)",    "border": "rgba(161,161,170,.11)","accent": "#a1a1aa", "text": "#f4f4f5", "text_dim": "#a1a1aa", "green": "#22c55e", "yellow": "#eab308", "red": "#ef4444"},
    "cloud_light":    {"bg": "#f0f9ff", "glass": "rgba(255,255,255,.82)", "border": "rgba(14,165,233,.2)",  "accent": "#0ea5e9", "text": "#0c2340", "text_dim": "#0369a1", "green": "#0d9488", "yellow": "#ca8a04", "red": "#dc2626"},
    "peach_light":    {"bg": "#fff5f0", "glass": "rgba(255,255,255,.86)", "border": "rgba(249,115,22,.18)", "accent": "#f97316", "text": "#3b1003", "text_dim": "#9a3412", "green": "#15803d", "yellow": "#ca8a04", "red": "#dc2626"},
    "mint_light":     {"bg": "#f0fffe", "glass": "rgba(255,255,255,.86)", "border": "rgba(13,148,136,.18)", "accent": "#0d9488", "text": "#042f2e", "text_dim": "#0f766e", "green": "#15803d", "yellow": "#ca8a04", "red": "#dc2626"},
    "lavender_light": {"bg": "#faf5ff", "glass": "rgba(255,255,255,.8)",  "border": "rgba(147,51,234,.18)", "accent": "#9333ea", "text": "#2d0a5e", "text_dim": "#6b21a8", "green": "#15803d", "yellow": "#ca8a04", "red": "#dc2626"},
    "gold_light":     {"bg": "#fffbeb", "glass": "rgba(255,255,255,.86)", "border": "rgba(217,119,6,.2)",   "accent": "#d97706", "text": "#451a03", "text_dim": "#92400e", "green": "#15803d", "yellow": "#d97706", "red": "#dc2626"},
}


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

_DEFAULT_VSTYLE = "default"
_DEFAULT_VMODE  = "dark"


def load_appearance() -> tuple[str, str]:
    """Read vstyle and vmode from theme.json.

    Returns ``(vstyle, vmode)``, falling back to defaults on any error.
    """
    try:
        with open(THEME_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
        vstyle = d.get("vstyle", _DEFAULT_VSTYLE)
        vmode  = d.get("vmode",  _DEFAULT_VMODE)
        return vstyle, vmode
    except Exception:
        return _DEFAULT_VSTYLE, _DEFAULT_VMODE


def save_appearance(vstyle: str, vmode: str) -> None:
    """Write vstyle and vmode to theme.json. Silently ignores write errors."""
    try:
        with open(THEME_FILE, "w", encoding="utf-8") as f:
            json.dump({"vstyle": vstyle, "vmode": vmode}, f)
    except Exception:
        pass


def current_theme_key(vstyle: str, vmode: str) -> str:
    """Return the THEMES_DATA key for a given vstyle + vmode pair."""
    return f"{vstyle}_{vmode}"
