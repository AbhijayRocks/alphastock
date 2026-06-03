// NIFTY 50 universe — mirrors backend data_pipeline/nifty50.py exactly.
// Source of truth for sector, name, weight. The frontend never invents this.

export const UNIVERSE = [
  { ticker: 'RELIANCE.NS',   name: 'Reliance Industries',       sector: 'Energy',              industry: 'Oil & Gas Refining',   weight: 9.8 },
  { ticker: 'TCS.NS',        name: 'Tata Consultancy Services', sector: 'Information Technology', industry: 'IT Services',         weight: 8.2 },
  { ticker: 'HDFCBANK.NS',   name: 'HDFC Bank',                 sector: 'Financial Services',  industry: 'Private Banks',        weight: 7.1 },
  { ticker: 'BHARTIARTL.NS', name: 'Bharti Airtel',             sector: 'Communication',       industry: 'Telecom',              weight: 3.8 },
  { ticker: 'ICICIBANK.NS',  name: 'ICICI Bank',                sector: 'Financial Services',  industry: 'Private Banks',        weight: 5.2 },
  { ticker: 'INFY.NS',       name: 'Infosys',                   sector: 'Information Technology', industry: 'IT Services',         weight: 5.8 },
  { ticker: 'SBIN.NS',       name: 'State Bank of India',       sector: 'Financial Services',  industry: 'Public Banks',         weight: 2.8 },
  { ticker: 'HINDUNILVR.NS', name: 'Hindustan Unilever',        sector: 'FMCG',                industry: 'Personal Products',    weight: 2.1 },
  { ticker: 'ITC.NS',        name: 'ITC Limited',               sector: 'FMCG',                industry: 'Tobacco & FMCG',       weight: 3.1 },
  { ticker: 'LT.NS',         name: 'Larsen & Toubro',           sector: 'Capital Goods',       industry: 'Engineering',          weight: 3.2 },
  { ticker: 'KOTAKBANK.NS',  name: 'Kotak Mahindra Bank',       sector: 'Financial Services',  industry: 'Private Banks',        weight: 2.9 },
  { ticker: 'AXISBANK.NS',   name: 'Axis Bank',                 sector: 'Financial Services',  industry: 'Private Banks',        weight: 2.4 },
  { ticker: 'WIPRO.NS',      name: 'Wipro',                     sector: 'Information Technology', industry: 'IT Services',         weight: 1.3 },
  { ticker: 'HCLTECH.NS',    name: 'HCL Technologies',          sector: 'Information Technology', industry: 'IT Services',         weight: 2.1 },
  { ticker: 'ASIANPAINT.NS', name: 'Asian Paints',              sector: 'Consumer Discretionary', industry: 'Paints',              weight: 1.4 },
  { ticker: 'MARUTI.NS',     name: 'Maruti Suzuki',             sector: 'Consumer Discretionary', industry: 'Automobiles',         weight: 1.8 },
  { ticker: 'SUNPHARMA.NS',  name: 'Sun Pharmaceutical',        sector: 'Healthcare',          industry: 'Pharmaceuticals',      weight: 2.3 },
  { ticker: 'ULTRACEMCO.NS', name: 'UltraTech Cement',          sector: 'Materials',           industry: 'Cement',               weight: 1.7 },
  { ticker: 'TITAN.NS',      name: 'Titan Company',             sector: 'Consumer Discretionary', industry: 'Jewellery & Watches', weight: 1.6 },
  { ticker: 'BAJFINANCE.NS', name: 'Bajaj Finance',             sector: 'Financial Services',  industry: 'NBFC',                 weight: 2.2 },
  { ticker: 'NTPC.NS',       name: 'NTPC',                      sector: 'Utilities',           industry: 'Power Generation',     weight: 1.3 },
  { ticker: 'POWERGRID.NS',  name: 'Power Grid Corp',           sector: 'Utilities',           industry: 'Power Transmission',   weight: 1.1 },
  { ticker: 'ONGC.NS',       name: 'ONGC',                      sector: 'Energy',              industry: 'Oil & Gas Exploration',weight: 1.4 },
  { ticker: 'COALINDIA.NS',  name: 'Coal India',                sector: 'Energy',              industry: 'Coal Mining',          weight: 1.1 },
  { ticker: 'NESTLEIND.NS',  name: 'Nestle India',              sector: 'FMCG',                industry: 'Food Products',        weight: 0.9 },
  { ticker: 'BAJAJFINSV.NS', name: 'Bajaj Finserv',             sector: 'Financial Services',  industry: 'NBFC',                 weight: 1.2 },
  { ticker: 'M&M.NS',        name: 'Mahindra & Mahindra',       sector: 'Consumer Discretionary', industry: 'Automobiles',         weight: 1.7 },
  { ticker: 'TECHM.NS',      name: 'Tech Mahindra',             sector: 'Information Technology', industry: 'IT Services',         weight: 1.0 },
  { ticker: 'ADANIENT.NS',   name: 'Adani Enterprises',         sector: 'Industrials',         industry: 'Conglomerate',         weight: 1.2 },
  { ticker: 'ADANIPORTS.NS', name: 'Adani Ports',               sector: 'Industrials',         industry: 'Ports & Logistics',    weight: 1.1 },
  { ticker: 'JSWSTEEL.NS',   name: 'JSW Steel',                 sector: 'Materials',           industry: 'Steel',                weight: 1.1 },
  { ticker: 'TATASTEEL.NS',  name: 'Tata Steel',                sector: 'Materials',           industry: 'Steel',                weight: 1.0 },
  { ticker: 'HINDALCO.NS',   name: 'Hindalco Industries',       sector: 'Materials',           industry: 'Aluminium',            weight: 1.0 },
  { ticker: 'GRASIM.NS',     name: 'Grasim Industries',         sector: 'Materials',           industry: 'Cement & Chemicals',   weight: 1.2 },
  { ticker: 'CIPLA.NS',      name: 'Cipla',                     sector: 'Healthcare',          industry: 'Pharmaceuticals',      weight: 1.0 },
  { ticker: 'DRREDDY.NS',    name: "Dr. Reddy's Laboratories",  sector: 'Healthcare',          industry: 'Pharmaceuticals',      weight: 1.1 },
  { ticker: 'DIVISLAB.NS',   name: "Divi's Laboratories",       sector: 'Healthcare',          industry: 'Pharmaceuticals',      weight: 0.9 },
  { ticker: 'EICHERMOT.NS',  name: 'Eicher Motors',             sector: 'Consumer Discretionary', industry: 'Automobiles',         weight: 0.9 },
  { ticker: 'HEROMOTOCO.NS', name: 'Hero MotoCorp',             sector: 'Consumer Discretionary', industry: 'Two-Wheelers',        weight: 0.8 },
  { ticker: 'BPCL.NS',       name: 'BPCL',                      sector: 'Energy',              industry: 'Oil & Gas Refining',   weight: 0.9 },
  { ticker: 'BRITANNIA.NS',  name: 'Britannia Industries',      sector: 'FMCG',                industry: 'Food Products',        weight: 0.8 },
  { ticker: 'TATACONSUM.NS', name: 'Tata Consumer Products',    sector: 'FMCG',                industry: 'Food & Beverages',     weight: 0.9 },
  { ticker: 'APOLLOHOSP.NS', name: 'Apollo Hospitals',          sector: 'Healthcare',          industry: 'Hospitals',            weight: 1.0 },
  { ticker: 'INDUSINDBK.NS', name: 'IndusInd Bank',             sector: 'Financial Services',  industry: 'Private Banks',        weight: 1.0 },
  { ticker: 'SHRIRAMFIN.NS', name: 'Shriram Finance',           sector: 'Financial Services',  industry: 'NBFC',                 weight: 0.8 },
  { ticker: 'SBILIFE.NS',    name: 'SBI Life Insurance',        sector: 'Financial Services',  industry: 'Insurance',            weight: 1.1 },
  { ticker: 'HDFCLIFE.NS',   name: 'HDFC Life Insurance',       sector: 'Financial Services',  industry: 'Insurance',            weight: 1.0 },
  { ticker: 'BAJAJ-AUTO.NS', name: 'Bajaj Auto',                sector: 'Consumer Discretionary', industry: 'Two-Wheelers',        weight: 1.1 },
  { ticker: 'BEL.NS',        name: 'Bharat Electronics',        sector: 'Capital Goods',       industry: 'Defence Electronics',  weight: 0.8 },
  { ticker: 'TRENT.NS',      name: 'Trent',                     sector: 'Consumer Discretionary', industry: 'Retail',              weight: 0.9 },
];

