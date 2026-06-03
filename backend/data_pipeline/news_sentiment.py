"""
data_pipeline/news_sentiment.py — Financial news sentiment scoring via FinBERT.

WHAT IS FinBERT?
  FinBERT is a BERT model fine-tuned specifically on financial text (earnings
  calls, analyst reports, financial news). Unlike general-purpose sentiment
  models, it understands finance-specific language:
    "The company missed estimates" -> negative (general BERT might miss this)
    "Guidance was revised upward"  -> positive
    "Margin compression persists"  -> negative

WHY SENTIMENT MATTERS:
  Stock prices are driven by human expectations. News changes expectations.
  On days when strongly negative news hits a stock, our model should widen
  its prediction interval and bias toward downside. This is exactly the kind
  of external signal that pure price-based models completely miss.

DATA SOURCE:
  NewsAPI (free tier: 100 requests/day, 1 month history).
  We fetch headlines for each Nifty 50 company name + "India stock market".
  One sentiment score per stock per day — aggregated from all headlines.

ARCHITECTURE:
  NewsAPI -> raw headlines -> FinBERT -> sentiment score [-1, +1]
  -> saved as daily Parquet -> joined in features/pipeline.py

NOTE ON FREE TIER LIMITS:
  100 requests/day means we can cover ~3-4 stocks per day fully, or
  use broad market queries to get index-level sentiment cheaply.
  Strategy: fetch market-wide sentiment daily, stock-specific weekly.
"""

import logging
import time
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import requests
import torch
from transformers import AutoTokenizer, AutoModelForSequenceClassification

from config import NEWS_API_KEY, FEATURES_DIR, LOG_LEVEL

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s | %(levelname)s | %(message)s")
logger = logging.getLogger(__name__)

SENTIMENT_DIR = FEATURES_DIR / "sentiment"
SENTIMENT_DIR.mkdir(parents=True, exist_ok=True)

# FinBERT model — downloads once (~400MB), cached by HuggingFace locally
FINBERT_MODEL = "ProsusAI/finbert"
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ── FinBERT Scorer ─────────────────────────────────────────────────────────────

class FinBERTScorer:
    """
    Wrapper around FinBERT for batch sentiment scoring.

    Loads the model once and keeps it in memory for the session.
    On first call, downloads ~400MB from HuggingFace (cached after that).

    Output scores:
      +1.0 = strongly positive
       0.0 = neutral
      -1.0 = strongly negative
    """

    def __init__(self):
        self._model     = None
        self._tokenizer = None

    def _load(self):
        """Lazy load — only downloads/loads model when first needed."""
        if self._model is None:
            logger.info(f"Loading FinBERT model ({FINBERT_MODEL}) — first time takes ~30s...")
            self._tokenizer = AutoTokenizer.from_pretrained(FINBERT_MODEL)
            self._model     = AutoModelForSequenceClassification.from_pretrained(FINBERT_MODEL)
            self._model.to(DEVICE)
            self._model.eval()
            logger.info(f"FinBERT loaded on {DEVICE}")

    def score_texts(self, texts: List[str], batch_size: int = 16) -> List[float]:
        """
        Score a list of text strings, returns float scores in [-1, +1].

        FinBERT outputs 3 classes: positive, negative, neutral.
        We convert to a single score: positive_prob - negative_prob.
        This gives a continuous signal instead of a discrete label.

        Args:
            texts     : list of headlines or sentences
            batch_size: process N texts at a time (memory vs speed tradeoff)

        Returns:
            list of float scores, same length as texts
        """
        self._load()
        scores = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]

            # Tokenize — truncate long texts to 512 tokens (BERT limit)
            inputs = self._tokenizer(
                batch,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            ).to(DEVICE)

            with torch.no_grad():
                outputs = self._model(**inputs)

            # Softmax gives probabilities across [positive, negative, neutral]
            probs = torch.softmax(outputs.logits, dim=-1).cpu().numpy()

            # FinBERT label order: positive=0, negative=1, neutral=2
            # Score = positive_prob - negative_prob (range: -1 to +1)
            batch_scores = (probs[:, 0] - probs[:, 1]).tolist()
            scores.extend(batch_scores)

        return scores

    def score_single(self, text: str) -> float:
        """Score a single text string."""
        return self.score_texts([text])[0]


