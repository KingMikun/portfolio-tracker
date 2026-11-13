import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import json
import plotly.express as px
import plotly.graph_objects as go

st.set_page_config(page_title="Portfolio Tracker & HL Opportunities", layout="wide", page_icon="📊")

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
def get_hl_positions(address):
    if not address or not address.startswith("0x"):
        return None
    data = hl_post({"type": "clearinghouseState", "user": address})
    return data

@st.cache_data(ttl=300)
def get_hl_portfolio(address):
    if not address or not address.startswith("0x"):
        return None
    data = hl_post({"type": "portfolio", "user": address})
    return data

@st.cache_data(ttl=30)
def get_meta_and_ctxs():
    data = hl_post({"type": "metaAndAssetCtxs"})
    return data

@st.cache_data(ttl=300)
def get_candles(coin, interval="1h", hours=48):
    end = int(datetime.now().timestamp() * 1000)
    start = end - hours * 3600 * 1000
    data = hl_post({
        "type": "candleSnapshot",
        "req": {"coin": coin, "interval": interval, "startTime": start, "endTime": end}
    })
    return data

def score_opportunity(funding, day_change_pct, volume, oi, mark):
    """Simple scoring for near-perfect setups."""
    score = 0
    reasons = []
    # Extreme funding (annualized approx 8h * 3 * 365)
    ann_funding = float(funding) * 3 * 365 * 100  # rough %
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
    
    # Funding direction vs price
    if float(funding) < -0.0001 and day_change_pct > 0:  # negative funding + up = longs favored
        score += 25
        reasons.append("Negative funding + upward momentum (long bias)")
    elif float(funding) > 0.0001 and day_change_pct < 0:
        score += 25
        reasons.append("Positive funding + downward momentum (short bias)")
    
    return score, reasons

# Sidebar config
st.sidebar.title("⚙️ Configuration")
hl_address = st.sidebar.text_input("Hyperliquid Wallet Address", placeholder="0x...", help="Public address to track positions. No private key needed.")
tracked_stocks = st.sidebar.text_area("Tracked Stocks (ticker,qty per line)", value="AAPL,10\nMSFT,5\nNVDA,3", help="e.g. AAPL,10")
tracked_crypto = st.sidebar.text_area("Tracked Crypto Tokens (symbol per line)", value="BTC\nETH\nSOL\nHYPE", help="For fundamentals/news")

st.title("📊 Portfolio Tracker + Hyperliquid Opportunities")
st.caption("Tracks positions from Hyperliquid (by address), manual stocks, fundamentals, news, and scans for futures setups.")

# === Portfolio Section ===
st.header("📈 Portfolio Overview")

col1, col2 = st.columns(2)

positions_df = pd.DataFrame()
total_hl_value = 0

with col1:
    st.subheader("Hyperliquid Positions")
    if hl_address:
        state = get_hl_positions(hl_address)
        if state and "assetPositions" in state:
            rows = []
            for ap in state["assetPositions"]:
                pos = ap["position"]
                coin = pos["coin"]
                szi = float(pos["szi"])
                if abs(szi) < 1e-8:
                    continue
                entry = float(pos["entryPx"])
                mark = float(pos.get("positionValue", 0)) / abs(szi) if szi != 0 else entry  # rough
                upnl = float(pos.get("unrealizedPnl", 0))
                lev = pos["leverage"]["value"] if "leverage" in pos else 1
                rows.append({
                    "Coin": coin,
                    "Side": "Long" if szi > 0 else "Short",
                    "Size": abs(szi),
                    "Entry": entry,
                    "uPnL": upnl,
                    "Leverage": lev,
                    "Value": abs(float(pos.get("positionValue", 0)))
                })
            if rows:
                positions_df = pd.DataFrame(rows)
                st.dataframe(positions_df.style.format({"Entry": "{:.4f}", "uPnL": "{:.2f}", "Value": "{:.2f}", "Size": "{:.4f}"}), use_container_width=True)
                total_hl_value = positions_df["Value"].sum()
                st.metric("HL Positions Notional", f"${total_hl_value:,.0f}")
            else:
                st.info("No open perp positions.")
            # Account summary
            ms = state.get("marginSummary", {})
            if ms:
                st.metric("Account Value", f"${float(ms.get('accountValue', 0)):,.2f}")
                st.metric("Withdrawable", f"${float(ms.get('withdrawable', 0)):,.2f}")
        else:
            st.warning("Could not fetch positions. Check address.")
    else:
        st.info("Enter a Hyperliquid address in the sidebar to track live positions.")

