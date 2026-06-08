# AlphaStock: Executive Presentation Report

## 1. Project Overview
AlphaStock is a full-stack, AI-driven quantitative analytics platform designed for the NIFTY 50. It transforms over a decade of raw market data into actionable trading intelligence, providing users with a professional-grade terminal for portfolio management and risk analysis.

## 2. Technology Stack (How We Built It)
We utilized a decoupled architecture to ensure maximum performance and scalability:
- **Frontend (UI/UX):** Built with **React 19** and **Vite 8**, featuring a premium dark-mode interface styled with **TailwindCSS 3.4**. It includes offline-first resilience so the terminal functions even if the connection drops.
- **Backend (API):** Engineered in **Python 3.12** using **FastAPI** for high-speed, asynchronous data delivery.
- **Database:** **PostgreSQL** handles user accounts, watchlists, and secure preferences, integrated via SQLAlchemy.
- **Infrastructure:** The application is fully containerized with **Docker** and deployed continuously via **Vercel** (Frontend) and **Render** (Backend).

## 3. Data Pipeline & Market Context
- **Data Sourcing:** Historical pricing and volume ingested via `yfinance`; real-time market sentiment via `newsapi`.
- **Feature Engineering:** We compute over 130 technical indicators (e.g., RSI, MACD, Volatility bands) using `pandas-ta`.
- **Regime Detection:** We use **Hidden Markov Models (HMM)** to automatically classify the market into states (Bull, Bear, Sideways, Crisis), allowing models to adapt dynamically to market conditions.

## 4. Artificial Intelligence & Predictive Models
We discarded simple moving averages in favor of an institutional-grade machine learning pipeline:

- **Tree-Based Ensembles (XGBoost & LightGBM):** Used for highly accurate, non-linear classification of directional movement (UP/DOWN) across 1-day, 5-day, and 20-day horizons.
- **Temporal Fusion Transformers (TFTs):** A state-of-the-art deep learning model tailored for time-series forecasting. TFTs analyze past prices and static covariates (like sector) to output predictions with a strict *confidence interval*, essential for institutional risk management.
- **Model Explainability (SHAP):** We use SHAP values to "open the black box." Every prediction includes an explanation (e.g., "Expected to rise due to oversold RSI and positive momentum"), ensuring complete transparency for analysts.

## 5. Portfolio Optimization & Backtesting
- **Optimization:** Markowitz Mean-Variance optimization dynamically allocates asset weights based on the user's risk tolerance to maximize the Sharpe ratio.
- **Backtesting:** A robust walk-forward simulation engine prevents data leakage, reporting key metrics (Max Drawdown, Calmar Ratio, Excess Return) against a Buy-and-Hold benchmark.

## 6. Future Roadmap (Advanced Risk Modeling)
To elevate AlphaStock to the next level of quantitative risk management, we are integrating:
- **Merton Jump Diffusion (MJD) Models:** To account for sudden market shocks and "jumps" caused by unpredictable macroeconomic news.
- **Monte Carlo Simulations:** To generate thousands of future price paths using the MJD framework, calculating accurate Value at Risk (VaR) and Expected Shortfall for extreme scenario planning.

---
*Prepared for Organizational Review.*
