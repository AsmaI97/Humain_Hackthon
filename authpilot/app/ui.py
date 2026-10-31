"""Shared look for the Streamlit pages: one stylesheet and small HTML components.

Every piece of dynamic text goes through esc() before it is placed in HTML.
"""

from html import escape

import streamlit as st

# Status pills always carry a text label. Colors are background, foreground.
STATUS_COLORS = {
    "approved": ("#CFEFDB", "#1F4A52"),
    "met": ("#CFEFDB", "#1F4A52"),
    "submitted": ("#E8F5EE", "#1F4A52"),
    "checking": ("#E8EEF0", "#1F4A52"),
    "intake": ("#E8EEF0", "#1F4A52"),
    "ready_for_approval": ("#E6F76B", "#1F4A52"),
    "appealing": ("#E8F5EE", "#1F4A52"),
    "needs_evidence": ("#FEF1DC", "#8A3B07"),
    "unclear": ("#E8EEF0", "#1F4A52"),
    "queued": ("#FEF1DC", "#8A3B07"),
    "escalated": ("#FEF1DC", "#8A3B07"),
    "denied": ("#FBE3E3", "#8A1F1F"),
    "not_met": ("#FBE3E3", "#8A1F1F"),
}

TIMELINE_COLORS = {
    "step": "#2C6E77", "verdict": "#1F4A52", "tool call": "#3F7078", "tool result": "#3F7078",
    "model": "#3F7078", "human": "#2C6E77", "fallback": "#8A3B07", "error": "#8A1F1F", "event": "#1F4A52",
}

_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap');

