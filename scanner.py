#!/usr/bin/env python3
"""
Daily market scanner for stocks and meme coins.

The scanner highlights assets that are up at least a configurable percent today
and computes a simple watchlist score from momentum, liquidity, and volatility.
It is meant for research, not financial advice.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote_plus

import requests

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - handled at runtime for friendlier CLI output
    yf = None


DEFAULT_CONFIG = Path(__file__).with_name("scanner_config.json")


@dataclass
class Signal:
    market: str
    symbol: str
    name: str
    price: float | None
    change_pct: float | None
    volume_usd: float | None
    trend_pct: float | None
    volatility_pct: float | None
    score: float
    notes: list[str]
    volume_ratio: float | None = None
    prediction_score: float | None = None
    news_score: float | None = None
    headlines: list[dict[str, str]] | None = None
    setup_grade: str | None = None
    setup_tags: list[str] | None = None


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def unique_symbols(symbols: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        clean = str(symbol).strip().upper()
        if clean and clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result


def unique_ids(ids: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in ids:
        clean = str(item).strip().lower()
        if clean and clean not in seen:
            result.append(clean)
            seen.add(clean)
    return result


def resolve_stock_symbols(config: dict[str, Any]) -> list[str]:
    stock_config = config["stocks"]
    symbols = list(stock_config.get("symbols", []))
    for filename in stock_config.get("symbol_files", []):
        path = Path(__file__).with_name(filename)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#"):
                symbols.append(clean.split(",")[0])
    max_symbols = int(stock_config.get("max_symbols", 350))
    return unique_symbols(symbols)[:max_symbols]


def resolve_crypto_ids(config: dict[str, Any]) -> list[str]:
    crypto_config = config["crypto"]
    coin_ids = list(crypto_config.get("coingecko_ids", []))
    for filename in crypto_config.get("coin_files", []):
        path = Path(__file__).with_name(filename)
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#"):
                coin_ids.append(clean.split(",")[0])
    max_coins = int(crypto_config.get("max_coins", 250))
    return unique_ids(coin_ids)[:max_coins]


def pct_change(new: float | None, old: float | None) -> float | None:
    if new is None or old in (None, 0):
        return None
    return ((new - old) / old) * 100


def safe_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return None
        return result
    except (TypeError, ValueError):
        return None


def score_signal(
    change_pct: float | None,
    volume_usd: float | None,
    trend_pct: float | None,
    volatility_pct: float | None,
    min_volume_usd: float,
) -> tuple[float, list[str]]:
    notes: list[str] = []
    score = 0.0

    if change_pct is not None:
        score += min(max(change_pct, 0), 40) * 2.0
        if change_pct >= 10:
            notes.append("up 10%+ today")

    if volume_usd is not None:
        liquidity_ratio = min(volume_usd / max(min_volume_usd, 1), 5)
        score += liquidity_ratio * 10
        if volume_usd >= min_volume_usd:
            notes.append("passes liquidity filter")
        else:
            notes.append("thin liquidity")

    if trend_pct is not None:
        score += min(max(trend_pct, -20), 50) * 0.8
        if trend_pct > 0:
            notes.append("positive short trend")

    if volatility_pct is not None:
        if volatility_pct > 20:
            score -= 15
            notes.append("very volatile")
        elif volatility_pct < 8:
            score += 5

    return round(score, 2), notes


def pro_setup_read(
    *,
    change_pct: float | None,
    volume_usd: float | None,
    volume_ratio: float | None,
    volatility_pct: float | None,
    news_score: float | None,
    min_volume_usd: float,
) -> tuple[str, list[str]]:
    tags: list[str] = []
    points = 0

    if change_pct is not None:
        if change_pct >= 20:
            tags.append("momentum burst")
            points += 2
        elif change_pct >= 8:
            tags.append("mover")
            points += 1

    if volume_ratio is not None:
        if volume_ratio >= 3:
            tags.append("relative volume surge")
            points += 3
        elif volume_ratio >= 1.5:
            tags.append("unusual volume")
            points += 2

    if volume_usd is not None:
        if volume_usd >= min_volume_usd:
            tags.append("liquid enough")
            points += 2
        elif volume_usd < min_volume_usd * 0.25:
            tags.append("thin liquidity")
            points -= 2

    if volatility_pct is not None:
        if volatility_pct >= 25:
            tags.append("wide-risk tape")
            points -= 2
        elif volatility_pct <= 12:
            tags.append("controlled range")
            points += 1

    if news_score is not None and news_score > 0:
        tags.append("catalyst watch")
        points += 1

    if points >= 7:
        grade = "A"
    elif points >= 4:
        grade = "B"
    elif points >= 1:
        grade = "C"
    else:
        grade = "Avoid"

    return grade, tags[:5]


def score_news_headlines(headlines: list[dict[str, str]]) -> tuple[float, list[str]]:
    positive_words = {
        "approval",
        "beats",
        "breakout",
        "contract",
        "deal",
        "earnings beat",
        "fda",
        "guidance raised",
        "launch",
        "merger",
        "partnership",
        "raises",
        "rally",
        "surge",
        "upgrade",
    }
    negative_words = {
        "bankruptcy",
        "downgrade",
        "investigation",
        "lawsuit",
        "misses",
        "offering",
        "probe",
        "sec",
        "slump",
        "warning",
    }
    score = 0.0
    notes: list[str] = []
    text = " ".join(item["title"].lower() for item in headlines)
    for word in positive_words:
        if word in text:
            score += 4
    for word in negative_words:
        if word in text:
            score -= 5
    if score > 0:
        notes.append("positive news keywords")
    if score < 0:
        notes.append("caution news keywords")
    return max(min(score, 20), -20), notes


def fetch_yahoo_news(symbol: str, limit: int = 3) -> list[dict[str, str]]:
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={quote_plus(symbol)}&region=US&lang=en-US"
    response = requests.get(url, timeout=12, headers={"User-Agent": "market-scanner/1.0"})
    response.raise_for_status()
    root = ET.fromstring(response.content)
    headlines: list[dict[str, str]] = []
    for item in root.findall(".//item")[:limit]:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        published = item.findtext("pubDate") or ""
        if title:
            headlines.append({"title": title, "link": link, "published": published})
    return headlines


def prediction_from_factors(
    change_pct: float | None,
    volume_usd: float | None,
    volume_ratio: float | None,
    trend_pct: float | None,
    volatility_pct: float | None,
    news_score: float | None,
    min_volume_usd: float,
) -> float:
    score = 45.0
    if change_pct is not None:
        score += min(max(change_pct, -10), 25) * 0.9
    if trend_pct is not None:
        score += min(max(trend_pct, -20), 40) * 0.35
    if volume_usd is not None:
        score += min(volume_usd / max(min_volume_usd, 1), 5) * 3.0
    if volume_ratio is not None:
        score += min(max(volume_ratio - 1, -1), 5) * 5.0
    if volatility_pct is not None and volatility_pct > 18:
        score -= min((volatility_pct - 18) * 0.8, 18)
    if news_score is not None:
        score += news_score
    return round(max(0, min(score, 99)), 1)


def with_extra_stock_symbols(config: dict[str, Any], extra_symbols: Iterable[str] | None) -> dict[str, Any]:
    if not extra_symbols:
        return config
    updated = json.loads(json.dumps(config))
    current = updated.setdefault("stocks", {}).setdefault("symbols", [])
    seen = {str(symbol).upper() for symbol in current}
    for symbol in extra_symbols:
        clean = str(symbol).strip().upper()
        if clean and clean not in seen:
            current.append(clean)
            seen.add(clean)
    return updated


def stock_frame(data: Any, symbol: str, symbol_count: int) -> Any | None:
    if data is None or data.empty:
        return None
    if symbol_count == 1:
        return data
    if symbol in data.columns.get_level_values(0):
        return data[symbol]
    return None


def previous_daily_close(daily_history: Any, latest_day: Any | None) -> float | None:
    if daily_history is None or daily_history.empty:
        return None
    daily_history = daily_history.dropna(subset=["Close"])
    if daily_history.empty:
        return None
    if latest_day is not None and daily_history.index[-1].date() == latest_day and len(daily_history) > 1:
        return safe_float(daily_history.iloc[-2].get("Close"))
    return safe_float(daily_history.iloc[-1].get("Close"))


def scan_premarket_stocks(
    config: dict[str, Any],
    *,
    min_price: float | None = None,
    max_price: float | None = None,
    min_change_pct: float = 5.0,
    min_volume_ratio: float = 1.5,
    include_news: bool = False,
    news_limit: int = 3,
) -> list[Signal]:
    if yf is None:
        raise RuntimeError("Missing dependency: install yfinance with `pip install -r requirements.txt`.")

    stock_config = config["stocks"]
    symbols = resolve_stock_symbols(config)
    min_volume_usd = float(stock_config.get("premarket_min_volume_usd", 250_000))
    min_price = float(stock_config.get("min_price", 0.001) if min_price is None else min_price)
    max_price = float(stock_config.get("max_price", 30) if max_price is None else max_price)

    intraday = yf.download(
        tickers=" ".join(symbols),
        period="5d",
        interval="5m",
        group_by="ticker",
        auto_adjust=False,
        prepost=True,
        progress=False,
        threads=True,
        timeout=10,
    )
    daily = yf.download(
        tickers=" ".join(symbols),
        period="10d",
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=10,
    )

    signals: list[Signal] = []
    for symbol in symbols:
        history = stock_frame(intraday, symbol, len(symbols))
        daily_history = stock_frame(daily, symbol, len(symbols))
        if history is None:
            continue

        if history.empty or daily_history is None or daily_history.empty:
            continue

        history = history.dropna(subset=["Close"])
        daily_history = daily_history.dropna(subset=["Close"])
        if history.empty or daily_history.empty:
            continue

        latest = history.iloc[-1]
        price = safe_float(latest.get("Close"))
        if price is None or price < min_price or price > max_price:
            continue

        latest_day = history.index[-1].date()
        previous_close = previous_daily_close(daily_history, latest_day)
        change = pct_change(price, previous_close)
        if change is None or change < min_change_pct:
            continue

        session_rows = history[[index.date() == latest_day for index in history.index]]
        previous_days = history[[index.date() != latest_day for index in history.index]]
        session_volume = safe_float(session_rows["Volume"].sum()) if "Volume" in session_rows else None
        avg_session_volume = None
        if "Volume" in previous_days and not previous_days.empty:
            by_day = previous_days.groupby(previous_days.index.date)["Volume"].sum()
            avg_session_volume = safe_float(by_day.mean())

        volume_ratio = (
            session_volume / avg_session_volume
            if session_volume is not None and avg_session_volume not in (None, 0)
            else None
        )
        if volume_ratio is not None and volume_ratio < min_volume_ratio:
            continue

        volume_usd = price * session_volume if session_volume is not None else None
        session_low = safe_float(session_rows["Low"].min()) if "Low" in session_rows else None
        session_high = safe_float(session_rows["High"].max()) if "High" in session_rows else None
        volatility = (
            ((session_high - session_low) / price) * 100
            if session_high is not None and session_low is not None and price not in (None, 0)
            else None
        )

        score, notes = score_signal(change, volume_usd, change, volatility, min_volume_usd)
        notes.append("pre-market gap")
        if volume_ratio is not None and volume_ratio >= 3:
            notes.append("volume surge")
        elif volume_ratio is not None and volume_ratio >= 1.5:
            notes.append("unusual early volume")

        headlines: list[dict[str, str]] = []
        news_score = 0.0
        if include_news:
            try:
                headlines = fetch_yahoo_news(symbol, limit=news_limit)
                news_score, news_notes = score_news_headlines(headlines)
                notes.extend(news_notes)
            except Exception:
                notes.append("news unavailable")

        prediction_score = prediction_from_factors(
            change,
            volume_usd,
            volume_ratio,
            change,
            volatility,
            news_score,
            min_volume_usd,
        )
        setup_grade, setup_tags = pro_setup_read(
            change_pct=change,
            volume_usd=volume_usd,
            volume_ratio=volume_ratio,
            volatility_pct=volatility,
            news_score=news_score,
            min_volume_usd=min_volume_usd,
        )

        signals.append(
            Signal(
                market="pre_market",
                symbol=symbol.upper(),
                name=symbol.upper(),
                price=price,
                change_pct=change,
                volume_usd=volume_usd,
                trend_pct=change,
                volatility_pct=volatility,
                score=score,
                notes=notes,
                volume_ratio=volume_ratio,
                prediction_score=prediction_score,
                news_score=news_score,
                headlines=headlines,
                setup_grade=setup_grade,
                setup_tags=setup_tags,
            )
        )

    return sorted(signals, key=lambda item: item.prediction_score or item.score, reverse=True)


def scan_stocks(
    config: dict[str, Any],
    *,
    min_price: float | None = None,
    max_price: float | None = None,
    min_change_pct: float | None = None,
    top_movers_only: bool = True,
    include_news: bool = False,
    news_limit: int = 3,
) -> list[Signal]:
    if yf is None:
        raise RuntimeError("Missing dependency: install yfinance with `pip install -r requirements.txt`.")

    stock_config = config["stocks"]
    symbols = resolve_stock_symbols(config)
    min_change_pct = float(stock_config.get("min_change_pct", 10) if min_change_pct is None else min_change_pct)
    min_volume_usd = float(stock_config.get("min_volume_usd", 20_000_000))
    period = stock_config.get("history_period", "1mo")
    min_price = float(stock_config.get("min_price", 0.001) if min_price is None else min_price)
    max_price = float(stock_config.get("max_price", 30) if max_price is None else max_price)

    signals: list[Signal] = []
    intraday = yf.download(
        tickers=" ".join(symbols),
        period="5d",
        interval="5m",
        group_by="ticker",
        auto_adjust=False,
        prepost=True,
        progress=False,
        threads=True,
        timeout=10,
    )
    data = yf.download(
        tickers=" ".join(symbols),
        period=period,
        interval="1d",
        group_by="ticker",
        auto_adjust=False,
        progress=False,
        threads=True,
        timeout=10,
    )

    for symbol in symbols:
        history = stock_frame(data, symbol, len(symbols))
        current_history = stock_frame(intraday, symbol, len(symbols))
        if history is None:
            continue

        if history.empty:
            continue

        history = history.dropna(subset=["Close"])
        if history.empty:
            continue

        latest = history.iloc[-1]
        current_history = (
            current_history.dropna(subset=["Close"])
            if current_history is not None and not current_history.empty
            else None
        )
        current_latest = current_history.iloc[-1] if current_history is not None and not current_history.empty else None
        price = safe_float(current_latest.get("Close")) if current_latest is not None else safe_float(latest.get("Close"))
        if price is None or price < min_price or price > max_price:
            continue
        latest_day = current_history.index[-1].date() if current_history is not None and not current_history.empty else None
        previous_close = previous_daily_close(history, latest_day)
        change = pct_change(price, previous_close)
        if current_history is not None and not current_history.empty:
            session_rows = current_history[[index.date() == latest_day for index in current_history.index]]
            volume = safe_float(session_rows["Volume"].sum()) if "Volume" in session_rows else None
        else:
            volume = safe_float(latest.get("Volume"))
        volume_usd = price * volume if price is not None and volume is not None else None
        avg_volume = safe_float(history.tail(20)["Volume"].mean()) if "Volume" in history else None
        volume_ratio = volume / avg_volume if volume is not None and avg_volume not in (None, 0) else None

        first_close = safe_float(history.iloc[0].get("Close"))
        trend = pct_change(price, first_close)
        daily_ranges = []
        for _, row in history.tail(10).iterrows():
            high = safe_float(row.get("High"))
            low = safe_float(row.get("Low"))
            close = safe_float(row.get("Close"))
            if high is not None and low is not None and close not in (None, 0):
                daily_ranges.append(((high - low) / close) * 100)
        volatility = sum(daily_ranges) / len(daily_ranges) if daily_ranges else None

        score, notes = score_signal(change, volume_usd, trend, volatility, min_volume_usd)
        headlines: list[dict[str, str]] = []
        news_score = 0.0
        if include_news:
            try:
                headlines = fetch_yahoo_news(symbol, limit=news_limit)
                news_score, news_notes = score_news_headlines(headlines)
                notes.extend(news_notes)
            except Exception:
                notes.append("news unavailable")

        prediction_score = prediction_from_factors(
            change,
            volume_usd,
            volume_ratio,
            trend,
            volatility,
            news_score,
            min_volume_usd,
        )
        if volume_ratio is not None and volume_ratio >= 1.5:
            notes.append("unusual volume")
        setup_grade, setup_tags = pro_setup_read(
            change_pct=change,
            volume_usd=volume_usd,
            volume_ratio=volume_ratio,
            volatility_pct=volatility,
            news_score=news_score,
            min_volume_usd=min_volume_usd,
        )

        if not top_movers_only or (change is not None and change >= min_change_pct):
            signals.append(
                Signal(
                    market="stock",
                    symbol=symbol.upper(),
                    name=symbol.upper(),
                    price=price,
                    change_pct=change,
                    volume_usd=volume_usd,
                    trend_pct=trend,
                    volatility_pct=volatility,
                    score=score,
                    notes=notes,
                    volume_ratio=volume_ratio,
                    prediction_score=prediction_score,
                    news_score=news_score,
                    headlines=headlines,
                    setup_grade=setup_grade,
                    setup_tags=setup_tags,
                )
            )

    sort_key = (lambda item: item.score) if top_movers_only else (lambda item: item.prediction_score or 0)
    return sorted(signals, key=sort_key, reverse=True)


def chunked(items: list[str], size: int) -> Iterable[list[str]]:
    for index in range(0, len(items), size):
        yield items[index : index + size]


def scan_meme_coins(
    config: dict[str, Any],
    *,
    min_price: float | None = None,
    max_price: float | None = None,
    min_change_pct: float | None = None,
) -> list[Signal]:
    crypto_config = config["crypto"]
    coin_ids = resolve_crypto_ids(config)
    min_change_pct = float(crypto_config.get("min_change_pct", 10) if min_change_pct is None else min_change_pct)
    min_volume_usd = float(crypto_config.get("min_volume_usd", 1_000_000))
    min_price = float(crypto_config.get("min_price", 0) if min_price is None else min_price)
    max_price = float(crypto_config.get("max_price", 30) if max_price is None else max_price)
    max_coins = int(crypto_config.get("max_coins", 250))
    use_meme_category = bool(crypto_config.get("use_coingecko_meme_category", True))
    base_url = "https://api.coingecko.com/api/v3/coins/markets"

    signals: list[Signal] = []
    market_payloads: list[list[dict[str, Any]]] = []
    if use_meme_category:
        response = requests.get(
            base_url,
            params={
                "vs_currency": "usd",
                "order": "market_cap_desc",
                "category": "meme-token",
                "per_page": min(max_coins, 250),
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h,7d",
            },
            timeout=30,
        )
        response.raise_for_status()
        market_payloads.append(response.json())

    for ids in chunked(coin_ids, 100):
        response = requests.get(
            base_url,
            params={
                "vs_currency": "usd",
                "ids": ",".join(ids),
                "order": "market_cap_desc",
                "per_page": len(ids),
                "page": 1,
                "sparkline": "false",
                "price_change_percentage": "24h,7d",
            },
            timeout=30,
        )
        response.raise_for_status()
        market_payloads.append(response.json())

    seen_ids: set[str] = set()
    for payload in market_payloads:
        for coin in payload:
            coin_id = str(coin.get("id", ""))
            if coin_id in seen_ids:
                continue
            seen_ids.add(coin_id)
            price = safe_float(coin.get("current_price"))
            if price is None or price < min_price or price > max_price:
                continue
            change = safe_float(coin.get("price_change_percentage_24h"))
            volume_usd = safe_float(coin.get("total_volume"))
            trend = safe_float(coin.get("price_change_percentage_7d_in_currency"))
            high_24h = safe_float(coin.get("high_24h"))
            low_24h = safe_float(coin.get("low_24h"))
            volatility = (
                ((high_24h - low_24h) / price) * 100
                if high_24h is not None and low_24h is not None and price not in (None, 0)
                else None
            )

            score, notes = score_signal(change, volume_usd, trend, volatility, min_volume_usd)
            setup_grade, setup_tags = pro_setup_read(
                change_pct=change,
                volume_usd=volume_usd,
                volume_ratio=None,
                volatility_pct=volatility,
                news_score=None,
                min_volume_usd=min_volume_usd,
            )
            if change is not None and change >= min_change_pct:
                signals.append(
                    Signal(
                        market="meme_coin",
                        symbol=str(coin.get("symbol", "")).upper(),
                        name=str(coin.get("name", "")),
                        price=price,
                        change_pct=change,
                        volume_usd=volume_usd,
                        trend_pct=trend,
                    volatility_pct=volatility,
                    score=score,
                    notes=notes,
                    prediction_score=score,
                    setup_grade=setup_grade,
                    setup_tags=setup_tags,
                )
            )

    return sorted(signals, key=lambda item: item.score, reverse=True)


def format_money(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.2f}K"
    return f"${value:.6g}"


def format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:+.2f}%"


def print_table(signals: list[Signal], limit: int) -> None:
    if not signals:
        print("No symbols matched the current filters.")
        return

    rows = signals[:limit]
    print(
        f"{'Market':<10} {'Symbol':<10} {'Name':<22} {'Price':>12} "
        f"{'Today':>9} {'7d/1mo':>9} {'Volume':>12} {'Volatility':>11} {'Score':>7}  Notes"
    )
    print("-" * 124)
    for item in rows:
        print(
            f"{item.market:<10} {item.symbol:<10} {item.name[:22]:<22} "
            f"{format_money(item.price):>12} {format_pct(item.change_pct):>9} "
            f"{format_pct(item.trend_pct):>9} {format_money(item.volume_usd):>12} "
            f"{format_pct(item.volatility_pct):>11} {item.score:>7.2f}  "
            f"{', '.join(item.notes)}"
        )


def write_json(signals: list[Signal], output: Path) -> None:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "signals": [signal.__dict__ for signal in signals],
    }
    with output.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan stocks and meme coins for daily 10%+ movers.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Path to scanner_config.json.")
    parser.add_argument("--market", choices=["stocks", "crypto", "all"], default="all")
    parser.add_argument("--limit", type=int, default=25, help="Maximum rows to print.")
    parser.add_argument("--json", type=Path, help="Optional path to write full results as JSON.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)

    signals: list[Signal] = []
    if args.market in ("stocks", "all"):
        signals.extend(scan_stocks(config))
    if args.market in ("crypto", "all"):
        signals.extend(scan_meme_coins(config))

    signals.sort(key=lambda item: item.score, reverse=True)
    print_table(signals, args.limit)

    if args.json:
        write_json(signals, args.json)
        print(f"\nWrote JSON results to {args.json}")

    print("\nResearch only. Confirm news, filings, liquidity, spreads, and your risk plan before trading.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except requests.HTTPError as exc:
        print(f"Data provider error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    except Exception as exc:
        print(f"Scanner failed: {exc}", file=sys.stderr)
        raise SystemExit(1)
