<h1 align="center">AlphaStock</h1>
<p align="center">
  <strong>A full-stack analytics platform for NIFTY 50 equities</strong><br/>
  Predictive signals, market-regime context, portfolio optimization, and walk-forward backtesting — in one professional terminal.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat-square&logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-0.109+-009688?style=flat-square&logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/Vite-8-646CFF?style=flat-square&logo=vite&logoColor=white" />
  <img src="https://img.shields.io/badge/TailwindCSS-3.4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white" />
  <img src="https://img.shields.io/badge/License-MIT-green?style=flat-square" />
</p>

---

AlphaStock turns a decade of NSE market history into clear, explainable analytics for the **NIFTY 50**. A high-performance **FastAPI** backend serves direction/return forecasts, factor attribution, market-regime detection, portfolio optimization, and backtests; a premium dark-mode **React + Vite** frontend presents them as a trading-desk–grade terminal with authentication, a personal watchlist, a screener, and a command palette.

> **Offline-first:** if the API is unreachable, the frontend transparently serves the last known analytics so the workspace always renders. Ports are fully environment-driven — nothing is hardcoded.

---

## ✨ Features

- **Multi-horizon forecasts** — direction (UP/DOWN), expected return, probability, and a confidence interval across **1-day**, **5-day**, and **20-day** horizons, with a `strong / moderate / weak` signal strength.
- **Factor attribution** — every forecast ships with the key factors driving it, ranked by contribution, plus a plain-English thesis. Full transparency, no black boxes.
- **Market regime** — automatic Bull / Bear / Sideways / Crisis detection that maps to an actionable desk stance (Risk-On / Neutral / Risk-Off / Defensive).
- **Portfolio optimizer** — mean-variance (Markowitz) allocation with dynamic conditional covariance and a configurable risk multiplier, returning per-asset weights, sector breakdown, and a written summary.
- **Walk-forward backtest** — time-series-aware splits vs. a buy-and-hold benchmark, reporting Sharpe, Calmar, max drawdown, hit rate, and excess return.
- **Market screener** — filter and sort the full NIFTY 50 by direction, strength, sector, and expected return, with CSV export.
- **Accounts & personalization** — JWT sign-in, per-user watchlist and preferences (SQLite by default, Postgres-ready).
- **Premium UX** — consistent green/red/neutral P&L system, animated charts, command palette (`⌘K`), keyboard navigation, and responsive layouts.

---

## 🏗️ Project structure

```
alpha_stock/
├── backend/                     # FastAPI service + ML pipeline
│   ├── api/
│   │   ├── main.py              # App entry point, lifespan, CORS, `python -m api.main`
│   │   ├── routes.py            # Core endpoints (predict/explain/backtest/…)
│   │   ├── model_registry.py    # Model loading, prediction, attribution, backtest
│   │   └── schemas.py           # Pydantic request/response models
│   ├── auth/                    # Accounts: JWT, password hashing, SQLAlchemy models
│   ├── models/                  # ML model definitions (classifier, ensemble, portfolio, …)
│   ├── features/                # Feature engineering (technical, regime, selection)
│   ├── data_pipeline/           # yFinance ingestion, NIFTY 50 universe, news sentiment
│   ├── training/                # Training loop + backtest engine
│   ├── config.py                # Central config — HOST / PORT / RELOAD are env-driven
│   ├── requirements.txt
│   └── .env.example
│
├── frontend/                    # React 19 + Vite 8 terminal
│   ├── src/
│   │   ├── App.jsx              # Routing + app shell
│   │   ├── api/                 # Typed API client (+ offline fallback) & auth
│   │   ├── pages/               # Dashboard, Screener, Analysis, Portfolio, Backtest, Settings, Login
│   │   ├── components/
│   │   │   ├── shell/           # Sidebar, Topbar, TickerTape, CommandPalette, Footer
│   │   │   ├── domain/          # RegimeBanner, DirectionPill, HorizonSwitcher, ShapBars
│   │   │   ├── charts/          # AreaChart, AllocationDonut, Sparkline
│   │   │   └── ui/              # Buttons, cards, tabs, inputs, toasts, …
│   │   └── context/             # App + Auth providers
│   ├── vite.config.js           # Port read from VITE_PORT / PORT (default 4000)
│   └── .env.example
│
├── README.md
└── SETUP.md                     # Detailed environment + model setup
```

---

