# Daily Stock and Meme Coin Scanner

This is a local research scanner for stocks and meme coins. It flags assets that are up at least 10% today and ranks them with a simple score based on:

- daily percent gain
- dollar volume / liquidity
- short trend
- recent volatility

It does not make buy/sell decisions for you. Treat every result as a starting point for research.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Run

Browser app:

```powershell
python app.py
```

If `python` is not on your PATH, use the installed Python directly:

```powershell
& 'C:\Users\PJ Chitolie\AppData\Local\Python\pythoncore-3.14-64\python.exe' app.py
```

Then open:

```text
http://127.0.0.1:8787
```

You can also double-click:

- `run_local.bat` for this computer only.
- `run_network.bat` to let phones/tablets/other computers on the same Wi-Fi open the app.

When using network mode, open this from another device:

```text
http://YOUR_COMPUTER_IPV4:8787
```

Example:

```text
http://192.168.1.25:8787
```

If Windows Firewall asks, allow Python on private networks.

## Hosted Phone Access

To use the scanner when you are away from your computer, deploy it online. See `DEPLOY.md`.

The hosted app can be password protected with:

```text
SCANNER_PASSWORD=your-private-password
```

Login username:

```text
trader
```

Scan both stocks and meme coins:

```powershell
python scanner.py
```

Only scan stocks:

```powershell
python scanner.py --market stocks
```

Only scan meme coins:

```powershell
python scanner.py --market crypto
```

Write full results to JSON:

```powershell
python scanner.py --json results.json
```

## Customize

Edit `scanner_config.json` to change:

- `min_change_pct`: default is `10`
- `min_volume_usd`: liquidity filter
- `premarket_min_volume_usd`: minimum pre-market dollar volume
- `symbol_files`: extra symbol lists to scan, including `penny_stock_universe.txt`
- `max_symbols`: cap for how many stock symbols to scan from the combined universe
- stock ticker symbols
- crypto price range, CoinGecko ids, and `meme_coin_universe.txt`
- CoinGecko meme coin ids

## How to Read Results

- `Pre-Market Exploders`: extended-hours low-price stocks with a gap and unusual early volume.
- `Today`: percent move versus the previous close for stocks, or 24h move for crypto.
- `7d/1mo`: 1 month trend for stocks, 7 day trend for crypto.
- `Volume`: estimated dollar volume.
- `Vol Ratio`: current session volume compared with recent average session volume.
- `Volatility`: recent average range for stocks, 24h range for crypto.
- `Score`: rough watchlist score, not a prediction.

For pre-market day trade scanning, lower `Mover %` to `2` or `3` if the list is empty, and lower `Pre Vol x` to `1.0` to see more early movers. Higher settings are stricter.

Before trading, check news, earnings, SEC filings, token unlocks, spreads, liquidity, and your own risk limits.