with col2:
    st.subheader("Stocks Positions (Manual)")
    stock_rows = []
    if tracked_stocks:
        for line in tracked_stocks.strip().split("\n"):
            if "," in line:
                try:
                    ticker, qty = line.split(",")
                    ticker = ticker.strip().upper()
                    qty = float(qty.strip())
                    t = yf.Ticker(ticker)
                    price = t.fast_info.get("lastPrice") or t.history(period="1d")["Close"].iloc[-1]
                    value = price * qty
                    stock_rows.append({"Ticker": ticker, "Qty": qty, "Price": price, "Value": value})
                except Exception as e:
                    st.warning(f"Error on {line}: {e}")
        if stock_rows:
            stocks_df = pd.DataFrame(stock_rows)
            st.dataframe(stocks_df.style.format({"Price": "{:.2f}", "Value": "{:.2f}"}), use_container_width=True)
            st.metric("Stocks Value", f"${stocks_df['Value'].sum():,.0f}")
        else:
            st.info("Add stocks in sidebar.")

# Combined
if not positions_df.empty or stock_rows:
    st.subheader("Total Approximate Portfolio")
    total = total_hl_value + (sum(r["Value"] for r in stock_rows) if stock_rows else 0)
    st.metric("Combined Tracked Value", f"${total:,.0f}", help="HL notional + stocks. Spot/onchain not fully included.")

# === Fundamentals & News ===
st.header("🔍 Fundamentals, Buybacks, Revenue & News")

asset_type = st.radio("Select asset type", ["Stocks", "Crypto"], horizontal=True)

if asset_type == "Stocks":
    selected = st.selectbox("Select Stock", [r["Ticker"] for r in stock_rows] if stock_rows else ["AAPL"])
    if selected:
        try:
            t = yf.Ticker(selected)
            info = t.info
            st.subheader(f"{selected} - {info.get('shortName', '')}")
            
            cols = st.columns(4)
            cols[0].metric("Price", f"${info.get('currentPrice', info.get('regularMarketPrice', 0)):.2f}")
            cols[1].metric("Market Cap", f"${info.get('marketCap', 0)/1e9:.1f}B")
            cols[2].metric("Revenue (TTM)", f"${info.get('totalRevenue', 0)/1e9:.1f}B" if info.get('totalRevenue') else "N/A")
            cols[3].metric("P/E", f"{info.get('trailingPE', 0):.1f}" if info.get('trailingPE') else "N/A")
            
            # Buybacks proxy: share count change or cashflow
            try:
                cf = t.cashflow
                if "Repurchase Of Capital Stock" in cf.index:
                    buyback = abs(cf.loc["Repurchase Of Capital Stock"].iloc[0]) / 1e9
                    st.metric("Latest Buybacks (approx)", f"${buyback:.2f}B")
                else:
                    st.info("No direct buyback line in cashflow. Check shares outstanding trend.")
            except:
                pass
            
            # News
            st.subheader("Latest News")
            news = t.news[:5] if t.news else []
            for n in news:
                st.markdown(f"**[{n.get('title', '')}]({n.get('link', '')})** - {n.get('publisher', '')}")
            
            # Custom metrics placeholder
            st.subheader("Custom Metrics")
            st.info("Add your own: e.g. revenue growth, buyback yield = buybacks / market cap. Extend the code for more.")
            
        except Exception as e:
            st.error(f"Error fetching {selected}: {e}")

