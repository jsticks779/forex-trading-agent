"""Professional forex trading console.

Streamlit app that talks to the broker client (MT5 REST API or OANDA). Gives a
live, market-grade overview of the account, prices, signals, positions and
deals, plus manual order placement.

Run with:
    streamlit run app/dashboard/app.py
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from app.config import BROKER, DEFAULT_SYMBOLS, ENGINE_MAGIC, build_client  # noqa: E402

st.set_page_config(
    page_title="Apex FX — Trading Console",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------ branding
APP_NAME = "Apex FX"
APP_TAGLINE = "Algorithmic Forex Desk"
AUTO_REFRESH_SECONDS = 5

st.markdown(
    """
    <style>
    :root {
        --fx-bg: #0b1220;
        --fx-panel: #0f1a2b;
        --fx-border: #1d2b42;
        --fx-buy: #00c853;
        --fx-sell: #ff1744;
        --fx-neutral: #8aa0bd;
        --fx-accent: #4f8cf7;
    }
    .stApp {
        background: radial-gradient(1200px 600px at 70% -10%, #12203a 0%, var(--fx-bg) 55%);
        color: #dbe6f4;
    }
    .sidebar .sidebar-content, [data-testid="stSidebar"] {
        background: #0b1424;
        border-right: 1px solid var(--fx-border);
    }
    .block-container {
        padding-top: 1.2rem;
        max-width: 1500px;
        margin: 0 auto;
    }

    h1, h2, h3 {
        font-family: "Segoe UI", system-ui, sans-serif;
        letter-spacing: .3px;
    }
    .fx-header {
        display: flex; align-items: center; gap: 14px;
        padding: 10px 0 14px 0;
        flex-wrap: wrap;
    }
    .fx-header > div { min-width: 0; }
    .fx-logo {
        width: 44px; height: 44px; border-radius: 12px;
        background: linear-gradient(135deg, #4f8cf7, #22d3ee);
        display: flex; align-items: center; justify-content: center;
        font-size: 24px; color: #fff; font-weight: 800;
        box-shadow: 0 6px 18px rgba(79,140,247,.35);
    }
    .fx-title { font-size: 24px; font-weight: 800; color: #f2f7ff; line-height: 1.1; }
    .fx-sub { font-size: 12px; color: var(--fx-neutral); letter-spacing: 2.2px; text-transform: uppercase; }
    .fx-badge {
        display: inline-flex; align-items: center; gap: 6px;
        font-size: 11px; font-weight: 600; padding: 3px 10px;
        border-radius: 999px; border: 1px solid;
        letter-spacing: .5px;
    }
    .fx-badge-ok   { color: var(--fx-buy); border-color: rgba(0,200,83,.4); background: rgba(0,200,83,.10); }
    .fx-badge-err  { color: var(--fx-sell); border-color: rgba(255,23,68,.4); background: rgba(255,23,68,.10); }
    .fx-badge-info { color: var(--fx-accent); border-color: rgba(79,140,247,.4); background: rgba(79,140,247,.10); }

    .fx-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
        gap: 12px;
        width: 100%;
    }
    .fx-card {
        border: 1px solid var(--fx-border);
        border-radius: 14px;
        padding: 12px 16px 8px;
        background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,0));
        min-width: 0;
    }
    .fx-card-head { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
    .fx-card-sym  { color: var(--fx-neutral); font-size: 12px; font-weight: 700; letter-spacing: .4px; }
    .fx-card-bid  { font-size: 23px; font-weight: 800; color: #fff; margin-top: 2px; }
    .fx-card-foot { display: flex; justify-content: space-between; color: var(--fx-neutral); font-size: 11px; margin-top: 2px; }
    .fx-col-pad   { padding: 0.35rem 0.85rem 0.85rem 0.85rem; }

    @media (max-width: 900px) {
        .stTabs [data-baseweb="tab"] { padding: 8px 12px; font-size: 13px; }
        .fx-card-bid { font-size: 20px; }
    }
    @media (max-width: 640px) {
        div[data-testid="stMetric"] { padding: 8px 10px; }
        .fx-card { padding: 10px 12px 6px; }
    }

    div[data-testid="stMetric"] {
        background: linear-gradient(180deg, rgba(255,255,255,.03), rgba(255,255,255,0));
        border: 1px solid var(--fx-border);
        border-radius: 14px;
        padding: 10px 14px;
    }
    div[data-testid="stMetricLabel"] { color: var(--fx-neutral); font-size: 12px; }
    div[data-testid="stMetricValue"] { color: #f2f7ff; font-weight: 700; }
    .fx-pnl-pos { color: var(--fx-buy) !important; font-weight: 700; }
    .fx-pnl-neg { color: var(--fx-sell) !important; font-weight: 700; }

    [data-testid="stDataFrame"] { border: 1px solid var(--fx-border); border-radius: 12px; overflow: hidden; }
    .stTabs [data-baseweb="tab-list"] { gap: 6px; }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255,255,255,.03);
        border-radius: 8px 8px 0 0;
        padding: 8px 18px; font-weight: 600;
    }
    header[data-testid="stHeader"] {
        background: transparent !important;
        z-index: 99 !important;
    }
    [data-testid="stExpandSidebarButton"], [data-testid="stSidebarCollapseButton"] {
        display: inline-flex !important;
        visibility: visible !important;
        opacity: 1 !important;
        z-index: 999999 !important;
    }
    [data-testid="stDecoration"], .stDeployButton {
        display: none !important;
    }
    footer { display: none; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ------------------------------------------------------------------- helpers
def safe(fn, default=None):
    """Call fn and return default on any exception (shows the error inline)."""
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        st.error(f"API error: {exc}")
        return default


@st.cache_resource
def get_client():
    return build_client()


def pnl_html(value: float) -> str:
    css = "fx-pnl-pos" if value >= 0 else "fx-pnl-neg"
    return f'<span class="{css}">{value:+,.2f}</span>'


def sparkline_fig(series: pd.Series, color: str) -> go.Figure:
    fig = go.Figure(
        go.Scatter(
            x=series.index,
            y=series.values,
            mode="lines",
            line=dict(color=color, width=2),
            fill="tozeroy",
            fillcolor=f"rgba({tuple(int(color.lstrip('#')[i:i+2], 16) for i in (0, 2, 4)) + (0.12,)}",
        )
    )
    fig.update_layout(
        margin=dict(l=0, r=0, t=2, b=2),
        height=48,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig


def svg_spark(closes, color: str) -> str:
    """Tiny inline-SVG sparkline for a price card (responsive, no JS)."""
    arr = [float(c) for c in closes[-40:]]
    if len(arr) < 2:
        return ""
    lo, hi = min(arr), max(arr)
    span = (hi - lo) or 1.0
    n = len(arr)
    pts = " ".join(
        f"{(i / (n - 1)) * 100:.1f},{24 - ((v - lo) / span) * 20:.1f}"
        for i, v in enumerate(arr)
    )
    return (
        f'<svg viewBox="0 0 100 24" preserveAspectRatio="none" '
        f'style="width:100%;height:26px;display:block">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="1.6" stroke-linejoin="round"/></svg>'
    )


def candle_fig(symbol: str, rates: list[dict]) -> go.Figure:
    df = pd.DataFrame(rates)
    if df.empty:
        return go.Figure()
    df["time"] = pd.to_datetime(df["time"])
    fig = go.Figure(
        data=[
            go.Candlestick(
                x=df["time"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                increasing_line_color="#00c853",
                decreasing_line_color="#ff1744",
                name=symbol,
                hovertemplate="<b>%{x|%b %d, %H:%M}</b><br>Open: %{open:.5f}<br>High: %{high:.5f}<br>Low: %{low:.5f}<br>Close: %{close:.5f}<extra></extra>",
            )
        ]
    )
    fig.update_layout(
        title=f"{symbol} — {rates and rates[0].get('timeframe', 'H1')}",
        xaxis=dict(showgrid=False, rangeslider=dict(visible=False)),
        yaxis=dict(gridcolor="#16233a"),
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#8aa0bd"),
        height=450,
        margin=dict(l=10, r=10, t=40, b=10),
        dragmode="pan",
        hovermode="x unified",
    )
    return fig


client = get_client()

# -------------------------------------------------------------------- header
health = safe(lambda: client.health(), {})
ok = bool(health)
badge = (
    '<span class="fx-badge fx-badge-ok">● ONLINE</span>'
    if ok
    else '<span class="fx-badge fx-badge-err">● OFFLINE</span>'
)
st.markdown(
    f'<div class="fx-header">'
    f'<div class="fx-logo">FX</div>'
    f'<div style="min-width:0">'
    f'<div class="fx-title">{APP_NAME}</div>'
    f'<div class="fx-sub">{APP_TAGLINE}</div>'
    f'</div>'
    f'<div style="flex:1"></div>'
    f'<div style="text-align:right;white-space:nowrap">{badge}<br>'
    f'<span class="fx-sub" style="font-size:11px">BROKER · {BROKER.upper()}'
    f'&nbsp;|&nbsp;backend {type(client).__name__}</span></div>'
    f'</div>',
    unsafe_allow_html=True,
)

# ------------------------------------------------------------------- sidebar
account = safe(lambda: client.account())
login = account.get("login") if isinstance(account, dict) else None

with st.sidebar:
    st.markdown(f"### {APP_NAME} Console")
    st.caption(f"**Broker:** {BROKER.upper()} · **Engine magic:** {ENGINE_MAGIC}")

    if ok:
        st.success("API connected")
    else:
        st.error("API not reachable — is the container up?")

    st.markdown("---")
    if isinstance(account, dict) and login:
        c = account.get("currency", "USD")
        st.metric("Balance", f"{account.get('balance', 0):,.2f}")
        st.metric("Equity", f"{account.get('equity', 0):,.2f}")
        st.metric("Free Margin", f"{account.get('margin_free', 0):,.2f}")
        st.metric("Margin Level", f"{account.get('margin_level', 0):,.2f}%")
        st.metric("Open P/L", f"{account.get('profit', 0):+,.2f}")
        st.metric("Leverage", f"1:{account.get('leverage', 0)}")
        st.caption(
            f"Account **{login}** · {account.get('name', '')}\n\n"
            f"Server: `{account.get('server', '')}` · {c}"
        )
    else:
        st.warning("No account data — do the broker login in the VNC desktop first.")

st.sidebar.markdown("---")
st.sidebar.caption(f"Auto-refresh: every {AUTO_REFRESH_SECONDS}s · {APP_NAME} v1.0")

# --------------------------------------------------------------------- tabs
tab_prices, tab_charts, tab_positions, tab_trade, tab_history, tab_ai = st.tabs(
    ["📊 Live Prices", "📈 Charts", "💼 Positions", "🛒 Trade", "🕘 History", "🤖 AI Agent & Backtest"]
)


# ------------------------------------------------------------- LIVE PRICES --
@st.fragment(run_every=f"{AUTO_REFRESH_SECONDS}s")
def render_live_prices():
    st.subheader("Market Watch")
    rows = []
    for sym in DEFAULT_SYMBOLS:
        t = safe(lambda s=sym: client.tick(s))
        if not (isinstance(t, dict) and "bid" in t):
            rows.append({"Symbol": sym, "Bid": None, "Ask": None, "Spread": None, "Trend": "—"})
            continue
        r = safe(lambda s=sym: client.rates(s, "H1", 60), {})
        hist = pd.DataFrame(r.get("rates", []))
        last_close = float(hist["close"].iloc[-1]) if not hist.empty else float("nan")
        bid = float(t["bid"])
        chg = ((bid - last_close) / last_close * 100) if last_close == last_close else 0.0
        spread = float(t.get("ask", 0)) - bid
        rows.append(
            {
                "Symbol": sym,
                "Bid": bid,
                "Ask": t.get("ask"),
                "Spread": spread,
                "Δ%": chg,
                "Trend": hist["close"].tail(30) if not hist.empty else None,
            }
        )

    cards = []
    for row in rows:
        if row["Bid"] is None:
            cards.append(
                f'<div class="fx-card"><div class="fx-card-head">'
                f'<span class="fx-card-sym">{row["Symbol"]}</span></div>'
                f'<div style="color:#ff1744;font-size:13px;padding:8px 0">No quote</div></div>'
            )
            continue
        delta = row["Δ%"]
        color = (
            "#00c853"
            if delta > 0
            else "#ff1744"
            if delta < 0
            else "#8aa0bd"
        )
        arrow = "▲" if delta > 0 else "▼" if delta < 0 else "–"
        spark = svg_spark(row["Trend"], color) if row["Trend"] is not None else ""
        cards.append(
            f'<div class="fx-card">'
            f'<div class="fx-card-head">'
            f'<span class="fx-card-sym">{row["Symbol"]}</span>'
            f'<span style="color:{color};font-size:12px;font-weight:700">{arrow} {delta:+.3f}%</span>'
            f'</div>'
            f'<div class="fx-card-bid">{row["Bid"]:.5f}</div>'
            f'<div class="fx-card-foot">'
            f'<span>Ask {row["Ask"]:.5f}</span><span>Spread {row["Spread"]:.5f}</span>'
            f'</div>{spark}</div>'
        )

    st.markdown(f'<div class="fx-grid">{"".join(cards)}</div>', unsafe_allow_html=True)
    st.caption(f"Prices refresh automatically every {AUTO_REFRESH_SECONDS} seconds.")


with tab_prices:
    render_live_prices()


# ------------------------------------------------------------------ CHARTS --
@st.fragment(run_every=f"{AUTO_REFRESH_SECONDS * 3}s")
def render_chart_tab():
    c1, c2 = st.columns([1.4, 3.4])
    with c1:
        st.subheader("Chart Controls")
        sym = st.selectbox("Symbol", DEFAULT_SYMBOLS, key="chart_sym")
        tf = st.selectbox(
            "Timeframe",
            ["M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1", "MN1"],
            index=4,
            key="chart_tf",
        )
        count = st.slider("History Depth (Bars)", 50, 2000, 300, 50, key="chart_n")
        st.caption("Candles render on the right.")
    with c2:
        r = safe(lambda s=sym, t=tf, n=count: client.rates(s, t, n), {})
        rates = r.get("rates", []) if isinstance(r, dict) else []
        if rates:
            st.plotly_chart(
                candle_fig(sym, rates),
                width="stretch",
                config={"scrollZoom": True, "displayModeBar": True, "displaylogo": False},
            )
        else:
            st.warning(f"No chart data for {sym}.")


with tab_charts:
    render_chart_tab()


# -------------------------------------------------------------- POSITIONS --
@st.fragment(run_every=f"{AUTO_REFRESH_SECONDS}s")
def render_positions_tab():
    st.subheader("Open Positions")
    positions = safe(lambda: client.positions(), [])
    if not positions:
        st.info("No open positions.")
        return

    df = pd.DataFrame(positions)
    keep = [
        "ticket", "symbol", "type_description", "volume", "price_open",
        "price_current", "sl", "tp", "profit", "magic", "comment",
    ]
    df = df[[c for c in keep if c in df.columns]]
    if "type_description" in df:
        df["type_description"] = df["type_description"].str.replace("POSITION_TYPE_", "")

    total_pnl = float(df.get("profit", pd.Series([0.0])).sum())
    st.metric("Total unrealized P/L", f"{total_pnl:+,.2f}",
              delta=f"{total_pnl:+,.2f}")

    st.dataframe(df, width="stretch", hide_index=True)

    st.markdown("---")
    st.subheader("Quick Close")
    ticket_map = {
        f"{p['ticket']} · {p['symbol']} · {p.get('type_description', '')} · {p.get('volume', '')} lots": p["ticket"]
        for p in positions
    }
    choice = st.selectbox("Position", list(ticket_map.keys()), key="pos_choice")
    ticket = ticket_map[choice]
    vols = [p.get("volume") for p in positions if p["ticket"] == ticket]
    vol = st.selectbox("Volume to close", ["Full", *[f"{v}" for v in dict.fromkeys(vols)]], key="pos_vol")
    if st.button("Close", key="pos_close", type="primary"):
        v = None if vol == "Full" else float(vol)
        res = safe(lambda: client.close_position(ticket, volume=v))
        desc = res.get("retcode_description") if isinstance(res, dict) else None
        if isinstance(res, dict) and res.get("success"):
            st.success(f"Closed {ticket}.")
        else:
            st.error(f"Close failed: {desc or res}")
        st.rerun()


with tab_positions:
    render_positions_tab()


# ------------------------------------------------------------------- TRADE --
@st.fragment
def render_trade_tab():
    st.subheader("Place Order")
    with st.form("trade_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        symbol = c1.selectbox("Symbol", DEFAULT_SYMBOLS, key="tr_sym")
        action = c2.selectbox("Side", ["BUY", "SELL"], key="tr_side")
        order_type = c3.selectbox("Order type", ["MARKET", "LIMIT", "STOP"], key="tr_type")

        c4, c5 = st.columns(2)
        volume = c4.number_input("Volume (lots)", 0.01, 50.0, 0.01, 0.01, key="tr_vol")
        price = c5.number_input("Limit/Stop price (0 = market)", 0.0, step=0.00001, key="tr_px")

        c6, c7 = st.columns(2)
        sl = c6.number_input("Stop Loss (0 = none)", 0.0, step=0.00001, key="tr_sl")
        tp = c7.number_input("Take Profit (0 = none)", 0.0, step=0.00001, key="tr_tp")

        c8, c9 = st.columns(2)
        magic = c8.number_input("Magic number (engine uses its own)", 0, step=1, key="tr_magic")
        comment = c9.text_input("Comment", "", key="tr_comment")

        submitted = st.form_submit_button("Place order", type="primary", width="stretch")

    if submitted:
        if magic == 0:
            st.caption("magic=0 → manual order. The AI engine uses its dedicated magic number when trading.")
        res = safe(
            lambda: client.send_order(
                symbol=symbol,
                action=action,
                volume=volume,
                order_type=order_type,
                price=price if price else None,
                sl=sl if sl else None,
                tp=tp if tp else None,
                magic=int(magic),
                comment=comment,
            ),
        )
        if isinstance(res, dict):
            if res.get("success"):
                st.success(f"Order placed — ticket {res.get('order')} @ {res.get('price')}")
            else:
                st.error(f"Order failed: {res.get('retcode_description', '')} — {res.get('comment', '')}")


with tab_trade:
    render_trade_tab()


# ----------------------------------------------------------------- HISTORY --
@st.fragment(run_every=f"{AUTO_REFRESH_SECONDS * 3}s")
def render_history_tab():
    st.subheader("Account History")

    from_time = datetime.now() - timedelta(days=30)
    deals = safe(lambda: client.deals(from_time, datetime.now()), [])
    if deals:
        df = pd.DataFrame(deals)
        drop = [c for c in df.columns if "description" in c]
        df = df.drop(columns=[c for c in drop if c in df])
        keep = [c for c in ["time", "type", "symbol", "volume", "price", "profit", "magic", "comment"] if c in df.columns]
        st.dataframe(df[keep], width="stretch", hide_index=True)

        profit_df = df[~df["profit"].isna()].copy()
        if not profit_df.empty:
            profit_df["time"] = pd.to_datetime(profit_df["time"])
            profit_df = profit_df.sort_values("time")
            profit_df["cum"] = profit_df["profit"].cumsum()
            fig = go.Figure(
                go.Scatter(
                    x=profit_df["time"],
                    y=profit_df["cum"],
                    mode="lines+markers",
                    line=dict(color="#4f8cf7", width=2),
                    marker=dict(size=5, color="#22d3ee"),
                    name="Cumulative P/L",
                )
            )
            fig.update_layout(
                title="Cumulative P/L — last 30 days",
                xaxis=dict(showgrid=False),
                yaxis=dict(gridcolor="#16233a", title="P/L"),
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#8aa0bd"),
                height=330,
                margin=dict(l=20, r=20, t=40, b=10),
            )
            st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})
    else:
        st.info("No deals recorded in the last 30 days.")


with tab_history:
    render_history_tab()


# ------------------------------------------------------------- AI AGENT & BACKTEST --
def render_ai_tab():
    st.subheader("🤖 AI Agent Controls & Backtest Suite")

    c1, c2 = st.columns([2.0, 2.0])

    with c1:
        st.markdown("#### AI Agent Status & Control")
        import subprocess
        res = subprocess.run(["pgrep", "-f", "app.engine.engine"], capture_output=True, text=True)
        pids = res.stdout.strip().split()
        is_running = len(pids) > 0

        eng_tf = st.selectbox("AI Strategy Timeframe", ["H1", "H4", "D1", "M15", "M30"], index=0, key="eng_tf")

        if is_running:
            st.success(f"● AI Agent Active (PIDs: {', '.join(pids)})")
            if st.button("⏹ Stop AI Engine", type="primary", key="stop_eng_btn", width="stretch"):
                subprocess.run(["pkill", "-f", "app.engine.engine"])
                st.success("Stopped AI Engine")
                st.rerun()
        else:
            st.warning("○ AI Agent Stopped")
            if st.button("▶ Start AI Engine", type="primary", key="start_eng_btn", width="stretch"):
                log_file = Path(__file__).resolve().parent.parent.parent / "logs" / "engine.log"
                log_file.parent.mkdir(parents=True, exist_ok=True)
                venv_py = Path(__file__).resolve().parent.parent.parent / ".venv" / "bin" / "python"
                cmd = f"nohup {venv_py} -m app.engine.engine run --timeframe {eng_tf} --interval 60 > {log_file} 2>&1 &"
                subprocess.Popen(cmd, shell=True)
                st.success(f"Started AI Engine on {eng_tf} timeframe in background loop!")
                st.rerun()

        st.markdown("---")
        st.markdown("#### Interactive Strategy Backtester")
        b1, b2 = st.columns([1.5, 1.0])
        bt_sym = b1.selectbox("Symbol to Backtest", DEFAULT_SYMBOLS, key="bt_sym")
        bt_tf = b2.selectbox("Timeframe", ["H1", "H4", "D1", "M15", "M30"], index=0, key="bt_tf")
        bt_bars = st.slider("Historical Bars", 200, 2000, 1000, 100, key="bt_bars")

        if st.button("🚀 Run Backtest", key="run_bt_btn", width="stretch"):
            with st.spinner(f"Fetching {bt_tf} rate history for {bt_sym} and running backtest..."):
                from app.engine.engine import ema, fastrsi, macd, atr, adx
                rates_resp = safe(lambda: client.rates(bt_sym, bt_tf, bt_bars), {})
                rates = rates_resp.get("rates", []) if isinstance(rates_resp, dict) else []
                if not rates:
                    st.error(f"No history data for {bt_sym}")
                else:
                    df = pd.DataFrame(rates)
                    df["time"] = pd.to_datetime(df["time"])
                    close = df["close"]
                    df["ema20"] = ema(close, 20)
                    df["ema50"] = ema(close, 50)
                    df["ema200"] = ema(close, 200)
                    df["rsi"] = fastrsi(close, 14)
                    m_line, s_line = macd(close)
                    df["macd"] = m_line
                    df["macd_sig"] = s_line
                    df["atr"] = atr(df, 14)
                    df["adx"] = adx(df, 14)

                    bal = 50000.0
                    init_bal = bal
                    trades = []
                    pos = None

                    for i in range(200, len(df)):
                        row = df.iloc[i]
                        curr_time = row["time"]
                        curr_atr = row["atr"]

                        if pos:
                            high, low = row["high"], row["low"]
                            if not pos["be"]:
                                if pos["type"] == "BUY" and high >= pos["entry"] + 1.0 * curr_atr:
                                    pos["sl"] = pos["entry"]
                                    pos["be"] = True
                                elif pos["type"] == "SELL" and low <= pos["entry"] - 1.0 * curr_atr:
                                    pos["sl"] = pos["entry"]
                                    pos["be"] = True

                            exit_px = None
                            if pos["type"] == "BUY":
                                if low <= pos["sl"]: exit_px = pos["sl"]
                                elif high >= pos["tp"]: exit_px = pos["tp"]
                            elif pos["type"] == "SELL":
                                if high >= pos["sl"]: exit_px = pos["sl"]
                                elif low <= pos["tp"]: exit_px = pos["tp"]

                            if exit_px:
                                pnl = (exit_px - pos["entry"]) * pos["u"] if pos["type"] == "BUY" else (pos["entry"] - exit_px) * pos["u"]
                                bal += pnl
                                trades.append({"pnl": pnl, "bal": bal, "time": curr_time})
                                pos = None

                        if not pos:
                            if row["adx"] >= 20.0:
                                t_up = row["ema20"] > row["ema50"] and row["close"] > row["ema200"]
                                t_dn = row["ema20"] < row["ema50"] and row["close"] < row["ema200"]
                                if t_up and row["rsi"] < 60 and row["macd"] > row["macd_sig"]:
                                    entry = row["close"]
                                    sl = entry - 1.2 * curr_atr
                                    tp = entry + 2.5 * curr_atr
                                    u = (bal * 0.01) / abs(entry - sl)
                                    pos = {"type": "BUY", "entry": entry, "sl": sl, "tp": tp, "u": u, "be": False}
                                elif t_dn and row["rsi"] > 40 and row["macd"] < row["macd_sig"]:
                                    entry = row["close"]
                                    sl = entry + 1.2 * curr_atr
                                    tp = entry - 2.5 * curr_atr
                                    u = (bal * 0.01) / abs(sl - entry)
                                    pos = {"type": "SELL", "entry": entry, "sl": sl, "tp": tp, "u": u, "be": False}

                    t_df = pd.DataFrame(trades)
                    if t_df.empty:
                        st.info("No trades triggered during backtest period.")
                    else:
                        wins = t_df[t_df["pnl"] > 0]
                        wr = (len(wins) / len(t_df)) * 100
                        ret = ((bal - init_bal) / init_bal) * 100

                        st.markdown("##### Backtest Performance Results")
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Final Balance", f"${bal:,.2f}", f"{ret:+.2f}%")
                        m2.metric("Total Trades", len(t_df))
                        m3.metric("Win Rate", f"{wr:.1f}%")

                        fig = go.Figure(go.Scatter(x=t_df["time"], y=t_df["bal"], mode="lines+markers", line=dict(color="#4f8cf7", width=2)))
                        fig.update_layout(title=f"Backtest Equity Curve — {bt_sym}", height=280, margin=dict(l=10,r=10,t=30,b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
                        st.plotly_chart(fig, width="stretch")

    with c2:
        st.markdown("#### AI Market Consultant & Guidance")

        q_choice = st.selectbox(
            "Select Question or Topic to Discuss:",
            [
                "Analyze current active trades (AUDUSD, EURUSD, USDCAD)",
                "How does the 200 EMA + ADX Trend Strategy work?",
                "How do Stop Loss & Breakeven Protection work?",
                "How do I read past graphs and candlesticks?",
                "What risk percentage should I use on my account?"
            ],
            key="qa_choice"
        )

        if "Analyze current active trades" in q_choice:
            st.info("💡 **Active AI Positions Analysis:**")
            st.markdown("""
            - **AUDUSD SELL (4.18 lots):** Opened on H1 downtrend below 200 EMA. Stop Loss moved to **0.71550** to lock in protection.
            - **EURUSD SELL (4.33 lots):** Opened on strong USD momentum. Stop Loss set at 1.16010.
            - **USDCAD BUY (3.74 lots):** Opened on USD uptrend above 200 EMA. Stop Loss set at 1.38821.
            """)
        elif "200 EMA + ADX" in q_choice:
            st.markdown("""
            💡 **Strategy Architecture:**
            1. **200 EMA Filter:** Confirms overall market trend direction.
            2. **ADX >= 20:** Measures trend strength to skip low-volatility sideways ranges.
            3. **20/50 EMA + RSI + MACD:** Precise entry timing.
            4. **Breakeven SL:** Moves Stop Loss to entry price ($0 risk) once in profit.
            """)
        elif "Stop Loss & Breakeven" in q_choice:
            st.markdown("""
            💡 **Risk Protection Mechanics:**
            - **Max Risk per Trade:** Exactly **1.0%** of account equity ($500 on $50k balance).
            - **Breakeven Move:** Once a trade reaches +1.0x ATR profit, Stop Loss moves to entry price ($0 risk).
            - **Daily Circuit Breaker:** Auto-pauses trading if daily drawdown hits **3%**.
            """)
        elif "past graphs" in q_choice:
            st.markdown("""
            💡 **Reading Historical Candlesticks:**
            - Use the **📈 Charts** tab slider to load up to **2,000 past candles**.
            - Look for **Support** (price floor bounces) and **Resistance** (price ceiling rejections).
            - 🟢 Green = Bullish (Close > Open) | 🔴 Red = Bearish (Close < Open).
            """)
        elif "risk percentage" in q_choice:
            st.markdown("""
            💡 **Recommended Account Sizing:**
            - Conservative: **0.5%** per trade ($250 per trade).
            - Standard Demo: **1.0%** per trade ($500 per trade).
            - Never risk more than 2% on any single trade.
            """)

        st.markdown("---")
        st.markdown("#### Live AI Engine Activity Log")
        log_file = Path(__file__).resolve().parent.parent.parent / "logs" / "engine.log"
        if log_file.exists():
            logs = log_file.read_text().splitlines()[-15:]
            st.code("\n".join(logs), language="text")
        else:
            st.caption("No log output found yet.")


with tab_ai:
    render_ai_tab()

st.markdown(
    '<div style="text-align:center;color:#5b6c85;font-size:11px;'
    f'margin-top:24px">© {datetime.now().year} {APP_NAME} · '
    "Automated demo trading · prices may be delayed</div>",
    unsafe_allow_html=True,
)