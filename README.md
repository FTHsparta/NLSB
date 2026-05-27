# NLSB
A web-based backtesting tool where users describe a trading strategy in plain English. The system translates the description into executable code, runs it against historical price data, and returns standard performance metrics plus an honest overfitting assessment.

The Problem: Most retail traders lose money. They backtest against the market and when they see good looking results, they naturally believe they will continue. Unfortunately, this doesn't happen to be the case due to overfit strategies, ignored transaction costs, and survivorship bais. I started this project after seeing my peers try, in vain, to "daytrade" and following viral tiktok strategies to try and make money quick. Existing backtesting tools either cost hundreds of dollars per month, require coding expertise that most retail traders don't have, or mislead consumers on their strategy. NLSB is a backtester that gives honest results that don't hinder you financially. 

What it does: Accepts strategy in plain english ("buy SPY when RSI drops below 30 and the 50-day MA is above the 200-day; sell when RSI exceeds 70")
              Translates the description into an executable strategy using LLM 
              Runs the strategy into historical price data for stocks/ETFs and crypto
              Returns standard performance metric (Sharpe ratio, RSI) along with delivering an honest robust assessment of your strategy (walk-forward validation results, parameter sensitivity analysis, and a deflated                     Sharpe ratio that accounts for overfitting)

What differentiates NLSB from other backtesters is that it doesn't optimize to show you a green line. Specifically, it records 