# Global singleton — load once, reuse everywhere
_scorer: Optional[FinBERTScorer] = None

def get_scorer() -> FinBERTScorer:
    global _scorer
    if _scorer is None:
        _scorer = FinBERTScorer()
    return _scorer


# ── NewsAPI Fetching ───────────────────────────────────────────────────────────

def fetch_market_news(
    query: str = "India stock market Nifty NSE",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    max_articles: int = 50,
) -> List[Dict]:
    """
    Fetch financial news headlines from NewsAPI.

    Free tier limits:
      - 100 requests per day
      - Only last 30 days of articles
      - 100 articles per request max

    Args:
        query       : search query string
        from_date   : YYYY-MM-DD string, defaults to 7 days ago
        to_date     : YYYY-MM-DD string, defaults to today
        max_articles: cap to avoid burning API quota

    Returns:
        list of article dicts with keys: title, description, publishedAt, source
    """
    if not NEWS_API_KEY:
        logger.warning("NEWS_API_KEY not set in .env — returning empty news")
        return []

    if from_date is None:
        from_date = (date.today() - timedelta(days=7)).strftime("%Y-%m-%d")
    if to_date is None:
        to_date = date.today().strftime("%Y-%m-%d")

    url = "https://newsapi.org/v2/everything"
    params = {
        "q":          query,
        "from":       from_date,
        "to":         to_date,
        "language":   "en",
        "sortBy":     "publishedAt",
        "pageSize":   min(max_articles, 100),
        "apiKey":     NEWS_API_KEY,
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if data.get("status") != "ok":
            logger.warning(f"NewsAPI error: {data.get('message', 'unknown')}")
            return []

        articles = data.get("articles", [])
        logger.info(f"Fetched {len(articles)} articles for query: '{query}'")
        return articles

    except Exception as e:
        logger.error(f"NewsAPI fetch failed: {e}")
        return []


def fetch_stock_news(ticker: str, company_name: str, days_back: int = 7) -> List[Dict]:
    """
    Fetch news specific to one stock using company name as query.

    We use company name (not ticker) because news articles say
    "Reliance Industries" not "RELIANCE.NS".
    """
    # Strip ".NS" suffix, use clean name
    clean_name = company_name.split()[0]  # e.g. "Reliance" from "Reliance Industries"
    query = f"{clean_name} India stock NSE"

    from_date = (date.today() - timedelta(days=days_back)).strftime("%Y-%m-%d")
    return fetch_market_news(query=query, from_date=from_date, max_articles=20)


# ── Sentiment Aggregation ──────────────────────────────────────────────────────

def articles_to_daily_sentiment(articles: List[Dict]) -> pd.Series:
    """
    Convert a list of news articles to a daily sentiment score.

    Process:
      1. Extract title + description for each article
      2. Score each with FinBERT
      3. Group by publish date
      4. Average score per day (weighted by recency — newer = more weight)

    Returns:
      pd.Series indexed by date, values in [-1, +1]
    """
    if not articles:
        return pd.Series(dtype=float, name="sentiment")

    scorer = get_scorer()
    rows = []

    texts = []
    dates = []

    for article in articles:
        title = article.get("title", "") or ""
        desc  = article.get("description", "") or ""
        text  = f"{title}. {desc}".strip(". ")

        if not text or text == ".":
            continue

        pub = article.get("publishedAt", "")
        try:
            pub_date = pd.to_datetime(pub).date()
        except Exception:
            continue

        texts.append(text)
        dates.append(pub_date)

    if not texts:
        return pd.Series(dtype=float, name="sentiment")

    scores = scorer.score_texts(texts)

    df = pd.DataFrame({"date": dates, "score": scores})
    df["date"] = pd.to_datetime(df["date"])

    # Daily average sentiment
    daily = df.groupby("date")["score"].mean()
    daily.name = "sentiment"
    daily.index.name = "date"

    return daily


def compute_market_sentiment(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
) -> pd.DataFrame:
    """
    Compute daily market-wide sentiment score from broad market news.

    This is the "macro sentiment" feature — how is the overall market
    feeling today? Used as a feature for ALL stocks.

    Returns:
        DataFrame with columns: [market_sentiment, market_sentiment_5d_avg]
    """
    logger.info("Computing market-wide sentiment...")

    queries = [
        "India stock market NSE Nifty",
        "BSE Sensex India economy",
        "RBI monetary policy India",
        "India GDP inflation rupee",
    ]

    all_articles = []
    for q in queries:
        articles = fetch_market_news(query=q, from_date=start_date, to_date=end_date)
        all_articles.extend(articles)
        time.sleep(0.5)  # rate limit courtesy

    daily = articles_to_daily_sentiment(all_articles)

    if daily.empty:
        logger.warning("No sentiment data fetched — returning zeros")
        return pd.DataFrame()

    result = daily.to_frame("market_sentiment")
    result["market_sentiment_5d_avg"] = result["market_sentiment"].rolling(5).mean()

    # Forward fill gaps (weekends, holidays)
    result = result.resample("D").mean().ffill()

    # Save to disk
    path = SENTIMENT_DIR / "market_sentiment.parquet"
    result.to_parquet(path, engine="pyarrow", compression="snappy")
    logger.info(f"Market sentiment saved: {result.shape} -> {path}")

    return result


def compute_stock_sentiment(
    ticker: str,
    company_name: str,
    days_back: int = 30,
) -> pd.Series:
    """
    Compute daily sentiment for a specific stock.

    Returns pd.Series of daily sentiment scores.
    """
    logger.info(f"Computing sentiment for {ticker} ({company_name})...")

    articles = fetch_stock_news(ticker, company_name, days_back=days_back)
    daily = articles_to_daily_sentiment(articles)

    if not daily.empty:
        path = SENTIMENT_DIR / f"{ticker.replace('.', '_')}_sentiment.parquet"
        daily.to_frame("sentiment").to_parquet(path, engine="pyarrow", compression="snappy")

    return daily


def load_sentiment(name: str = "market_sentiment") -> pd.DataFrame:
    """Load saved sentiment data from disk."""
    path = SENTIMENT_DIR / f"{name}.parquet"
    if not path.exists():
        logger.warning(f"No sentiment file at {path}")
        return pd.DataFrame()
    df = pd.read_parquet(path, engine="pyarrow")
    df.index = pd.to_datetime(df.index)
    return df


def get_fallback_sentiment(index: pd.DatetimeIndex) -> pd.DataFrame:
    """
    Returns a neutral sentiment DataFrame when NewsAPI is unavailable.
    Ensures the pipeline never breaks even without news data.
    All zeros = neutral sentiment — model treats it as no news signal.
    """
    df = pd.DataFrame(
        {"market_sentiment": 0.0, "market_sentiment_5d_avg": 0.0},
        index=index
    )
    return df


if __name__ == "__main__":
    # Quick test — scores a few financial headlines
    scorer = get_scorer()

    headlines = [
        "Reliance Industries reports record quarterly profit, beats estimates",
        "HDFC Bank shares fall as NPA concerns mount amid slowdown",
        "RBI holds rates steady, market reaction muted",
        "Infosys upgrades guidance, sees strong demand from US clients",
        "India VIX surges to 3-month high amid global selloff",
    ]

    scores = scorer.score_texts(headlines)
    for h, s in zip(headlines, scores):
        sentiment_label = "POSITIVE" if s > 0.1 else ("NEGATIVE" if s < -0.1 else "NEUTRAL")
        print(f"{sentiment_label:10} ({s:+.3f})  {h[:70]}")