else:
    # Crypto - use CoinGecko keyless for basic, note limitations
    selected = st.selectbox("Select Crypto", tracked_crypto.strip().split("\n") if tracked_crypto else ["BTC"])
    if selected:
        st.subheader(f"{selected.upper()} Fundamentals")
        # Simple price via CG
        cg_map = {"BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana", "HYPE": "hyperliquid"}
        cg_id = cg_map.get(selected.upper(), selected.lower())
        try:
            r = requests.get(f"https://api.coingecko.com/api/v3/coins/{cg_id}?localization=false&tickers=false&market_data=true&community_data=false&developer_data=false", timeout=10)
            if r.ok:
                data = r.json()
                md = data.get("market_data", {})
                cols = st.columns(4)
                cols[0].metric("Price", f"${md.get('current_price', {}).get('usd', 0):,.2f}")
                cols[1].metric("Market Cap", f"${md.get('market_cap', {}).get('usd', 0)/1e9:.1f}B")
                cols[2].metric("24h Vol", f"${md.get('total_volume', {}).get('usd', 0)/1e6:.0f}M")
                cols[3].metric("ATH", f"${md.get('ath', {}).get('usd', 0):,.0f}")
                
                st.write("**Description:**", data.get("description", {}).get("en", "N/A")[:500] + "...")
                
                # Revenue / buybacks for crypto is project-specific; note it
                st.info("Token buybacks and protocol revenue require project-specific sources (e.g. DefiLlama fees, tokenomics docs). For HYPE, check burns/buybacks on Hyperliquid docs or dashboards.")
                
                # News via search or simple
                st.subheader("Latest Mentions / News")
                st.markdown(f"[Search latest on CoinGecko](https://www.coingecko.com/en/coins/{cg_id}) | [X/Twitter search](https://x.com/search?q={selected})")
            else:
                st.warning("CoinGecko fetch failed. Try with API key for better data.")
        except Exception as e:
            st.error(str(e))

# === Hyperliquid Opportunities Scanner ===
st.header("🚀 Hyperliquid Futures Opportunities")
st.caption("Scans all perps for near-perfect setups based on funding extremes, momentum, volume. Refresh to update.")

if st.button("🔄 Scan Opportunities Now") or True:
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
                score, reasons = score_opportunity(funding, day_chg, vol, oi, mark)
                if score >= 25:  # threshold for "close to perfect"
                    opps.append({
                        "Coin": coin,
                        "Mark": mark,
                        "24h %": day_chg,
                        "Funding %/h": funding * 100,
                        "Ann. Fund ~%": funding * 3 * 365 * 100,
                        "Volume $": vol,
                        "OI": oi,
                        "Score": score,
                        "Reasons": "; ".join(reasons)
                    })
            except:
                continue
        
        if opps:
            opps_df = pd.DataFrame(opps).sort_values("Score", ascending=False)
            st.dataframe(
                opps_df.style.format({
                    "Mark": "{:.4f}",
                    "24h %": "{:+.2f}",
                    "Funding %/h": "{:.4f}",
                    "Ann. Fund ~%": "{:.1f}",
                    "Volume $": "{:,.0f}",
                    "OI": "{:.2f}"
                }),
                use_container_width=True
            )
            st.success(f"Found {len(opps)} near-perfect or strong opportunities. Higher score = better setup. Always DYOR.")
            
            # Top one chart
            if not opps_df.empty:
                top = opps_df.iloc[0]["Coin"]
                st.subheader(f"Chart for top: {top}")
                candles = get_candles(top, "1h", 72)
                if candles:
                    cdf = pd.DataFrame(candles)
                    cdf["time"] = pd.to_datetime(cdf["t"], unit="ms")
                    fig = go.Figure(data=[go.Candlestick(
                        x=cdf["time"], open=cdf["o"].astype(float), high=cdf["h"].astype(float),
                        low=cdf["l"].astype(float), close=cdf["c"].astype(float)
                    )])
                    fig.update_layout(title=f"{top} 1h candles", xaxis_rangeslider_visible=False, height=400)
                    st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No strong opportunities right now. Try again later or lower threshold in code.")
    else:
        st.error("Failed to fetch market data.")

st.divider()
st.caption("⚠️ This is a research tool, not financial advice. Positions from HL are public; stocks are manual. Extend with more onchain APIs (Zerion, DeBank) for full multi-venue tracking. Custom metrics and buybacks can be enhanced with paid APIs or project-specific scrapers.")
st.caption("Built for tracking across venues: HL auto-updates from address. For other onchain, add wallet trackers. Run locally with `streamlit run app.py`.")
