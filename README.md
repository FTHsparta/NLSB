# NLSB — Natural Language Strategy Backtester

> A backtesting tool that tells you when your strategy is fooling you.

![Status](https://img.shields.io/badge/status-in%20development-yellow)
![Python](https://img.shields.io/badge/python-3.11-blue)
![License](https://img.shields.io/badge/license-MIT-green)
A web-based backtesting tool where users describe a trading strategy in plain English. The system translates the description into executable code, runs it against historical price data, and returns standard performance metrics plus an honest overfitting assessment.

The Problem: Most retail traders lose money. They backtest against the market and when they see good looking results, they naturally believe they will continue. Unfortunately, this doesn't happen to be the case due to overfit strategies, ignored transaction costs, and survivorship bais. I started this project after seeing my peers try, in vain, to "daytrade" and following viral tiktok strategies to try and make money quick. Existing backtesting tools either cost hundreds of dollars per month, require coding expertise that most retail traders don't have, or mislead consumers on their strategy. NLSB is a backtester that gives honest results that don't hinder you financially. 

What it does: Accepts strategy in plain english ("buy SPY when RSI drops below 30 and the 50-day MA is above the 200-day; sell when RSI exceeds 70")
              Translates the description into an executable strategy using LLM 
              Runs the strategy into historical price data for stocks/ETFs and crypto
              Returns standard performance metric (Sharpe ratio, RSI) along with delivering an honest robust assessment of your strategy (walk-forward validation results, parameter sensitivity analysis, and a deflated                     Sharpe ratio that accounts for overfitting)

What differentiates NLSB from other backtesters is that it doesn't optimize to show you a green line. Specifically, the robustness detector flags: Overfitting- Strategies whose performance collapses out-of-sample
                           Parameter fragility — strategies that only work for one narrow set of parameters
                           Regime dependence — strategies that only worked during specific market conditions (e.g., the                                2020-2021 bull run)
                           Hidden costs — strategies that look profitable until you model realistic transaction costs
How it works: 1. User submits a strategy description in natural language
              2. LLM translates the description into a structured strategy with various verification steps that confirm the                     translation matches user intent
              3. The strategy is executed against historical data using a Python backtesting engine
              4. Standard metrics are computed
              5. The robustness layer runs validation, parameter sweeps, and statistical adjustments to flag overfitting
              6. Results are returned to the frontend with both the optimistic and honeste views
Tech Stack: Backend - Python 3.11, FastAPI
            Backtesting engine: vectorbt
            Market data: yfinance (equities), ccxt (crypto)
            LLM: Antrhopic Claude API
            Frontend: Next.js, Tailwind CSS, Recharts
            Deployment: Vercel (frontend), Railway (backend) 
Project status
In active development (Summer 2026). Currently working on:

 Project scoping and architecture
 Backtesting engine integration
 LLM strategy translation pipeline
 Overfitting detection layer
 Frontend MVP
 Live demo deployment
 Investigation: testing popular day-trading strategies for robustness

See LOG.md for build notes and design decisions.
References
This project's robustness methodology draws on academic work on backtest overfitting, particularly:

Bailey, Borwein, Lopez de Prado, Zhu (2014). The Probability of Backtest Overfitting.
Lopez de Prado (2018). Advances in Financial Machine Learning.
            
