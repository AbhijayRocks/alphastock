"""
data_pipeline/news.py — Free, zero-cost sector & stock news via Google News RSS.

WHY THIS (and not NewsAPI):
  Google News exposes a standard RSS feed for any search query, India-localized,
  with NO API key, NO paid tier, and NO request quota. We fetch it with the
  standard library + requests (already a dependency), parse the items, and cache
  per query for ~15 minutes so we stay fast and polite. Cost: zero.

WHAT WE RETURN (and the ethics):
  Headline + source name + publish time + a short summary + a LINK back to the
  publisher. We never copy full article text — we surface the headline and link
  out, which is exactly what RSS is for. Always attribute and link to the source.
"""

import re
import time
import logging
from typing import Dict, List, Optional
from email.utils import parsedate_to_datetime
import xml.etree.ElementTree as ET

import requests

from data_pipeline.nifty50 import get_sectors, NIFTY50_META

logger = logging.getLogger(__name__)

_CACHE: Dict[str, tuple] = {}          # {key: (timestamp, [articles])}
_TTL = 900                             # 15 minutes
_UA = {"User-Agent": "Mozilla/5.0 (AlphaStock; news reader)"}
_BASE = "https://news.google.com/rss/search"

# Tuned India queries per sector; anything unknown falls back to a generic query.
SECTOR_QUERY = {
    "Information Technology":  "Indian IT sector stocks Infosys TCS Wipro HCLTech",
    "Financial Services":     "Indian banking financial sector stocks HDFC ICICI SBI",
    "Energy":                 "Indian energy oil gas sector stocks Reliance ONGC",
    "FMCG":                   "Indian FMCG sector stocks HUL ITC Nestle",
    "Healthcare":             "Indian pharma healthcare sector stocks Sun Pharma Cipla",
    "Materials":              "Indian metals materials cement sector stocks Tata Steel",
    "Consumer Discretionary": "Indian auto consumer discretionary sector stocks Maruti Titan",
    "Communication":          "Indian telecom sector stocks Bharti Airtel",
    "Capital Goods":          "Indian capital goods engineering sector stocks L&T",
    "Utilities":              "Indian power utilities sector stocks NTPC PowerGrid",
    "Industrials":            "Indian industrials sector stocks Adani",
}


def available_sectors() -> List[str]:
    """Sectors we can show news for (from the NIFTY-50 universe)."""
    return get_sectors()


def _query_for_sector(sector: str) -> str:
    return SECTOR_QUERY.get(sector, f"{sector} sector India stock market")


def _strip_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def _parse_rss(content: bytes, limit: int) -> List[Dict]:
    root = ET.fromstring(content)
    out: List[Dict] = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title", "") or "").strip()
        link = (item.findtext("link", "") or "").strip()
        pub = item.findtext("pubDate", "") or ""
        src_el = item.find("{*}source")
        source = (src_el.text if src_el is not None else "") or "News"
        desc = item.findtext("description", "") or ""

        # Google News titles are "Headline - Source"; drop the trailing source.
        if source and title.endswith(f" - {source}"):
            title = title[: -(len(source) + 3)].strip()

        published: Optional[str] = None
        try:
            published = parsedate_to_datetime(pub).isoformat() if pub else None
        except Exception:
            published = None

        if title and link:
            out.append({
                "headline":  title,
                "link":      link,
                "source":    source,
                "published": published,
                "summary":   _strip_html(desc)[:220],
            })
    return out


def _fetch(query: str, limit: int, cache_key: str) -> List[Dict]:
    now = time.time()
    cached = _CACHE.get(cache_key)
    if cached and (now - cached[0]) < _TTL:
        return cached[1]

    url = f"{_BASE}?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        r = requests.get(url, headers=_UA, timeout=12)
        r.raise_for_status()
        items = _parse_rss(r.content, limit)
    except Exception as e:
        logger.warning(f"News fetch failed ({query}): {e}")
        return cached[1] if cached else []

    if items:
        _CACHE[cache_key] = (now, items)
    return items


_VALID_RANGES = {"1h", "12h", "1d", "3d", "7d", "14d", "30d", "1y"}


def _normalize_range(time_range: Optional[str]) -> Optional[str]:
    """Validate a Google-News `when:` recency token (e.g. '1d', '7d'). None = all time."""
    if not time_range:
        return None
    r = str(time_range).lower().strip()
    return r if r in _VALID_RANGES else None


def fetch_sector_news(sector: str, limit: int = 20,
                      time_range: Optional[str] = None) -> List[Dict]:
    """
    Latest India news for a sector, cached ~15 min. `time_range` limits recency via
    Google News' `when:` operator ('1d','7d','30d', …); None = all time. [] on failure.
    """
    limit = max(1, min(int(limit), 40))
    query = _query_for_sector(sector)
    rng = _normalize_range(time_range)
    if rng:
        query = f"{query} when:{rng}"
    return _fetch(query, limit, f"sector:{sector}:{limit}:{rng or 'all'}")


def fetch_stock_news(ticker: str, limit: int = 12) -> List[Dict]:
    """Latest news for a single stock, queried by company name (NSE)."""
    limit = max(1, min(int(limit), 30))
    sym = ticker.replace("_NS", ".NS").replace("M_M", "M&M")
    meta = NIFTY50_META.get(sym)
    name = meta.name if meta else ticker
    return _fetch(f"{name} share price NSE India", limit, f"stock:{ticker}:{limit}")


if __name__ == "__main__":
    for s in ["Information Technology", "Healthcare"]:
        arts = fetch_sector_news(s, 3)
        print(f"\n{s}: {len(arts)} articles")
        for a in arts:
            print(" -", a["source"], "|", a["headline"][:70].encode("ascii", "ignore").decode())
