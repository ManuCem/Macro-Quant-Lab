# Macro Quant Lab

This is a personal project for testing ideas at the intersection of
macroeconomics, machine learning, and quantitative trading — a space to try
things, break things, and see what actually holds up.

It's wired to an n8n + Telegram automation: a Telegram bot triggers an n8n
workflow, which pulls the latest code from this repo, runs the relevant
script, and sends an AI-generated interpretation of the result back through
Telegram. So new experiments here go live the moment they're pushed.

## What's here

Each folder is a self-contained experiment:

- **bond-30y/** — pulls 30-year Treasury yield data, engineers technical
  features, and predicts next-day direction (up/down), validated with
  time-series cross-validation.
- **sp500/** — same approach applied to the S&P 500 index, with added
  volume and Bollinger Band features.
- **VIX/** — tests whether the VIX is "overpriced" relative to the volatility
  that actually materializes. Since the VIX is a forward-looking (~30-day)
  implied volatility, each day's VIX is compared with the S&P 500's realized
  volatility over the *following* 21 trading days (annualized, from log
  returns) rather than the trailing window. Over 30 years of data, the script
  reports the average bias (VIX − realized; a positive value means the VIX
  overestimated volatility, i.e. the volatility risk premium) and the RMSE,
  and saves an interactive Plotly chart to `VIX/output/volatility.html`.

More will be added as new ideas come up — this is a lab, not a finished product.

## How it runs

Telegram command → n8n workflow → pulls latest code from this repo → runs
the script → sends the raw output to an LLM for interpretation → replies
back in Telegram. A sample of the n8n workflow (credentials and IDs
scrubbed) is included in this repo for reference.

## Disclaimer

Personal research/learning project. Nothing here is investment advice.

## License

MIT — see [LICENSE](LICENSE).