export const SECTORS = [...new Set(UNIVERSE.map((s) => s.sector))].sort();

export const META_BY_TICKER = Object.fromEntries(UNIVERSE.map((m) => [m.ticker, m]));

export const SECTOR_COLOR = {
  'Financial Services':      '#818CF8',
  'Information Technology':  '#38BDF8',
  'Energy':                  '#F4C45D',
  'FMCG':                    '#34D399',
  'Healthcare':              '#FB7185',
  'Consumer Discretionary':  '#A78BFA',
  'Materials':               '#FBBF24',
  'Communication':           '#22D3EE',
  'Industrials':             '#FB923C',
  'Utilities':               '#4ADE80',
  'Capital Goods':           '#F472B6',
};

// Single source of truth for horizons — mirrors backend/api/schemas.py.
// `days` is the trading-day count used in target shifts and projection math.
export const HORIZONS = [
  { value: '1d',  label: '1 Day',  short: '1D',  days: 1,  description: 'Intraday signal'  },
  { value: '5d',  label: '5 Day',  short: '5D',  days: 5,  description: 'Swing window'     },
  { value: '20d', label: '20 Day', short: '20D', days: 20, description: 'Position window'  },
];

export const HORIZON_BY_VALUE = Object.fromEntries(HORIZONS.map((h) => [h.value, h]));
export const horizonDays = (v) => HORIZON_BY_VALUE[v]?.days ?? 1;
export const horizonLabel = (v) => HORIZON_BY_VALUE[v]?.label ?? v;
export const isValidHorizon = (v) => Boolean(HORIZON_BY_VALUE[v]);
export const DEFAULT_HORIZON = '5d';

export const REGIME_META = {
  bull:     { label: 'Bull',        tone: 'bull',  description: 'Trending upward with low volatility. Momentum strategies favored.' },
  bear:     { label: 'Bear',        tone: 'bear',  description: 'Trending downward with elevated fear. Capital preservation is key.' },
  sideways: { label: 'Sideways',    tone: 'ink',   description: 'No clear trend. Range-bound, choppy. Breakout strategies preferred.' },
  crisis:   { label: 'Crisis',      tone: 'warn',  description: 'Extreme volatility. Correlations spike. High uncertainty.' },
  unknown:  { label: 'Unknown',     tone: 'ink',   description: 'Regime model not loaded.' },
};
