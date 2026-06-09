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

import os
import re
import json
import time
import logging
from typing import Dict, List, Optional
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor
import xml.etree.ElementTree as ET

import requests

from data_pipeline.nifty50 import get_sectors, NIFTY50_META

logger = logging.getLogger(__name__)

_CACHE: Dict[str, tuple] = {}          # {key: (timestamp, [articles])}
_TTL = 900                             # 15 minutes
_UA = {"User-Agent": "Mozilla/5.0 (AlphaStock; news reader)"}
_BASE = "https://news.google.com/rss/search"

# ── Google News link resolution ───────────────────────────────────────────────
# Since ~2024, the <link> in a Google News RSS item is an encoded redirect
# (news.google.com/rss/articles/CBMi…) that no longer bounces to the publisher —
# opened directly it just dumps the reader on Google News. We resolve each one to
# the real article URL via Google's batchexecute endpoint (the same call the
# Google News web client makes), cache the result for the life of the process,
# and fall back to the original link on any failure so behaviour never regresses.
_GN_HOST = "news.google.com"
_BATCH_URL = "https://news.google.com/_/DotsSplashUi/data/batchexecute"
_DECODE_CACHE: Dict[str, str] = {}     # {google_news_url: real_publisher_url}
_DECODE_ENABLED = os.getenv("ALPHASTOCK_DECODE_NEWS", "1").strip().lower() not in ("0", "false", "no")


def _gn_article_id(url: str) -> Optional[str]:
    """Extract the article id from a Google News RSS/read URL, else None."""
    try:
        parts = [p for p in urlparse(url).path.split("/") if p]
        for key in ("articles", "read"):
            if key in parts:
                i = parts.index(key)
                if i + 1 < len(parts):
                    return parts[i + 1]
    except Exception:
        pass
    return None


def _resolve_gn_url(url: str, timeout: int = 8) -> str:
    """Resolve one Google News link to the publisher URL; return `url` on failure."""
    if not url or _GN_HOST not in url:
        return url
    cached = _DECODE_CACHE.get(url)
    if cached:
        return cached
    art_id = _gn_article_id(url)
    if not art_id:
        return url
    try:
        # 1) Fetch the article shell to read its signature + timestamp.
        shell = requests.get(f"https://{_GN_HOST}/rss/articles/{art_id}",
                             headers=_UA, timeout=timeout)
        shell.raise_for_status()
        sig = re.search(r'data-n-a-sg="([^"]+)"', shell.text)
        ts  = re.search(r'data-n-a-ts="([^"]+)"', shell.text)
        if not (sig and ts):
            return url

        # 2) Ask the batchexecute endpoint to decode the id into the real URL.
        inner = json.dumps([
            "garturlreq",
            [["X", "X", ["X", "X"], None, None, 1, 1, "US:en", None, 1,
              None, None, None, None, None, 0, 1],
             "X", "X", 1, [1, 1, 1], 1, 1, None, 0, 0, None, 0],
            art_id, int(ts.group(1)), sig.group(1),
        ])
        payload = "f.req=" + requests.utils.quote(json.dumps([[["Fbv4je", inner]]]))
        headers = {**_UA, "content-type": "application/x-www-form-urlencoded;charset=UTF-8"}
        resp = requests.post(_BATCH_URL, headers=headers, data=payload, timeout=timeout)
        resp.raise_for_status()

        # The Fbv4je frame holds an escaped JSON string: ["garturlres","<url>",…].
        m = re.search(r'"Fbv4je","(.*?[^\\])"', resp.text, re.DOTALL)
        if not m:
            return url
        decoded = json.loads(json.loads(f'"{m.group(1)}"'))
        if isinstance(decoded, list) and len(decoded) > 1 and isinstance(decoded[1], str) \
                and decoded[1].startswith("http"):
            _DECODE_CACHE[url] = decoded[1]
            return decoded[1]
    except Exception as e:  # noqa: BLE001
        logger.debug(f"gnews decode failed ({art_id}): {e}")
    return url


def _resolve_links(items: List[Dict]) -> None:
    """Replace Google News redirect links with real article URLs, in place."""
    if not _DECODE_ENABLED:
        return
    targets = [it for it in items if _GN_HOST in (it.get("link") or "")]
    if not targets:
        return
    with ThreadPoolExecutor(max_workers=min(8, len(targets))) as pool:
        resolved = list(pool.map(lambda it: _resolve_gn_url(it["link"]), targets))
    for it, real in zip(targets, resolved):
        it["link"] = real

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
        _resolve_links(items)   # Google News redirect → real publisher URL
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
