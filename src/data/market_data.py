"""Market data aggregator - live feeds, news, institutional flow, scanners."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field

from src.config import settings


class NewsItem(BaseModel):
    title: str
    source: str
    url: str = ""
    published_at: datetime = Field(default_factory=datetime.utcnow)
    sentiment: float = 0.0  # -1.0 to 1.0
    symbols: list[str] = Field(default_factory=list)
    summary: str = ""


class InstitutionalFlow(BaseModel):
    symbol: str
    flow_type: str  # "BLOCK", "SWEEP", "SPLIT"
    option_type: str  # "CALL", "PUT"
    strike: float
    expiration: str
    premium: float
    volume: int
    open_interest: int
    side: str  # "BUY", "SELL"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MarketSnapshot(BaseModel):
    """Point-in-time market state for agent consumption."""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    spy_price: float = 0.0
    vix: float = 0.0
    spy_change_pct: float = 0.0
    sector_performance: dict[str, float] = Field(default_factory=dict)
    top_gainers: list[dict[str, Any]] = Field(default_factory=list)
    top_losers: list[dict[str, Any]] = Field(default_factory=list)
    unusual_options: list[InstitutionalFlow] = Field(default_factory=list)
    recent_news: list[NewsItem] = Field(default_factory=list)
    market_breadth: dict[str, Any] = Field(default_factory=dict)
    fear_greed_index: float = 50.0  # 0-100


class MarketDataEngine:
    """Aggregates data from multiple sources into a unified market view."""

    def __init__(self):
        self._http = httpx.AsyncClient(timeout=30.0)
        self._schwab_client = None
        self._running = False
        self._latest_snapshot: MarketSnapshot | None = None
        self._callbacks: list = []

    def set_schwab_client(self, client) -> None:
        self._schwab_client = client

    def on_update(self, callback) -> None:
        """Register callback for market data updates."""
        self._callbacks.append(callback)

    async def start(self) -> None:
        """Start the market data engine."""
        self._running = True
        logger.info("Market data engine started")
        asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        self._running = False
        await self._http.aclose()
        logger.info("Market data engine stopped")

    async def get_snapshot(self) -> MarketSnapshot:
        """Get the latest market snapshot, refreshing if stale."""
        if self._latest_snapshot and (
            datetime.utcnow() - self._latest_snapshot.timestamp
        ) < timedelta(seconds=30):
            return self._latest_snapshot

        return await self._build_snapshot()

    async def _poll_loop(self) -> None:
        """Continuous polling loop for market data."""
        while self._running:
            try:
                snapshot = await self._build_snapshot()
                for cb in self._callbacks:
                    await cb(snapshot)
            except Exception as e:
                logger.error(f"Market data poll error: {e}")
            await asyncio.sleep(15)

    async def _build_snapshot(self) -> MarketSnapshot:
        """Build a comprehensive market snapshot from all sources."""
        snapshot = MarketSnapshot()

        # Gather data from all sources concurrently
        results = await asyncio.gather(
            self._fetch_market_indices(),
            self._fetch_news(),
            self._fetch_unusual_options(),
            self._fetch_sector_performance(),
            return_exceptions=True,
        )

        indices, news, unusual_opts, sectors = results

        if isinstance(indices, dict):
            snapshot.spy_price = indices.get("spy_price", 0.0)
            snapshot.vix = indices.get("vix", 0.0)
            snapshot.spy_change_pct = indices.get("spy_change_pct", 0.0)
            snapshot.fear_greed_index = indices.get("fear_greed", 50.0)
            snapshot.market_breadth = indices.get("breadth", {})

        if isinstance(news, list):
            snapshot.recent_news = news

        if isinstance(unusual_opts, list):
            snapshot.unusual_options = unusual_opts

        if isinstance(sectors, dict):
            snapshot.sector_performance = sectors

        self._latest_snapshot = snapshot
        return snapshot

    async def _fetch_market_indices(self) -> dict[str, Any]:
        """Fetch major market indices via Schwab or fallback."""
        result = {"spy_price": 0.0, "vix": 0.0, "spy_change_pct": 0.0}

        if self._schwab_client:
            try:
                spy = await self._schwab_client.get_quote("SPY")
                result["spy_price"] = spy.get("lastPrice", 0.0)
                result["spy_change_pct"] = spy.get("netPercentChangeInDouble", 0.0)

                vix = await self._schwab_client.get_quote("$VIX.X")
                result["vix"] = vix.get("lastPrice", 0.0)
            except Exception as e:
                logger.debug(f"Schwab quote fetch error: {e}")

        # Estimate fear/greed from VIX
        vix_val = result.get("vix", 20)
        if vix_val > 0:
            result["fear_greed"] = max(0, min(100, 100 - (vix_val - 12) * 3))

        return result

    async def _fetch_news(self) -> list[NewsItem]:
        """Fetch financial news from available sources."""
        news_items = []

        # Polygon news endpoint
        if settings.polygon_api_key:
            try:
                resp = await self._http.get(
                    "https://api.polygon.io/v2/reference/news",
                    params={
                        "limit": 20,
                        "order": "desc",
                        "sort": "published_utc",
                        "apiKey": settings.polygon_api_key,
                    },
                )
                if resp.status_code == 200:
                    for item in resp.json().get("results", []):
                        tickers = [t for t in item.get("tickers", [])]
                        news_items.append(
                            NewsItem(
                                title=item.get("title", ""),
                                source=item.get("publisher", {}).get("name", ""),
                                url=item.get("article_url", ""),
                                published_at=datetime.fromisoformat(
                                    item.get("published_utc", datetime.utcnow().isoformat()).replace("Z", "+00:00")
                                ),
                                symbols=tickers,
                                summary=item.get("description", ""),
                            )
                        )
            except Exception as e:
                logger.debug(f"Polygon news error: {e}")

        # RSS fallback for free financial news
        try:
            import feedparser

            feeds = [
                "https://feeds.finance.yahoo.com/rss/2.0/headline?s=SPY&region=US&lang=en-US",
                "https://www.cnbc.com/id/100003114/device/rss/rss.html",
            ]
            for feed_url in feeds:
                resp = await self._http.get(feed_url)
                if resp.status_code == 200:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries[:5]:
                        news_items.append(
                            NewsItem(
                                title=entry.get("title", ""),
                                source=feed.feed.get("title", "Unknown"),
                                url=entry.get("link", ""),
                                summary=entry.get("summary", "")[:500],
                            )
                        )
        except Exception as e:
            logger.debug(f"RSS feed error: {e}")

        return news_items[:20]

    async def _fetch_unusual_options(self) -> list[InstitutionalFlow]:
        """Fetch unusual options activity / institutional flow."""
        flows = []

        if settings.polygon_api_key:
            try:
                resp = await self._http.get(
                    "https://api.polygon.io/v3/snapshot/options/SPY",
                    params={"apiKey": settings.polygon_api_key},
                )
                if resp.status_code == 200:
                    for result in resp.json().get("results", [])[:20]:
                        details = result.get("details", {})
                        day = result.get("day", {})
                        if day.get("volume", 0) > 1000:
                            flows.append(
                                InstitutionalFlow(
                                    symbol=details.get("ticker", ""),
                                    flow_type="SWEEP" if day.get("volume", 0) > 5000 else "BLOCK",
                                    option_type=details.get("contract_type", "CALL"),
                                    strike=details.get("strike_price", 0),
                                    expiration=details.get("expiration_date", ""),
                                    premium=day.get("volume", 0) * day.get("close", 0) * 100,
                                    volume=day.get("volume", 0),
                                    open_interest=result.get("open_interest", 0),
                                    side="BUY",
                                )
                            )
            except Exception as e:
                logger.debug(f"Unusual options error: {e}")

        return flows

    async def _fetch_sector_performance(self) -> dict[str, float]:
        """Fetch sector ETF performance."""
        sectors = {
            "XLK": "Technology",
            "XLF": "Financials",
            "XLE": "Energy",
            "XLV": "Healthcare",
            "XLI": "Industrials",
            "XLC": "Communication",
            "XLY": "Consumer Disc",
            "XLP": "Consumer Staples",
            "XLU": "Utilities",
            "XLRE": "Real Estate",
            "XLB": "Materials",
        }
        result = {}

        if self._schwab_client:
            for etf, name in sectors.items():
                try:
                    quote = await self._schwab_client.get_quote(etf)
                    result[name] = quote.get("netPercentChangeInDouble", 0.0)
                except Exception:
                    pass

        return result

    async def get_symbol_analysis(self, symbol: str) -> dict[str, Any]:
        """Get comprehensive analysis data for a specific symbol."""
        result: dict[str, Any] = {"symbol": symbol}

        if self._schwab_client:
            try:
                quote = await self._schwab_client.get_quote(symbol)
                result["quote"] = {
                    "price": quote.get("lastPrice", 0),
                    "change_pct": quote.get("netPercentChangeInDouble", 0),
                    "volume": quote.get("totalVolume", 0),
                    "52w_high": quote.get("52WkHigh", 0),
                    "52w_low": quote.get("52WkLow", 0),
                }

                # Get near-term options chain
                chain = await self._schwab_client.get_option_chain(
                    symbol, days_to_expiration=45
                )
                result["options_chain_size"] = len(chain)
                if chain:
                    # Summarize key metrics
                    calls = [c for c in chain if c.option_type == "CALL"]
                    puts = [c for c in chain if c.option_type == "PUT"]
                    result["put_call_ratio"] = len(puts) / max(1, len(calls))
                    result["avg_iv"] = sum(c.implied_volatility for c in chain) / len(chain)
                    result["max_oi_call"] = max((c for c in calls), key=lambda x: x.open_interest, default=None)
                    result["max_oi_put"] = max((c for c in puts), key=lambda x: x.open_interest, default=None)
            except Exception as e:
                logger.debug(f"Symbol analysis error for {symbol}: {e}")

        return result
