"""
data_pipeline/nifty50.py — Nifty 50 universe metadata.

WHY THIS EXISTS:
  Sector information is a powerful feature. Knowing that HDFCBANK is in
  "Financial Services" lets us build sector-level aggregation features
  (e.g. "how is the banking sector doing today vs this stock?").
  This file is the single source of truth for our stock universe.
"""

from dataclasses import dataclass
from typing import Dict, List
import pandas as pd


@dataclass
class StockMeta:
    ticker: str          # yfinance ticker (with .NS suffix)
    name: str            # human-readable company name
    sector: str          # broad sector
    industry: str        # more specific industry
    nifty_weight: float  # approximate index weight (%)


# Full Nifty 50 metadata — sector grouping drives our graph features later
NIFTY50_META: Dict[str, StockMeta] = {
    "RELIANCE.NS":    StockMeta("RELIANCE.NS",    "Reliance Industries",       "Energy",              "Oil & Gas Refining",      9.8),
    "TCS.NS":         StockMeta("TCS.NS",          "Tata Consultancy Services", "Information Technology","IT Services",            8.2),
    "HDFCBANK.NS":    StockMeta("HDFCBANK.NS",     "HDFC Bank",                 "Financial Services",  "Private Banks",           7.1),
    "BHARTIARTL.NS":  StockMeta("BHARTIARTL.NS",   "Bharti Airtel",             "Communication",       "Telecom",                 3.8),
    "ICICIBANK.NS":   StockMeta("ICICIBANK.NS",     "ICICI Bank",                "Financial Services",  "Private Banks",           5.2),
    "INFY.NS":        StockMeta("INFY.NS",          "Infosys",                   "Information Technology","IT Services",            5.8),
    "SBIN.NS":        StockMeta("SBIN.NS",          "State Bank of India",        "Financial Services",  "Public Banks",            2.8),
    "HINDUNILVR.NS":  StockMeta("HINDUNILVR.NS",    "Hindustan Unilever",         "FMCG",               "Personal Products",       2.1),
    "ITC.NS":         StockMeta("ITC.NS",           "ITC Limited",               "FMCG",               "Tobacco & FMCG",          3.1),
    "LT.NS":          StockMeta("LT.NS",            "Larsen & Toubro",           "Capital Goods",       "Engineering",             3.2),
    "KOTAKBANK.NS":   StockMeta("KOTAKBANK.NS",     "Kotak Mahindra Bank",       "Financial Services",  "Private Banks",           2.9),
    "AXISBANK.NS":    StockMeta("AXISBANK.NS",      "Axis Bank",                 "Financial Services",  "Private Banks",           2.4),
    "WIPRO.NS":       StockMeta("WIPRO.NS",         "Wipro",                     "Information Technology","IT Services",            1.3),
    "HCLTECH.NS":     StockMeta("HCLTECH.NS",       "HCL Technologies",          "Information Technology","IT Services",            2.1),
    "ASIANPAINT.NS":  StockMeta("ASIANPAINT.NS",    "Asian Paints",              "Consumer Discretionary","Paints",                1.4),
    "MARUTI.NS":      StockMeta("MARUTI.NS",        "Maruti Suzuki",             "Consumer Discretionary","Automobiles",           1.8),
    "SUNPHARMA.NS":   StockMeta("SUNPHARMA.NS",     "Sun Pharmaceutical",        "Healthcare",          "Pharmaceuticals",         2.3),
    "ULTRACEMCO.NS":  StockMeta("ULTRACEMCO.NS",    "UltraTech Cement",          "Materials",           "Cement",                  1.7),
    "TITAN.NS":       StockMeta("TITAN.NS",         "Titan Company",             "Consumer Discretionary","Jewellery & Watches",   1.6),
    "BAJFINANCE.NS":  StockMeta("BAJFINANCE.NS",    "Bajaj Finance",             "Financial Services",  "NBFC",                    2.2),
    "NTPC.NS":        StockMeta("NTPC.NS",          "NTPC",                      "Utilities",           "Power Generation",        1.3),
    "POWERGRID.NS":   StockMeta("POWERGRID.NS",     "Power Grid Corp",           "Utilities",           "Power Transmission",      1.1),
    "ONGC.NS":        StockMeta("ONGC.NS",          "ONGC",                      "Energy",              "Oil & Gas Exploration",   1.4),
    "COALINDIA.NS":   StockMeta("COALINDIA.NS",     "Coal India",                "Energy",              "Coal Mining",             1.1),
    "NESTLEIND.NS":   StockMeta("NESTLEIND.NS",     "Nestle India",              "FMCG",               "Food Products",           0.9),
    "BAJAJFINSV.NS":  StockMeta("BAJAJFINSV.NS",    "Bajaj Finserv",             "Financial Services",  "NBFC",                    1.2),
    "M&M.NS":         StockMeta("M&M.NS",           "Mahindra & Mahindra",       "Consumer Discretionary","Automobiles",           1.7),
    "TECHM.NS":       StockMeta("TECHM.NS",         "Tech Mahindra",             "Information Technology","IT Services",            1.0),
    "ADANIENT.NS":    StockMeta("ADANIENT.NS",      "Adani Enterprises",         "Industrials",         "Conglomerate",            1.2),
    "ADANIPORTS.NS":  StockMeta("ADANIPORTS.NS",    "Adani Ports",               "Industrials",         "Ports & Logistics",       1.1),
    "JSWSTEEL.NS":    StockMeta("JSWSTEEL.NS",      "JSW Steel",                 "Materials",           "Steel",                   1.1),
    "TATASTEEL.NS":   StockMeta("TATASTEEL.NS",     "Tata Steel",                "Materials",           "Steel",                   1.0),
    "HINDALCO.NS":    StockMeta("HINDALCO.NS",      "Hindalco Industries",       "Materials",           "Aluminium",               1.0),
    "GRASIM.NS":      StockMeta("GRASIM.NS",        "Grasim Industries",         "Materials",           "Cement & Chemicals",      1.2),
    "CIPLA.NS":       StockMeta("CIPLA.NS",         "Cipla",                     "Healthcare",          "Pharmaceuticals",         1.0),
    "DRREDDY.NS":     StockMeta("DRREDDY.NS",       "Dr. Reddy's Laboratories",  "Healthcare",          "Pharmaceuticals",         1.1),
    "DIVISLAB.NS":    StockMeta("DIVISLAB.NS",      "Divi's Laboratories",       "Healthcare",          "Pharmaceuticals",         0.9),
    "EICHERMOT.NS":   StockMeta("EICHERMOT.NS",     "Eicher Motors",             "Consumer Discretionary","Automobiles",           0.9),
    "HEROMOTOCO.NS":  StockMeta("HEROMOTOCO.NS",    "Hero MotoCorp",             "Consumer Discretionary","Two-Wheelers",          0.8),
    "BPCL.NS":        StockMeta("BPCL.NS",          "BPCL",                      "Energy",              "Oil & Gas Refining",      0.9),
    "BRITANNIA.NS":   StockMeta("BRITANNIA.NS",     "Britannia Industries",      "FMCG",               "Food Products",           0.8),
    "TATACONSUM.NS":  StockMeta("TATACONSUM.NS",    "Tata Consumer Products",    "FMCG",               "Food & Beverages",        0.9),
    "APOLLOHOSP.NS":  StockMeta("APOLLOHOSP.NS",    "Apollo Hospitals",          "Healthcare",          "Hospitals",               1.0),
    "INDUSINDBK.NS":  StockMeta("INDUSINDBK.NS",    "IndusInd Bank",             "Financial Services",  "Private Banks",           1.0),
    "SHRIRAMFIN.NS":  StockMeta("SHRIRAMFIN.NS",    "Shriram Finance",           "Financial Services",  "NBFC",                    0.8),
    "SBILIFE.NS":     StockMeta("SBILIFE.NS",       "SBI Life Insurance",        "Financial Services",  "Insurance",               1.1),
    "HDFCLIFE.NS":    StockMeta("HDFCLIFE.NS",      "HDFC Life Insurance",       "Financial Services",  "Insurance",               1.0),
    "BAJAJ-AUTO.NS":  StockMeta("BAJAJ-AUTO.NS",    "Bajaj Auto",                "Consumer Discretionary","Two-Wheelers",          1.1),
    "BEL.NS":         StockMeta("BEL.NS",           "Bharat Electronics",        "Capital Goods",       "Defence Electronics",     0.8),
    "TRENT.NS":       StockMeta("TRENT.NS",         "Trent",                     "Consumer Discretionary","Retail",                0.9),
}


