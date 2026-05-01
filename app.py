#!/usr/bin/env python3
"""
Local browser app for the market scanner.
"""

from __future__ import annotations

import json
import mimetypes
import argparse
import base64
import os
import requests
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from scanner import (
    DEFAULT_CONFIG,
    load_config,
    scan_meme_coins,
    scan_premarket_stocks,
    scan_stocks,
    resolve_crypto_ids,
    resolve_stock_symbols,
    with_extra_stock_symbols,
)


ROOT = Path(__file__).parent
STATIC = ROOT / "static"
AUTH_REALM = "Market Scanner"
YAHOO_SCREENER_URL = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"


def as_float(params: dict[str, list[str]], key: str, default: float) -> float:
    try:
        return float(params.get(key, [default])[0])
    except (TypeError, ValueError):
        return default


def as_int(params: dict[str, list[str]], key: str, default: int) -> int:
    try:
        return int(params.get(key, [default])[0])
    except (TypeError, ValueError):
        return default


def symbols_from_params(params: dict[str, list[str]]) -> list[str]:
    raw = ",".join(params.get("symbols", []))
    return [item.strip().upper() for item in raw.replace("\n", ",").split(",") if item.strip()]


class AppHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if not self.is_authorized():
            self.request_auth()
            return

        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.serve_file(STATIC / "index.html")
            return
        if parsed.path == "/api/scan":
            self.serve_scan(parsed.query)
            return
        if parsed.path == "/api/premarket":
            self.serve_premarket(parsed.query)
            return
        if parsed.path == "/api/crypto":
            self.serve_crypto(parsed.query)
            return
        if parsed.path == "/api/yahoo-gainers":
            self.serve_yahoo_gainers(parsed.query)
            return
        if parsed.path.startswith("/static/"):
            self.serve_file(STATIC / parsed.path.removeprefix("/static/"))
            return
        self.send_error(404, "Not found")

    def is_authorized(self) -> bool:
        password = os.environ.get("SCANNER_PASSWORD", "").strip()
        if not password:
            return True

        header = self.headers.get("Authorization", "")
        prefix = "Basic "
        if not header.startswith(prefix):
            return False

        try:
            decoded = base64.b64decode(header[len(prefix) :]).decode("utf-8")
        except Exception:
            return False

        username, _, supplied_password = decoded.partition(":")
        return username == "trader" and supplied_password == password

    def request_auth(self) -> None:
        self.send_response(401)
        self.send_header("WWW-Authenticate", f'Basic realm="{AUTH_REALM}"')
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Password required.")

    def serve_file(self, path: Path) -> None:
        if not path.exists() or not path.is_file() or STATIC not in path.resolve().parents:
            self.send_error(404, "Not found")
            return
        content = path.read_bytes()
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_json(self, status: int, payload: dict) -> None:
        content = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def serve_yahoo_gainers(self, query: str) -> None:
        params = parse_qs(query)
        limit = max(1, min(as_int(params, "limit", 25), 100))
        try:
            response = requests.get(
                YAHOO_SCREENER_URL,
                params={"scrIds": "day_gainers", "count": limit},
                headers={"User-Agent": "Mozilla/5.0 market-scanner/1.0"},
                timeout=20,
            )
            response.raise_for_status()
            result = response.json().get("finance", {}).get("result", [{}])[0]
            rows = []
            for quote in result.get("quotes", []):
                rows.append(
                    {
                        "symbol": quote.get("symbol"),
                        "name": quote.get("longName") or quote.get("shortName") or quote.get("displayName"),
                        "price": quote.get("regularMarketPrice"),
                        "change": quote.get("regularMarketChange"),
                        "change_pct": quote.get("regularMarketChangePercent"),
                        "volume": quote.get("regularMarketVolume"),
                        "avg_volume": quote.get("averageDailyVolume3Month"),
                        "market_cap": quote.get("marketCap"),
                        "pe_ratio": quote.get("trailingPE"),
                        "fifty_two_week_change_pct": quote.get("fiftyTwoWeekChangePercent"),
                        "fifty_two_week_range": quote.get("fiftyTwoWeekRange"),
                    }
                )
            self.serve_json(
                200,
                {
                    "gainers": rows,
                    "count": len(rows),
                    "source": "Yahoo Finance Day Gainers",
                    "disclaimer": "Yahoo screener data can be delayed. Confirm price, spread, and news before trading.",
                },
            )
        except Exception as exc:
            self.serve_json(500, {"error": f"Yahoo gainers unavailable: {exc}"})

    def serve_scan(self, query: str) -> None:
        params = parse_qs(query)
        market = params.get("market", ["all"])[0]
        min_price = as_float(params, "min_price", 0.001)
        max_price = as_float(params, "max_price", 30.0)
        min_change = as_float(params, "min_change", 10.0)
        limit = as_int(params, "limit", 25)
        include_news = params.get("news", ["true"])[0].lower() == "true"
        extra_symbols = symbols_from_params(params)
        if extra_symbols and max_price <= 30.0:
            max_price = 1000.0

        try:
            config = with_extra_stock_symbols(load_config(DEFAULT_CONFIG), extra_symbols)
            top_movers = []
            candidates = []
            meme_coins = []

            if market in ("all", "stocks"):
                stock_signals = scan_stocks(
                    config,
                    min_price=min_price,
                    max_price=max_price,
                    min_change_pct=min_change,
                    top_movers_only=False,
                    include_news=include_news,
                )
                top_movers = sorted(
                    (item for item in stock_signals if item.change_pct is not None and item.change_pct >= min_change),
                    key=lambda item: item.score,
                    reverse=True,
                )[:limit]
                candidates = stock_signals[:limit]

            if market in ("all", "crypto"):
                meme_coins = scan_meme_coins(
                    config,
                    min_price=min_price,
                    max_price=max_price,
                    min_change_pct=min_change,
                )[:limit]

            self.serve_json(
                200,
                {
                    "top_movers": [asdict(item) for item in top_movers],
                    "candidates": [asdict(item) for item in candidates],
                    "meme_coins": [asdict(item) for item in meme_coins],
                    "stock_universe_count": len(resolve_stock_symbols(config)),
                    "disclaimer": "Research only. Scores are heuristic, not a guarantee or financial advice.",
                },
            )
        except Exception as exc:
            self.serve_json(500, {"error": str(exc)})

    def serve_crypto(self, query: str) -> None:
        params = parse_qs(query)
        min_price = as_float(params, "min_price", 0.0)
        max_price = as_float(params, "max_price", 30.0)
        min_change = as_float(params, "min_change", 10.0)
        limit = as_int(params, "limit", 25)

        try:
            config = load_config(DEFAULT_CONFIG)
            meme_coins = scan_meme_coins(
                config,
                min_price=min_price,
                max_price=max_price,
                min_change_pct=min_change,
            )[:limit]
            self.serve_json(
                200,
                {
                    "meme_coins": [asdict(item) for item in meme_coins],
                    "crypto_universe_count": len(resolve_crypto_ids(config)),
                    "disclaimer": "Crypto and meme coins are high risk. Confirm liquidity, token unlocks, contract risk, and exchange access.",
                },
            )
        except Exception as exc:
            self.serve_json(500, {"error": str(exc)})

    def serve_premarket(self, query: str) -> None:
        params = parse_qs(query)
        min_price = as_float(params, "min_price", 0.001)
        max_price = as_float(params, "max_price", 30.0)
        min_change = as_float(params, "min_change", 5.0)
        min_volume_ratio = as_float(params, "min_volume_ratio", 1.5)
        limit = as_int(params, "limit", 25)
        include_news = params.get("news", ["true"])[0].lower() == "true"
        extra_symbols = symbols_from_params(params)

        try:
            config = with_extra_stock_symbols(load_config(DEFAULT_CONFIG), extra_symbols)
            premarket = scan_premarket_stocks(
                config,
                min_price=min_price,
                max_price=max_price,
                min_change_pct=min_change,
                min_volume_ratio=min_volume_ratio,
                include_news=include_news,
            )[:limit]
            self.serve_json(
                200,
                {
                    "premarket": [asdict(item) for item in premarket],
                    "stock_universe_count": len(resolve_stock_symbols(config)),
                    "disclaimer": "Pre-market movers are high risk. Confirm spreads, halts, dilution, float, and news before trading.",
                },
            )
        except Exception as exc:
            self.serve_json(500, {"error": str(exc)})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local market scanner web app.")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"), help="Use 0.0.0.0 to allow other devices on your network.")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8787")))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), AppHandler)
    display_host = "127.0.0.1" if args.host == "0.0.0.0" else args.host
    print(f"Market scanner app running at http://{display_host}:{args.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
