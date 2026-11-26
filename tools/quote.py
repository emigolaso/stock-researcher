from datetime import datetime, timezone
import re

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool


@tool(name="stock_research_get_stock_quote")
def get_stock_quote(ticker: str) -> dict:
    """Look up the latest regular-session share price. Include currency, quote time and source in the answer."""
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,19}", symbol):
        return {"error": "Please supply a stock ticker, such as IBM."}

    try:
        response = httpx.get(
            f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            params={"interval": "1d", "range": "1d"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=10,
        )
        response.raise_for_status()
        quote = response.json()["chart"]["result"][0]["meta"]
        price = quote["regularMarketPrice"]
        currency = quote["currency"]
        timestamp = datetime.fromtimestamp(quote["regularMarketTime"], timezone.utc)
        if quote["symbol"].upper() != symbol or not isinstance(price, (float, int)) or not currency:
            raise ValueError("Incomplete quote")
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, OverflowError):
        return {"ticker": symbol, "error": "Yahoo Finance could not provide a verified quote."}

    return {"ticker": symbol, "price": price, "currency": currency,
            "as_of_utc": timestamp.isoformat(), "source": f"https://finance.yahoo.com/quote/{symbol}/"}
