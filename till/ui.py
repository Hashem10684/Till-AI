"""Shared look: bold sticker styling, status rows and charts."""
from __future__ import annotations

from html import escape

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

INK, MUTED, GRID = "#17132E", "#5A5475", "#E4DFF5"
GRAPE, ORANGE = "#5B2EFF", "#F2600C"
SUN, PINK, MINT, LILAC = "#FFD23F", "#FF9CCF", "#6EE7B7", "#F1EDFF"
GOOD, BAD, FLAT = "#0F7A4F", "#C4243B", "#A66A00"
STATUS = {"critical": (BAD, "error", "Fix this"), "warning": (FLAT, "bolt", "Heads up"),
          "good": (GOOD, "celebration", "Nice"), "info": (GRAPE, "info", "Tip")}

CSS = f"""
<style>
header[data-testid="stHeader"], [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {{ display: none; }}
.block-container {{ padding-top: 1.2rem; padding-bottom: 5rem; max-width: 1080px; }}
h1, h2, h3 {{ letter-spacing: -0.02em; font-weight: 800 !important; }}

/* Top bar. On a phone it moves to the bottom, like an app. */
[class*="st-key-topbar"] {{ align-items: center; gap: 0.35rem; margin-bottom: 0.9rem; }}
[class*="st-key-topbar"] [data-testid="stPageLink"] a {{ border-radius: 999px; padding: 0.3rem 0.85rem; }}
[class*="st-key-topbar"] [data-testid="stPageLink"] a[aria-current="page"],
[class*="st-key-topbar"] [data-testid="stPageLink-NavLink"][aria-current="page"] {{ background: {INK}; }}
[class*="st-key-topbar"] a[aria-current="page"] * {{ color: #FFFFFF !important; }}
.logo {{ font-family: "Bricolage Grotesque", sans-serif; font-weight: 800; font-size: 1.7rem; letter-spacing: -0.04em;
  background: {SUN}; border: 2.5px solid {INK}; border-radius: 10px 10px 10px 2px; padding: 0 0.6rem; transform: rotate(-3deg);
  display: inline-block; box-shadow: 3px 3px 0 {INK}; margin-right: 0.8rem; color: {INK}; line-height: 1.35; }}

/* Stickers */
[class*="st-key-tile"] {{ border: 2.5px solid {INK}; border-radius: 22px; box-shadow: 5px 5px 0 {INK}; padding: 1.1rem 1.2rem; background: #FFFFFF; }}
.st-key-tile_sun {{ background: {SUN}; }} .st-key-tile_pink {{ background: {PINK}; }} .st-key-tile_mint {{ background: {MINT}; }}

.hero {{ position: relative; background: {GRAPE}; color: #FFFFFF; border: 2.5px solid {INK}; border-radius: 28px; box-shadow: 7px 7px 0 {INK};
  padding: 1.5rem 1.8rem 1.6rem; margin: 0.4rem 0 1.1rem; overflow: hidden; }}
.hero .kicker {{ font-size: 1.1rem; font-weight: 600; }}
.hero .big {{ font-family: "Bricolage Grotesque", sans-serif; font-weight: 800; letter-spacing: -0.045em;
  font-size: clamp(3.4rem, 8.5vw, 6.2rem); line-height: 1; margin: 0.15rem 0 0.5rem; }}
.hero .line {{ font-size: 1.15rem; max-width: 34em; }}
.hero .sticker {{ position: absolute; top: 1.3rem; right: 1.6rem; transform: rotate(5deg); background: {SUN}; color: {INK};
  border: 2.5px solid {INK}; border-radius: 14px; padding: 0.35rem 0.8rem; font-weight: 800; box-shadow: 3px 3px 0 {INK}; }}
.hero .sticker.down {{ background: {PINK}; }} .hero .sticker.up {{ background: {MINT}; }}

.stat .name {{ font-weight: 700; }}
.stat .value {{ font-family: "Bricolage Grotesque", sans-serif; font-weight: 800; font-size: clamp(1.7rem, 4vw, 2.5rem); letter-spacing: -0.03em; line-height: 1.1; overflow-wrap: anywhere; }}
.stat .note {{ font-size: 0.9rem; }}

.stButton button, .stFormSubmitButton button {{ border: 2px solid {INK}; border-radius: 14px; font-weight: 700; box-shadow: 3px 3px 0 {INK}; transition: transform .08s, box-shadow .08s; }}
.stButton button:hover, .stFormSubmitButton button:hover {{ transform: translate(1px, 1px); box-shadow: 2px 2px 0 {INK}; }}
.stButton button:active {{ transform: translate(3px, 3px); box-shadow: none; }}
[data-testid="stTextInputRootElement"], [data-testid="stTextAreaRootElement"], [data-testid="stNumberInputContainer"],
[data-testid="stDateInput"] [role="group"], div:has(> input[role="combobox"]) {{ background: {LILAC} !important; border: 1.5px solid {INK} !important; border-radius: 12px; }}
[data-testid="InputInstructions"] {{ display: none; }}
[data-testid="stNumberInputContainer"] div:has(> input) {{ background: transparent !important; border: 0 !important; }}
[data-testid="stExpander"] {{ border: 2px solid {INK}; border-radius: 16px; background: #FFFFFF; }}
[data-testid="stForm"] {{ border: 2px solid {INK}; border-radius: 18px; background: #FFFFFF; }}
[data-testid="stChatInput"] {{ border: 2.5px solid {INK}; border-radius: 18px; box-shadow: 4px 4px 0 {INK}; }}
[data-testid="stChatInput"] > div {{ border-radius: 16px; }}

.signal {{ display: flex; gap: 0.55rem; padding: 0.5rem 0; }}
.signal .icon {{ font-family: "Material Symbols Rounded"; font-size: 1.35rem; line-height: 1.25; }}
.signal b {{ display: block; font-weight: 700; line-height: 1.25; }}
.signal span.detail {{ color: {MUTED}; font-size: 0.92rem; line-height: 1.35; display: block; }}

.pl, .pl tr, .pl th, .pl td {{ border-left: 0 !important; border-right: 0 !important; background: transparent !important; }}
.pl {{ width: 100%; border-collapse: collapse; font-variant-numeric: tabular-nums; }}
.pl th {{ border-top: 0 !important; text-align: right; font-weight: 600; color: {MUTED}; font-size: 0.85rem; padding: 0 0 0.35rem !important; }}
.pl td {{ text-align: right; padding: 0.4rem 0 !important; border-top: 1px solid {GRID}; }}
.pl th:first-child, .pl td:first-child {{ text-align: left; }}
.pl tr.total td {{ font-weight: 800; border-top: 2px solid {INK}; }}

@media (prefers-reduced-motion: reduce) {{ .stButton button {{ transition: none; }} }}
@media (max-width: 640px) {{
  .block-container {{ padding: 1rem 1rem 7rem; }}
  .logo {{ display: none; }}
  [class*="st-key-topbar"] {{ position: fixed; left: 0; right: 0; bottom: 0; z-index: 999; margin: 0; padding: 0.35rem 0.3rem;
    background: #FFFFFF; border-top: 2.5px solid {INK}; justify-content: space-around; flex-wrap: nowrap; }}
  [class*="st-key-topbar"] [data-testid="stPageLink"] a {{ padding: 0.25rem 0.5rem; }}
  [data-testid="stBottom"] {{ bottom: 3.4rem; }}
  .hero {{ padding: 1.2rem 1.2rem 1.3rem; border-radius: 22px; }}
  .hero .sticker {{ position: static; display: inline-block; margin-bottom: 0.6rem; }}
}}
</style>
"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def logo() -> str:
    return '<span class="logo">Till</span>'


def hero(kicker: str, big: str, line: str, sticker: str | None = None, mood: str = "") -> None:
    tag = f'<div class="sticker {mood}">{escape(sticker)}</div>' if sticker else ""
    st.markdown(f'<div class="hero">{tag}<div class="kicker">{escape(kicker)}</div><div class="big">{escape(big)}</div>'
                f'<div class="line">{escape(line)}</div></div>', unsafe_allow_html=True)


def stat(column, colour: str, name: str, value: str, note: str) -> None:
    with column.container(key=f"tile_{colour}"):
        st.markdown(f'<div class="stat"><div class="name">{escape(name)}</div><div class="value">{escape(value)}</div>'
                    f'<div class="note">{escape(note)}</div></div>', unsafe_allow_html=True)


def signal_list(items: list[dict]) -> None:
    rows = []
    for s in items:
        colour, icon, label = STATUS[s["severity"]]
        rows.append(f'<div class="signal"><span class="icon" style="color:{colour}" aria-label="{label}">{icon}</span><div>'
                    f'<b>{escape(s["title"])}</b><span class="detail">{escape(s["detail"])}</span></div></div>')
    st.markdown("".join(rows), unsafe_allow_html=True)


def number_colour(value: float | None) -> str:
    if value is None or abs(value) < 0.5:
        return FLAT
    return GOOD if value > 0 else BAD


def pl_table(w: dict, currency: str) -> None:
    c, p = w["current"], w["prior"]
    lines = [("Money in", "revenue", 1, False), ("What your items cost", "cogs", -1, False),
             ("Bills and other costs", "operating_expenses", -1, False), ("What you kept", "net_profit", 1, True)]
    head = f"<tr><th>{escape(currency)}</th><th>This period</th>" + ("<th>Before</th>" if p else "") + "</tr>"
    rows = []
    for label, key, sign, total in lines:
        style = f' style="color:{number_colour(c[key])}"' if total else ""
        cells = f"<td>{label}</td><td{style}>{sign * c[key]:,.0f}</td>"
        if p:
            style = f' style="color:{number_colour(p[key])}"' if total else ""
            cells += f"<td{style}>{sign * p[key]:,.0f}</td>"
        rows.append(f'<tr class="{"total" if total else ""}">{cells}</tr>')
    st.markdown(f'<table class="pl">{head}{"".join(rows)}</table>', unsafe_allow_html=True)


def _layout(fig: go.Figure, height: int, legend: bool = False) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=0, r=8, t=8, b=0), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                      font=dict(family="Figtree, sans-serif", color=MUTED, size=13), showlegend=legend,
                      legend=dict(orientation="h", y=1.12, x=0), hoverlabel=dict(bgcolor="#FFFFFF", font_color=INK), bargap=0.3)
    fig.update_xaxes(showgrid=False, linecolor=GRID, tickcolor="rgba(0,0,0,0)")
    fig.update_yaxes(gridcolor=GRID, zeroline=True, zerolinecolor=MUTED, tickformat="~s")
    return fig


def show(fig: go.Figure) -> None:
    st.plotly_chart(fig, config={"displayModeBar": False}, width="stretch")


def months_chart(months: pd.DataFrame, currency: str) -> go.Figure:
    months = months.tail(8)
    opacity = [0.4 if p else 1 for p in months["partial"]]
    full = months[~months["partial"]]
    fig = go.Figure()
    fig.add_bar(x=months["label"], y=months["revenue"], name="Money in", marker=dict(color=GRAPE, opacity=opacity, cornerradius=6),
                hovertemplate=f"%{{x}}<br>Money in {currency} %{{y:,.0f}}<extra></extra>")
    fig.add_scatter(x=full["label"], y=full["net_profit"], name="You kept", mode="lines+markers", line=dict(color=ORANGE, width=3),
                    marker=dict(size=9, line=dict(color="#FFFFFF", width=2)),
                    hovertemplate=f"%{{x}}<br>You kept {currency} %{{y:,.0f}}<extra></extra>")
    fig.update_xaxes(categoryorder="array", categoryarray=months["label"].tolist())
    return _layout(fig, 270, legend=True)


def bars(labels: list[str], values: list[float], currency: str, text: list[str] | None = None) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(y=labels, x=values, orientation="h", marker=dict(color=GRAPE, cornerradius=6), text=text, textposition="outside",
                cliponaxis=False, hovertemplate=f"%{{y}}<br>{currency} %{{x:,.0f}}<extra></extra>")
    fig = _layout(fig, max(180, 38 * len(labels) + 30))
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)", zerolinecolor=GRID, tickformat="")
    fig.update_xaxes(visible=False, range=[0, max(values) * 1.4])
    return fig


def weekday_chart(frame: pd.DataFrame, currency: str) -> go.Figure:
    fig = go.Figure()
    fig.add_bar(x=frame["day"], y=frame["average"], marker=dict(color=GRAPE, cornerradius=6),
                hovertemplate=f"%{{x}}<br>Average {currency} %{{y:,.0f}}<extra></extra>")
    return _layout(fig, 220)
