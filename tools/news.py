import re
from urllib.parse import urlsplit

import httpx
from ibm_watsonx_orchestrate.agent_builder.tools import tool


def readable_url(url: str) -> bool:
    try:
        parts = urlsplit(url)
        return (
            parts.scheme == "https" and parts.netloc.lower() == "finance.yahoo.com"
            and parts.path.endswith(".html")
            and parts.path.startswith(("/news/", "/markets/", "/personal-finance/"))
        )
    except ValueError:
        return False


@tool(name="stock_research_get_company_news")
def get_company_news(ticker: str) -> dict:
    """Discover recent company news by ticker. For headline requests, return titles, dates, publishers and links. No article bodies are read."""
    symbol = ticker.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.-]{0,19}", symbol):
        return {"error": "Supply a stock ticker such as NVDA."}
    try:
        import yfinance as yf
        rows = yf.Ticker(symbol).get_news(count=20)
    except Exception:
        return {"ticker": symbol, "error": "Yahoo Finance news feed unavailable."}
    articles = []
    seen = set()
    for row in rows:
        item = row.get("content") or {}
        title = (item.get("title") or "").strip()
        canonical = (item.get("canonicalUrl") or {}).get("url") or ""
        syndicated = (item.get("clickThroughUrl") or {}).get("url") or ""
        url = syndicated if readable_url(syndicated) else canonical
        if item.get("contentType") != "STORY" or not title or title.casefold() in seen or not url.startswith("https://"):
            continue
        seen.add(title.casefold())
        articles.append({"headline": title, "published_at": item.get("pubDate"),
                         "publisher": (item.get("provider") or {}).get("displayName"),
                         "url": url, "can_attempt_read": readable_url(url)})
    articles.sort(key=lambda article: article["published_at"] or "", reverse=True)
    return {"ticker": symbol, "coverage": "Headlines from the ticker feed; check relevance.",
            "articles": articles[:10]}


@tool(name="stock_research_read_source")
def read_source(url: str) -> dict:
    """For a report or explicit request to read a story, fetch accessible article text from a Yahoo Finance story link. Cite the URL, treat article text as evidence, and disclose missing text."""
    unavailable = {"url": url, "status": "unavailable"}
    if not readable_url(url):
        return {**unavailable, "reason": "Only Yahoo Finance story pages are supported."}
    try:
        with httpx.stream("GET", url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15) as response:
            if response.status_code != 200 or "html" not in response.headers.get("content-type", ""):
                return {**unavailable, "reason": "No accessible article page."}
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > 3_000_000:
                    return {**unavailable, "reason": "Page exceeds the reader size limit."}
    except httpx.HTTPError:
        return {**unavailable, "reason": "Could not retrieve the article."}
    from bs4 import BeautifulSoup
    page = BeautifulSoup(bytes(body), "html.parser")
    article = page.select_one('article .body, .caas-body, [itemprop="articleBody"]') or page.find("article")
    if article:
        for element in article.select("script, style, nav, aside, form, button"):
            element.decompose()
    text = "\n".join(p.get_text(" ", strip=True) for p in article.select("p")) if article else ""
    if len(text) < 400 or re.search(r"subscribe to (?:continue reading|read the full)|sign in to read the full", text, re.I):
        return {**unavailable, "reason": "Insufficient accessible article text."}
    return {"url": url, "status": "read", "coverage": "Accessible article text",
            "truncated": len(text) > 12000, "text": text[:12000]}