## 🛠️ Tech stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, Vite 8, TailwindCSS 3.4, Framer Motion, Recharts, Axios, React Router 7 |
| **Backend** | Python 3.11, FastAPI, Uvicorn, Pydantic v2, SQLAlchemy |
| **Machine learning** | scikit-learn, LightGBM, XGBoost, SHAP, Optuna |
| **Regime / NLP** | hmmlearn (Hidden Markov Models), Hugging Face Transformers (FinBERT) |
| **Data** | yFinance, Pandas, NumPy, PyArrow, pandas-ta (130+ indicators) |
| **Auth** | JWT (HS256) + PBKDF2 — standard-library only, SQLite by default |

---

## 🚀 Getting started

### Prerequisites
- **Python** 3.11
- **Node.js** 18+
- **Git**

### 1. Clone

```bash
git clone https://github.com/pansariabhijay-source/Stock_Web_App.git
cd Stock_Web_App
```

### 2. Backend (FastAPI)

```bash
cd backend

# Create & activate a virtual environment
python -m venv .venv
# Windows:        .\.venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt

# Optional: copy the env template and adjust ports / keys
cp .env.example .env

# Run (honors HOST / PORT / RELOAD; defaults to 0.0.0.0:9000)
python -m api.main
# …or, equivalently:
# uvicorn api.main:app --reload --port 9000
```

Interactive API docs: **http://localhost:9000/docs**

> A zero-config SQLite database (`backend/alpha_stock.db`) and a dev auth secret are created automatically on first launch. See [SETUP.md](SETUP.md) for data ingestion, GPU/CUDA notes, model training, and Postgres.

### 3. Frontend (Vite + React)

In a new terminal:

```bash
cd frontend
npm install

# Optional: copy the env template (sets port + API base)
cp .env.example .env

npm run dev
```

Open the terminal at **http://localhost:4000**.

---

## ⚙️ Configuration

Both halves are environment-driven, so the same code runs locally, in Docker, and on a host like Render without edits. All variables are optional — sensible defaults apply.

### Backend (`backend/.env`)

| Variable | Description | Default |
|---|---|---|
| `HOST` | Interface to bind | `0.0.0.0` |
| `PORT` | API port (Render injects this) | `9000` |
| `RELOAD` | Auto-reload on changes (dev only) | `false` |
| `ALPHASTOCK_SECRET` | Stable JWT signing secret for production | auto-generated in dev |
| `DATABASE_URL` | Use Postgres instead of SQLite | SQLite file |
| `NEWS_API_KEY`, `HF_TOKEN`, `HF_REPO_ID` | Optional integrations | — |

### Frontend (`frontend/.env`)

| Variable | Description | Default |
|---|---|---|
| `VITE_PORT` | Dev/preview server port | `4000` |
| `VITE_API_BASE` | Backend base URL (include `/api`) | `http://localhost:9000/api` |

---

## 🔌 API endpoints

All routes are prefixed with `/api`; interactive Swagger lives at `/docs`.

### Analytics

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/predict` | Directional forecast with probability, expected return, and confidence interval |
| `POST` | `/api/explain` | Top factor attribution + plain-English interpretation |
| `POST` | `/api/backtest` | Walk-forward strategy simulation vs. buy-and-hold |
| `POST` | `/api/optimize_portfolio` | Mean-variance allocation with risk tolerance |
| `GET` | `/api/models` | Stocks with trained models, sectors, and accuracy |
| `GET` | `/api/prices` | Current prices and 1-day % change |
| `GET` | `/api/history/{ticker}` | Historical closing prices (configurable `days`) |
| `GET` | `/api/regime` | Detected market regime |
| `GET` | `/api/health` | Service health and coverage |

### Accounts

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/auth/register` | Create an account → returns a JWT |
| `POST` | `/api/auth/login` | Authenticate → returns a JWT |
| `GET` / `PATCH` | `/api/auth/me` | Current account / update display name |
| `GET` / `PUT` | `/api/user/data` | Fetch / persist watchlist & preferences |

---

## 📦 Production build

```bash
cd frontend
npm run build      # outputs static assets to frontend/dist
npm run preview    # serve the build locally on VITE_PORT
```

Serve `frontend/dist` from any static host (or behind the same origin as the API) and run the backend with a production `ALPHASTOCK_SECRET` and `PORT`.

---

## 📝 License

Released under the [MIT License](LICENSE).

---

<p align="center">
  Built by <strong>Abhijay Pansari</strong> , <strong>Gagan C</strong> , <strong>Abhishek Singh</strong> · ⭐ star the repo if it's useful.
</p>