# ── Helper functions ────────────────────────────────────────────────────────────

def get_all_tickers() -> List[str]:
    """Return all 50 tickers."""
    return list(NIFTY50_META.keys())


def get_tickers_by_sector(sector: str) -> List[str]:
    """
    Example: get_tickers_by_sector("Information Technology")
    Returns: ['TCS.NS', 'INFY.NS', 'WIPRO.NS', 'HCLTECH.NS', 'TECHM.NS']
    """
    return [t for t, m in NIFTY50_META.items() if m.sector == sector]


def get_sectors() -> List[str]:
    """Return sorted list of unique sectors."""
    return sorted(set(m.sector for m in NIFTY50_META.values()))


def get_sector_map() -> Dict[str, str]:
    """Returns {ticker: sector} mapping — used to build sector-level features."""
    return {t: m.sector for t, m in NIFTY50_META.items()}


def get_metadata_df() -> pd.DataFrame:
    """Return all metadata as a DataFrame — useful for display and joins."""
    rows = []
    for ticker, meta in NIFTY50_META.items():
        rows.append({
            "ticker":       meta.ticker,
            "name":         meta.name,
            "sector":       meta.sector,
            "industry":     meta.industry,
            "nifty_weight": meta.nifty_weight,
        })
    return pd.DataFrame(rows).set_index("ticker")


if __name__ == "__main__":
    # Quick sanity check — run this file directly to verify
    df = get_metadata_df()
    print(f"Total stocks: {len(df)}")
    print(f"\nSectors:\n{df.groupby('sector')['nifty_weight'].sum().sort_values(ascending=False)}")
    print(f"\nSample:\n{df.head()}")
