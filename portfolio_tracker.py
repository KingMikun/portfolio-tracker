import streamlit as st
import requests
import pandas as pd
from datetime import datetime
import plotly.graph_objects as go

st.set_page_config(page_title="HL Portfolio + Opportunities", layout="wide", page_icon="📊")

HL_INFO_URL = "https://api.hyperliquid.xyz/info"

def hl_post(payload):
    try:
        r = requests.post(HL_INFO_URL, json=payload, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        st.error(f"Hyperliquid API error: {e}")
        return None

@st.cache_data(ttl=60)
def get_hl_perp_positions(address):
    if not address or not address.startswith("0x"):
        return None
    return hl_post({"type": "clearinghouseState", "user": address})

@st.cache_data(ttl=60)
def get_hl_spot_balances(address):
    if not address or not address.startswith("0x"):
        return None
    return hl_post({"type": "spotClearinghouseState", "user": address})

@st.cache_data(ttl=30)
def get_meta_and_ctxs():
    return hl_post({"type": "metaAndAssetCtxs"})

@st.cache_data(ttl=300)
def get_candles(coin, interval="1h", hours=48):
    end = int(datetime.now().timestamp() * 1000)
    start = end - hours * 3600 * 1000
    return hl_post({
        "type": "candleSnapshot",
        "req": {"coin": coin, "interval": interval, "startTime": start, "endTime": end}
    })

def score_opportunity(funding, day_change_pct, volume, oi, mark):
    """Score setups and return bias (Long/Short)."""
    score = 0
    reasons = []
    bias = "Neutral"

    ann_funding = float(funding) * 3 * 365 * 100
    if abs(ann_funding) > 50:
        score += 30
        reasons.append(f"Extreme funding ~{ann_funding:.1f}% ann.")
    elif abs(ann_funding) > 20:
        score += 15
        reasons.append(f"High funding ~{ann_funding:.1f}% ann.")

    if abs(day_change_pct) > 10:
        score += 20
        reasons.append(f"Big 24h move {day_change_pct:+.1f}%")
    elif abs(day_change_pct) > 5:
        score += 10
        reasons.append(f"Solid move {day_change_pct:+.1f}%")

    if float(volume) > 10_000_000:
        score += 15
        reasons.append("High volume")
    elif float(volume) > 1_000_000:
        score += 5

    # Directional bias
    if float(funding) < -0.0001 and day_change_pct > 0:
        score += 25
        reasons.append("Negative funding + upward momentum")
        bias = "Long"
    elif float(funding) > 0.0001 and day_change_pct < 0:
        score += 25
        reasons.append("Positive funding + downward momentum")
        bias = "Short"
    elif float(funding) < -0.00005:
        bias = "Long"
        reasons.append("Negative funding (long bias)")
    elif float(funding) > 0.00005:
        bias = "Short"
        reasons.append("Positive funding (short bias)")

    return score, reasons, bias

# Sidebar
st.sidebar.title("⚙️ Configuration")
hl_address = st.sidebar.text_input(
    "Hyperliquid Wallet Address",
    placeholder="0x...",
    help="Public address only. No private key needed."
)
tracked_crypto = st.sidebar.text_area(
    "Tracked Crypto Tokens (one per line)",
    value="BTC\nETH\nSOL\nHYPE",
    help="Used for fundamentals section"
)

st.title("📊 Hyperliquid Portfolio + Futures Opportunities")
st.caption("Live Hyperliquid perp + spot positions and scanner for high-probability futures setups.")

# === Portfolio ===
st.header("📈 Portfolio Overview")

if not hl_address:
    st.info("Enter your Hyperliquid address in the sidebar to load positions.")
else:
    col1, col2 = st.columns(2)

    # Perp positions
    with col1:
        st.subheader("Perp Positions")
        state = get_hl_perp_positions(hl_address)
        if state and "assetPositions" in state:
            rows = []
            for ap in state["assetPositions"]:
                pos = ap["position"]
                szi = float(pos["szi"])
                if abs(szi) < 1e-8:
                    continue
                rows.append({
                    "Coin": pos["coin"],
                    "Side": "Long" if szi > 0 else "Short",
                    "Size": abs(szi),
                    "Entry": float(pos["entryPx"]),
                    "uPnL": float(pos.get("unrealizedPnl", 0)),
                    "Leverage": pos.get("leverage", {}).get("value", 1),
                    "Notional": abs(float(pos.get("positionValue", 0)))
                })
            if rows:
                df = pd.DataFrame(rows)
                st.dataframe(df.style.format({
                    "Entry": "{:.4f}", "uPnL": "{:.2f}", "Notional": "{:.2f}", "Size": "{:.4f}"
                }), use_container_width=True)
                st.metric("Perp Notional", f"${df['Notional'].sum():,.0f}")
            else:
                st.info("No open perp positions.")

            ms = state.get("marginSummary", {})
            if ms:
                st.metric("Account Value", f"${float(ms.get('accountValue', 0)):,.2f}")
                st.metric("Withdrawable", f"${float(ms.get('withdrawable', 0)):,.2f}")
        else:
            st.warning("Could not fetch perp positions.")

    # Spot balances
    with col2:
        st.subheader("Spot Balances")
        spot = get_hl_spot_balances(hl_address)
        if spot and "balances" in spot:
            spot_rows = []
            for b in spot["balances"]:
                total = float(b.get("total", 0))
                if total <= 0:
                    continue
                spot_rows.append({
                    "Token": b.get("coin", "?"),
                    "Total": total,
                    "Hold": float(b.get("hold", 0)),
                    "Available": total - float(b.get("hold", 0)),
                    "Entry Notional": float(b.get("entryNtl", 0))
                })
            if spot_rows:
                sdf = pd.DataFrame(spot_rows)
                st.dataframe(sdf.style.format({
                    "Total": "{:.4f}", "Hold": "{:.4f}", "Available": "{:.4f}", "Entry Notional": "{:.2f}"
                }), use_container_width=True)
            else:
                st.info("No spot balances.")
        else:
            st.warning("Could not fetch spot balances.")

# === Opportunities Scanner ===
st.header("🚀 Hyperliquid Futures Opportunities")
st.caption("Scans all perps. **Bias** shows whether the setup favors Long or Short.")

if st.button("🔄 Scan Opportunities Now", type="primary") or True:
    ctxs = get_meta_and_ctxs()
    if ctxs and len(ctxs) == 2:
        universe = ctxs[0]["universe"]
        asset_ctxs = ctxs[1]
        opps = []
        for i, coin_meta in enumerate(universe):
            coin = coin_meta["name"]
            ctx = asset_ctxs[i]
            try:
                funding = float(ctx.get("funding", 0))
                mark = float(ctx.get("markPx", 0))
                prev = float(ctx.get("prevDayPx", mark))
                day_chg = ((mark - prev) / prev * 100) if prev else 0
                vol = float(ctx.get("dayNtlVlm", 0))
                oi = float(ctx.get("openInterest", 0))
                score, reasons, bias = score_opportunity(funding, day_chg, vol, oi, mark)
                if score >= 25:
                    opps.append({
                        "Coin": coin,
                        "Bias": bias,
                        "Score": score,
                        "Mark": mark,
                        "24h %": day_chg,
                        "Funding %/h": funding * 100,
                        "Ann. Fund ~%": funding * 3 * 365 * 100,
                        "Volume $": vol,
                        "OI": oi,
                        "Reasons": "; ".join(reasons)
                    })
            except:
                continue

        if opps:
            opps_df = pd.DataFrame(opps).sort_values("Score", ascending=False)
            # Highlight Bias column
            def highlight_bias(val):
                if val == "Long":
                    return "background-color: #1a7f37; color: white"
                if val == "Short":
                    return "background-color: #cf222e; color: white"
                return ""
            st.dataframe(
                opps_df.style.format({
                    "Mark": "{:.4f}",
                    "24h %": "{:+.2f}",
                    "Funding %/h": "{:.4f}",
                    "Ann. Fund ~%": "{:.1f}",
                    "Volume $": "{:,.0f}",
                    "OI": "{:.2f}"
                }).map(highlight_bias, subset=["Bias"]),
                use_container_width=True
            )
            st.success(f"Found {len(opps)} setups. **Bias** column shows recommended side (Long/Short).")

            # Chart for top opportunity
            if not opps_df.empty:
                top = opps_df.iloc[0]
                st.subheader(f"Top setup: {top['Coin']} → **{top['Bias']}** (Score {top['Score']})")
                candles = get_candles(top["Coin"], "1h", 72)
                if candles:
                    cdf = pd.DataFrame(candles)
                    cdf["time"] = pd.to_datetime(cdf["t"], unit="ms")
                    fig = go.Figure(data=[go.Candlestick(
                        x=cdf["time"],
                        open=cdf["o"].astype(float),
                        high=cdf["h"].astype(float),
                        low=cdf["l"].astype(float),
                        close=cdf["c"].astype(float)
                    )])
                    fig.update_layout(
                        title=f"{top['Coin']} 1h — Bias: {top['Bias']}",
                        xaxis_rangeslider_visible=False,
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No strong opportunities right now (score ≥ 25). Try again later.")
    else:
        st.error("Failed to fetch market data.")

st.divider()
st.caption("⚠️ Research tool only — not financial advice. Always DYOR. Spot + perp data is public via Hyperliquid API.")