.stApp, [data-testid="stMain"], [data-testid="stAppViewContainer"] {
  background: #4B9E96;
  color: #1F4A52;
  font-family: "Inter Tight", "Avenir Next", "Segoe UI", sans-serif;
}
.stApp :where(p, li, h1, h2, h3, label, button, input, textarea) {
  font-family: "Inter Tight", "Avenir Next", "Segoe UI", sans-serif;
}
[data-testid="stIconMaterial"] {
  font-family: "Material Symbols Rounded" !important;
  font-weight: 400 !important;
  letter-spacing: normal !important;
}
.ap-mono, .ap-quote, .ap-quote .src, .ap-tl-time,
.ap-mono *, .ap-quote * {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace !important;
}
header[data-testid="stHeader"] { background: #FFFFFF; }
[data-testid="stSidebar"] { background: #FFFFFF; }
[data-testid="stSidebarContent"] { display: flex; flex-direction: column; }
[data-testid="stSidebarUserContent"] { order: 1; }
[data-testid="stSidebarNav"] { order: 2; }
.block-container { max-width: 1320px; padding: 16px 16px 40px; }
[data-testid="stSidebar"] [data-testid="stMarkdown"] p,
[data-testid="stSidebar"] label,
[data-testid="stWidgetLabel"] p,
[data-testid="stMarkdown"] p,
[data-testid="stMarkdown"] li {
  font-family: "Inter Tight", "Avenir Next", "Segoe UI", sans-serif;
}

[class*="st-key-panel"], [class*="st-key-deep"] {
  border-radius: 28px;
  padding: 72px 40px !important;
  margin-bottom: 16px;
  box-shadow: 0 12px 40px rgba(11, 31, 42, 0.09);
}
[class*="st-key-panel"] { background: #FFFFFF; color: #1F4A52; }
[class*="st-key-deep"] { background: #2A6872; color: #FFFFFF; }
.st-key-panel_footer { padding: 28px 40px !important; }
[class*="st-key-card"], [class*="st-key-q_"], .st-key-gate {
  background: #F1F8F5;
  border-radius: 22px;
  padding: 16px 18px !important;
  margin-bottom: 12px;
}
.st-key-gate { background: #FFFFFF; border: 2px solid #E6F76B; }

.ap-skip {
  position: absolute; left: 12px; top: -56px; z-index: 100000;
  background: #E6F76B; color: #1F4A52; font-weight: 700; font-size: 15px;
  text-decoration: none; border-radius: 999px; min-height: 44px;
  padding: 10px 18px; display: inline-flex; align-items: center;
}
.ap-skip:focus, .ap-skip:focus-visible { top: 12px; }

.ap-brand { display: flex; align-items: center; gap: 10px; margin: 0 0 16px 0; }
.ap-word { font-weight: 800; letter-spacing: -0.035em; color: #2C6E77; line-height: 1; }
.ap-hero-title, .ap-section-title, .ap-panel-title {
  font-family: "Inter Tight", "Avenir Next", "Segoe UI", sans-serif !important;
  font-weight: 800 !important; letter-spacing: -0.035em !important; margin: 0 0 16px 0;
}
.ap-hero-title { font-size: clamp(40px, 5.4vw, 72px) !important; line-height: 0.98 !important; color: #2C6E77; }
.ap-section-title { font-size: clamp(28px, 3.2vw, 40px) !important; line-height: 0.98 !important; color: #2C6E77; }
.ap-panel-title {
  line-height: 1.05 !important; font-size: 28px !important; color: #2C6E77; margin: 0 0 12px 0;
}
.ap-accent { color: #2F9A6E; }
.ap-eyebrow {
  font-size: 13px; font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase;
  color: #2C6E77; margin: 0 0 8px 0;
}
.ap-lead { font-size: 16px; line-height: 1.5; color: #1F4A52; max-width: 68ch; margin: 0 0 16px 0; }
.ap-muted { color: #3F7078; font-size: 14px; }
.ap-mono, .ap-quote, .ap-quote .src, .ap-tl-time {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, monospace;
}

.ap-card {
  background: #E8F5EE; border-radius: 22px; padding: 18px 20px; margin-bottom: 12px; height: 100%;
}
.ap-card h3 { margin: 0 0 8px 0; font-size: 18px; font-weight: 800; letter-spacing: -0.03em; color: #2C6E77; }
.ap-card p, .ap-card li { color: #1F4A52; font-size: 15px; line-height: 1.45; margin: 0; }
.ap-card ul { padding-left: 1.1rem; margin: 8px 0 0 0; }
.ap-crit { border-left: 6px solid #2C6E77; }
.ap-rule { border-top: 2px solid #94D6AB; padding: 16px 0 8px 0; }
.ap-rule h3 { margin: 0 0 6px 0; color: #2C6E77; font-size: 20px; font-weight: 800; letter-spacing: -0.03em; }
.ap-rule p { margin: 0; color: #1F4A52; font-size: 15px; line-height: 1.45; }

.ap-tall {
  background: #2A6872; color: #FFFFFF; border-radius: 22px; min-height: 220px; padding: 20px;
  display: flex; flex-direction: column; justify-content: space-between; height: 100%;
}
.ap-tall .num, .ap-step .num { font-weight: 800; font-size: 13px; letter-spacing: 0.06em; color: #D8EFE6; }
.ap-tall p { color: #FFFFFF; font-size: 16px; line-height: 1.35; margin: 16px 0 0 0; font-weight: 700; }
.ap-grid { display: grid; gap: 12px; }
.ap-grid.five { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.ap-grid.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.ap-grid.four { grid-template-columns: repeat(4, minmax(0, 1fr)); }
.ap-grid.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }

.ap-steps { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; margin: 8px 0 20px 0; }
.ap-step {
  border: 1px solid rgba(255, 255, 255, 0.45); border-radius: 22px; padding: 16px 16px 18px;
  min-height: 112px; background: transparent;
}
.ap-step h3 { color: #FFFFFF; font-size: 16px; font-weight: 800; margin: 16px 0 0 0; letter-spacing: -0.02em; }
.ap-step.gate { background: #E6F76B; border-color: #E6F76B; }
.ap-step.gate .num, .ap-step.gate h3 { color: #1F4A52; }

.ap-safe h3 { color: #94D6AB; font-size: 22px; font-weight: 800; letter-spacing: -0.03em; margin: 0 0 8px 0; }
.ap-safe p { color: #D8EFE6; font-size: 15px; line-height: 1.45; margin: 0; }

.ap-target { background: #E8F5EE; border-radius: 22px; padding: 18px; }
.ap-target h3 { color: #2C6E77; font-size: 18px; font-weight: 800; letter-spacing: -0.03em; margin: 6px 0; }
.ap-target p { color: #1F4A52; font-size: 15px; margin: 0 0 10px 0; }
.ap-target-value { color: #2C6E77; font-weight: 800; font-size: 20px; letter-spacing: -0.03em; }
.ap-pending { color: #3F7078; font-size: 14px; margin-top: 6px; }
.ap-kicker { font-size: 13px; font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; color: #3F7078; }

.ap-mock { background: #2A6872; border-radius: 22px; padding: 22px; }
.ap-mock h3 { color: #FFFFFF; font-size: 22px; font-weight: 800; letter-spacing: -0.03em; margin: 8px 0 12px 0; }
.ap-mock .ap-kicker { color: #D8EFE6; }
.ap-overlay {
  color: #94D6AB; font-weight: 800; font-size: clamp(20px, 2vw, 28px);
  letter-spacing: -0.03em; line-height: 1.15; margin: 18px 0 0 0;
}
.ap-stat { font-weight: 800; font-size: 28px; letter-spacing: -0.035em; color: #2C6E77; line-height: 1.1; }
.ap-stat-label { color: #3F7078; font-size: 14px; margin-top: 4px; }
.ap-stat-box { background: #E8F5EE; border-radius: 22px; padding: 16px 18px; height: 100%; }

.ap-badge {
  display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 13px;
  font-weight: 700; letter-spacing: 0.02em; margin: 0 6px 6px 0; white-space: nowrap;
}
.ap-chip {
  display: inline-block; padding: 6px 12px; border-radius: 999px; background: #E8F5EE; color: #1F4A52;
  font-size: 14px; font-weight: 600; margin: 4px 6px 4px 0; border: 1px solid transparent;
}
.ap-chip.solid { background: #FFFFFF; }
.ap-chip.lime { background: #E6F76B; color: #1F4A52; }
.ap-chip.line { background: #FFFFFF; border-color: #2C6E77; color: #1F4A52; }
.ap-quote {
  background: #F1F8F5; border-radius: 12px; padding: 12px 14px; margin: 8px 0;
  font-size: 14px; color: #1F4A52; line-height: 1.45;
}
.ap-quote .src { display: block; color: #3F7078; font-size: 13px; margin-top: 6px; }
.ap-gap { margin-top: 8px; font-size: 15px; color: #1F4A52; line-height: 1.4; }
.ap-gap-label {
  display: inline-block; background: #FEF1DC; color: #8A3B07; border-radius: 999px;
  padding: 3px 10px; font-size: 13px; font-weight: 700; margin-inline-end: 8px;
}
.ap-letter {
  background: #F1F8F5; border-radius: 22px; padding: 20px 22px; font-size: 16px;
  color: #1F4A52; line-height: 1.55; font-family: "Inter Tight", "Avenir Next", "Segoe UI", sans-serif;
}
.ap-banner { border-radius: 22px; padding: 14px 18px; margin: 0 0 16px 0; font-size: 15px; font-weight: 700; }
.ap-banner.warn { background: #FEF1DC; color: #8A3B07; }
.ap-banner.info { background: #E8F5EE; color: #1F4A52; }
.ap-timeline { margin: 0; }
.ap-tl-item { background: #F1F8F5; border-radius: 16px; padding: 12px 14px; margin: 0 0 10px 0; }
.ap-tl-time { color: #3F7078; font-size: 13px; }
.ap-tl-kind { font-weight: 700; font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase; }
.ap-tl-text { color: #1F4A52; font-size: 15px; margin-top: 4px; }
.ap-footer { color: #3F7078; font-size: 14px; margin: 8px 0 0 0; line-height: 1.45; }
a.ap-pill {
  display: inline-flex; align-items: center; min-height: 44px; padding: 0 18px; border-radius: 999px;
  background: #E6F76B; color: #1F4A52; font-weight: 700; font-size: 15px; text-decoration: none;
}

[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"],
.st-key-cta_primary [data-testid="stPageLink-NavLink"],
.st-key-cta_secondary [data-testid="stPageLink-NavLink"] {
  border-radius: 999px !important;
  min-height: 44px !important;
  font-weight: 700 !important;
  font-size: 15px !important;
  padding: 8px 18px !important;
  text-decoration: none !important;
}
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-primary"] p,
[data-testid="stBaseButton-primary"] span,
.st-key-cta_primary [data-testid="stPageLink-NavLink"] {
  background-color: #E6F76B !important;
  color: #1F4A52 !important;
  border: 1px solid #E6F76B !important;
}
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-secondary"] p,
[data-testid="stBaseButton-secondary"] span,
.st-key-cta_secondary [data-testid="stPageLink-NavLink"] {
  background-color: #FFFFFF !important;
  color: #1F4A52 !important;
  border: 1px solid #2C6E77 !important;
}
[data-testid="stBaseButton-primary"]:disabled,
[data-testid="stBaseButton-secondary"]:disabled {
  opacity: 0.5 !important;
  cursor: not-allowed !important;
}
[data-testid="stSidebarNavLink"] {
  color: #1F4A52 !important;
  font-size: 15px !important;
  min-height: 44px;
  border-radius: 999px;
}
[data-testid="stSelectbox"] [role="group"] {
  background-color: #FFFFFF !important;
  border: 1px solid #2C6E77 !important;
}
[data-testid="stMetric"] { background: #E8F5EE; border-radius: 22px; padding: 14px 16px; }
[data-testid="stMetricValue"] { color: #2C6E77 !important; font-weight: 800; }
[data-testid="stMetricLabel"] { color: #3F7078 !important; font-size: 14px !important; }
[data-testid="stCaptionContainer"], [data-testid="stCaptionContainer"] p {
  color: #3F7078 !important; font-size: 14px !important;
}
[data-testid="stDataFrame"], [data-testid="stTable"] { overflow-x: auto; max-width: 100%; }

[class*="st-key-deep"] .ap-section-title,
[class*="st-key-deep"] .ap-panel-title,
[class*="st-key-deep"] .ap-hero-title { color: #FFFFFF !important; }
[class*="st-key-deep"] .ap-eyebrow,
[class*="st-key-deep"] [data-testid="stMarkdownContainer"] p,
[class*="st-key-deep"] [data-testid="stMarkdownContainer"] li { color: #D8EFE6 !important; font-size: 16px !important; }
[class*="st-key-deep"] .ap-safe h3, [class*="st-key-deep"] .ap-overlay { color: #94D6AB !important; }
[class*="st-key-deep"] .ap-step.gate h3,
[class*="st-key-deep"] .ap-step.gate .num { color: #1F4A52 !important; }

.stApp :focus-visible {
  outline: 2px solid #E6F76B !important;
  outline-offset: 2px !important;
  box-shadow: 0 0 0 2px #2C6E77 !important;
}
a, button, [data-testid="stPageLink-NavLink"] {
  transition: color 150ms, background-color 150ms, opacity 150ms;
}

@media (max-width: 900px) {
  .ap-grid.five, .ap-grid.four, .ap-steps { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: 640px) {
  [class*="st-key-panel"], [class*="st-key-deep"], .st-key-panel_footer { padding: 20px !important; border-radius: 22px; }
  .ap-grid.five, .ap-grid.four, .ap-grid.three, .ap-grid.two, .ap-steps { grid-template-columns: 1fr; }
  [data-testid="stHorizontalBlock"] { flex-wrap: wrap !important; }
  [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important; flex: 1 1 100% !important; min-width: 100% !important;
  }
}
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation: none !important;
    transition: none !important;
    scroll-behavior: auto !important;
  }
}
[data-testid="stMarkdownContainer"],
[data-testid="stMarkdownContainer"] p,
[data-testid="stMarkdownContainer"] li,
[data-testid="stMarkdownContainer"] h1,
[data-testid="stMarkdownContainer"] h2,
[data-testid="stMarkdownContainer"] h3,
[data-testid="stCaptionContainer"],
[data-testid="stCaptionContainer"] p,
[data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-secondary"],
[data-testid="stPageLink-NavLink"],
[data-testid="stSidebarNavLink"],
.ap-word, .ap-lead, .ap-chip, .ap-badge, .ap-card, .ap-card h3, .ap-card p, .ap-card li,
.ap-rule h3, .ap-rule p, .ap-eyebrow, .ap-footer, .ap-banner, .ap-stat, .ap-stat-label {
  font-family: "Inter Tight", "Avenir Next", "Segoe UI", sans-serif !important;
}
.stApp .ap-mono, .stApp .ap-quote, .stApp .ap-quote .src, .stApp .ap-tl-time {
  font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace !important;
}
</style>
"""

_RTL_CSS = """
<style>
.block-container, [data-testid="stSidebar"] {direction: rtl; text-align: right;}
.ap-quote, .ap-letter.ltr, .ap-mono, .ap-tl-time, code {direction: ltr; text-align: left; unicode-bidi: plaintext;}
.ap-chip { unicode-bidi: plaintext; }
.ap-stat, [data-testid="stMetricValue"] {direction: ltr; text-align: right; unicode-bidi: isolate;}
.ap-letter.rtl {direction: rtl; text-align: right; unicode-bidi: plaintext;
  font-family: "Geeza Pro", "Noto Naskh Arabic", "Segoe UI", Tahoma, sans-serif; line-height: 1.9;}
.ap-crit {border-left-width: 0; border-right-width: 6px; border-right-style: solid;}
.ap-card ul {padding-left: 0; padding-right: 1.1rem;}
.ap-eyebrow {letter-spacing: 0;}
</style>
"""

TIMELINE_KINDS_AR = {
    "step": "خطوة", "verdict": "حكم", "human": "إجراء بشري", "fallback": "إجراء احتياطي", "error": "خطأ",
    "event": "حدث", "tool call": "استدعاء أداة", "tool result": "نتيجة أداة", "model": "نموذج",
}


def esc(value) -> str:
    return escape("" if value is None else str(value))


def _lang() -> str:
    from authpilot.app.strings import lang

    return lang()


def mark(size: int = 38) -> str:
    return (
        f'<svg class="ap-mark" width="{size}" height="{size}" viewBox="0 0 32 32" aria-hidden="true">'
        '<rect width="32" height="32" rx="10" fill="#2C6E77"/>'
        '<path d="M9 24L16 8L23 24" fill="none" stroke="#fff" stroke-width="3" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        '<path d="M12.6 20.2L15 22.6L19.4 17.2" fill="none" stroke="#E6F76B" stroke-width="2.6" '
        'stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )


def wordmark(size: int = 38) -> str:
    text = 22 if size >= 36 else 18
    return (
        f'<div class="ap-brand">{mark(size)}'
        f'<span class="ap-word" style="font-size:{text}px">AuthPilot</span></div>'
    )


def skip_link(label: str) -> str:
    return f'<a class="ap-skip" href="#ap-main">{esc(label)}</a>'


def inject_theme() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)
    if _lang() == "ar":
        st.markdown(_RTL_CSS, unsafe_allow_html=True)


def inject_css() -> None:
    inject_theme()
    from authpilot import config
    if config.LLM_MODE == "stub":
        from authpilot.app.strings import t
        banner(t("stub_mode_banner"), "warn")


def html(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)


def badge(label: str, key: str | None = None) -> str:
    from authpilot.app.strings import status_label

    bg, fg = STATUS_COLORS.get(key or label, ("#E8EEF0", "#1F4A52"))
    shown = status_label(label) if label in STATUS_COLORS else label.replace("_", " ")
    return f'<span class="ap-badge" style="background:{bg};color:{fg}">{esc(shown)}</span>'


def card(title: str, body: str, accent: str | None = None, extra_class: str = "") -> str:
    side = "right" if _lang() == "ar" else "left"
    style = f' style="border-{side}-color:{accent}"' if accent else ""
    return f'<div class="ap-card {extra_class}"{style}><h3>{esc(title)}</h3>{body}</div>'


def bullet_list(items: list[str]) -> str:
    return "<ul>" + "".join(f"<li>{esc(item)}</li>" for item in items) + "</ul>"


def quote(text: str, source: str) -> str:
    return f'<div class="ap-quote">&ldquo;{esc(text)}&rdquo;<span class="src">{esc(source)}</span></div>'


def letter(text: str, rtl: bool = False) -> str:
    """Show text exactly as written. Blank lines would otherwise end the HTML block and let
    Markdown reformat the content, so line breaks are emitted as <br>."""
    direction = "rtl" if rtl else "ltr"
    return f'<div class="ap-letter {direction}" dir="{direction}">{esc(text).replace(chr(10), "<br>")}</div>'


def banner(text: str, kind: str = "info") -> None:
    html(f'<div class="ap-banner {kind}" role="status" dir="auto">{esc(text)}</div>')


def eyebrow(text: str) -> None:
    html(f'<p class="ap-eyebrow">{esc(text)}</p>')


def section_title(text: str, level: int = 2, anchor: bool = False, compact: bool = False) -> None:
    tag = "h1" if level == 1 else "h2"
    ident = ' id="ap-main"' if anchor else ""
    klass = "ap-panel-title" if compact else "ap-section-title"
    html(f'<{tag} class="{klass}"{ident}>{esc(text)}</{tag}>')


def timeline(rows: list[dict]) -> str:
    items = []
    arabic = _lang() == "ar"
    for row in rows:
        color = TIMELINE_COLORS.get(row["kind"], "#3F7078")
        kind = TIMELINE_KINDS_AR.get(row["kind"], row["kind"]) if arabic else row["kind"]
        items.append(
            f'<div class="ap-tl-item">'
            f'<div class="ap-tl-time">{esc(row["time"])}</div>'
            f'<div class="ap-tl-kind" style="color:{color}">{esc(kind)}</div>'
            f'<div class="ap-tl-text">{esc(row["detail"])}</div></div>'
        )
    return '<div class="ap-timeline">' + "".join(items) + "</div>"


def flow(steps: list[tuple[str, bool]]) -> str:
    """steps: (label, is_human_gate)."""
    parts = []
    for label, gate in steps:
        parts.append(f'<span class="ap-chip{" lime" if gate else ""}">{esc(label)}</span>')
    return '<div class="ap-flow">' + "".join(parts) + "</div>"
