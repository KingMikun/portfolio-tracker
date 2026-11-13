# Portfolio Tracker + Hyperliquid Opportunities Scanner

A Streamlit app for tracking crypto (especially Hyperliquid) and stock positions, with fundamentals (revenue, buybacks proxy, news), custom metrics, and automated analysis of near-perfect futures setups on Hyperliquid.

## Features

- **Hyperliquid tracking**: Enter any public wallet address → live perp positions, uPnL, account value, margin (no private key).
- **Stocks**: Manual entry of ticker + quantity → live prices and values via yfinance.
- **Fundamentals**:
  - Stocks: Revenue (TTM), market cap, P/E, buyback proxy from cashflow, latest news.
  - Crypto: Price, mcap, volume, description via CoinGecko; notes on token buybacks/revenue.
- **Custom metrics**: Easy to extend in code.
- **HL Opportunities**: Scans all perps for extreme funding + momentum + volume setups. Scores and ranks "close to perfect" long/short biases. Includes chart for top pick.
- Auto-adjusts portfolio view based on onchain/HL activity when you refresh with the address.

## Setup & Run

```bash
pip install -r requirements.txt
streamlit run portfolio_tracker.py
```

Open the local URL (usually http://localhost:8501).

## Usage Tips

1. Paste your Hyperliquid address in the sidebar.
2. Edit tracked stocks and crypto list.
3. View portfolio, drill into fundamentals/news.
4. Hit the opportunities section (auto-scans) for futures ideas.
5. For more onchain venues: integrate Zerion/DeBank/CoinStats APIs (free tiers available) by adding wallet addresses and fetching balances.
6. For better crypto revenue/buybacks: use DefiLlama fees API, or project-specific dashboards (e.g. HYPE burns).
7. Rate limits: HL is generous; yfinance and CoinGecko keyless are fine for personal use. Get free CoinGecko Demo key for higher limits.

## Extending

- Add more chains: Use public RPCs + token lists or Zerion API.
- Better signals: Add RSI/MACD from candles, OI change over time, liquidation levels.
- Alerts: Add Telegram/Discord webhooks for high-score setups.
- Persistence: Save positions/history to CSV or SQLite.

**Disclaimer**: Research tool only. Not financial advice. DYOR. Public data only.
