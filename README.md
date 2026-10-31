# [Macro Quant Lab](https://manucem.github.io/Macro-Quant-Lab/)

A personal research lab at the intersection of macroeconomics, machine learning and quantitative trading — a space to test ideas and see what works.

## Projects

### [Is money rotating between big tech and bonds?](https://manucem.github.io/Macro-Quant-Lab/nasdaq-bonds/nasdaq_bonds.html)

| Window | Corr. Nasdaq vs 10y yield | Corr. Nasdaq vs long bonds | Nasdaq move on a +10 bp day | Nasdaq | 10y yield | Long bonds (TLT) | Regime |
|---|---|---|---|---|---|---|---|
| Last 20 days | +0.63 | −0.61 | +1.40% | −3.6% | −25 bp | +4.9% | Rotation |
| Last 60 days | +0.09 | −0.04 | +0.19% | −0.3% | +37 bp | −1.1% | No clear link |
| Last year | −0.18 | +0.19 | −0.53% | +14.2% | +90 bp | −5.8% | No clear link |

- In the last 20 trading days the Nasdaq and the 10-year yield moved together (+0.63), so tech and long bonds moved in opposite directions (−0.61).
- Long bonds rose on 9 of the 11 days the Nasdaq fell, gaining +0.57% on average while the Nasdaq lost 1.05%.
- 14 of the last 20 days were rotation days (tech and bonds moving opposite ways).
- Over five years the 60-day correlation was positive on only 43% of days, ranging from −0.67 (Jun 2026) to +0.46 (Apr 2025).
- Even in 2022, the year of the Fed's fastest hikes, the daily correlation averaged only −0.07.

**Conclusion:** money is rotating between big tech and bonds right now, and bonds are working as a cushion on tech's bad days. But the pattern is only a few weeks old and the link has flipped many times, so it is a current regime, not a rule.

### [Was the VIX right about four market shocks?](https://manucem.github.io/Macro-Quant-Lab/VIX/output/shocks.html)

| Episode | Day 0 | Avg VIX | Avg realized | VIX − realized | VIX peak | Market | S&P, day 0 to low |
|---|---|---|---|---|---|---|---|
| Dot-com (2000–02) | 14 Apr 2000 | 25.4 | 22.1 | +3.3 | 33.5 | Slightly overreacted | −42.7% |
| 2008 crisis | 15 Sep 2008 | 48.8 | 53.0 | −4.2 | 80.9 | Underestimated | −43.3% |
| Covid 2020 | 24 Feb 2020 | 41.4 | 48.0 | −6.6 | 82.7 | Underestimated | −30.6% |
| Tariff shock (2025) | Apr 2025 | 28.4 | 21.8 | +6.6 | — | Overreacted | −7.7% |

- Over 30 years the VIX tracks realized volatility well (correlation ~0.7).
- It sits above the volatility that follows on ~84% of days, +3.8 points on average: the price of insurance.
- In all four shocks the VIX was too low in the 40 days before day 0.
- In 2008 and Covid it underestimated the first weeks, then overshot once the panic was priced in.
- Covid brought the biggest miss: realized volatility peaked at 97.6 while the VIX peaked at 82.7.

**Conclusion:** the VIX is a good thermometer but a poor forecaster. It reacts to shocks rather than seeing them coming, and in calm times it overprices volatility.

### [Did low interest rates bring the recovery?](https://manucem.github.io/Macro-Quant-Lab/Rates_and_Phillips/index.html)

| Crisis | Peak unemployment | Months to recover | Months at floor | Peak core inflation | Lowest real rate | Recovery speed |
|---|---|---|---|---|---|---|
| 2008 crisis | 10.0% | 75 | 85 | 2.9% | −2.2% | Slow |
| Covid | 14.8% | 20 | 24 | 6.6% | −6.4% | Fast, then inflation |

- After 2008 the Fed held rates near zero for 85 months, and unemployment still took 75 months to recover.
- After Covid unemployment peaked higher (14.8%) but recovered in just 20 months.
- The Covid recovery came with core inflation at 6.6% and a real rate as low as −6.4%.
- The section also follows ECB key rates since 1999 and the Fed's EFFR and SOFR, which move almost exactly together.

**Conclusion:** low rates alone did not bring the recovery. In 2008 they were slow to work; after Covid, with huge fiscal support, the economy recovered fast but overshot into inflation, as the Phillips curve warns.

### [Who sells more to the world than it buys?](https://manucem.github.io/Macro-Quant-Lab/Deficit_Surplus/trade_balance.html)

| Biggest surpluses | Balance | Top buyer | Biggest deficits | Balance | Top seller |
|---|---|---|---|---|---|
| China | +$991 bn | United States | United States | −$1,293 bn | China |
| Germany | +$254 bn | United States | United Kingdom | −$293 bn | — |
| Russia* | +$197 bn | — | India | −$263 bn | — |
| Vietnam* | +$132 bn | — | France | −$116 bn | — |
| Ireland | +$98 bn | — | Turkey | −$82 bn | — |

\* estimated from partners' data (2024 goods trade, UN Comtrade).

- China sells the most more than it buys: +$991 bn, with the United States as its biggest buyer ($526 bn).
- The US deficit alone (−$1.29 tn) is bigger than China's whole surplus.
- 66 countries run a surplus and 156 a deficit.
- Countries that did not report their own figures (Russia, Vietnam, UAE…) are estimated from what their partners reported.
- The world does not add up to zero, because imports include freight and insurance, shipments cross the year end and hubs re-export.

**Conclusion:** a few large surpluses (China, Germany) face one giant deficit (the United States). That imbalance is what tariffs and trade wars are about.

### [What do France and Italy pay over Germany to borrow?](https://manucem.github.io/Macro-Quant-Lab/Yield_Curve/sovereign_spreads.html)

| Country | Spread over Germany (latest) | Sep 2026 monthly average | Record since 1999 | 5y CDS | Implied default risk / year |
|---|---|---|---|---|---|
| France | ~154 bp | 97 bp | 154 bp (Nov 2011) | 79.5 bp | ~1.3% |
| Italy | ~107 bp | 89 bp | 519 bp (Nov 2011) | 68.0 bp | ~1.1% |
| Germany | — | — | — | 7.3 bp | ~0.1% |

- France's spread is back at its 2011 euro-crisis record (~154 bp).
- Since 1999 France paid more than Italy in only 5 months, all of them recent.
- Insuring French debt (CDS) now costs more than insuring Italian debt, and about 10 times as much as German debt.
- Italy's record (519 bp in Nov 2011) is still far above where it is today.

**Conclusion:** the market now sees France as about as risky as Italy, a reversal of the euro crisis, driven by France's politics and deficits.

### [What quietly drives bonds and gold?](https://manucem.github.io/Macro-Quant-Lab/tips-gold-bonds/tips_gold_bonds.html)

| Reference value (Oct 2026) | Level | What it means |
|---|---|---|
| 10-year nominal yield | 5.1% | What a normal Treasury pays |
| 10-year TIPS (real) yield | 2.65% | What you earn after inflation |
| 10-year breakeven | 2.3% | The inflation the market expects |
| US CPI inflation | 3.7% | The inflation that actually happened |

- Nominal yield ≈ real yield + expected inflation: 5.1% ≈ 2.65% + 2.3%.
- A TIPS adds CPI to its principal, so it keeps a 2.65% real return whatever inflation does.
- A plain bond beats a TIPS only if actual inflation stays below ~2.4%.
- Gold pays nothing, so holding $1,000 of gold gives up about $26.50 a year of real income at today's real yield.

**Conclusion:** the real yield is the hidden price behind both bonds and gold. When it rises, bonds and gold usually fall; when it falls, both get more attractive.

## Automation

An **n8n** workflow turns the lab into a Telegram bot. A command in Telegram starts the workflow, which connects to a server over SSH and runs a model script (the 30-year Treasury yield or the S&P 500 direction model). The script pulls the latest market data and makes its forecast. An AI model then turns the raw output into a short brief, and the bot replies in Telegram.

It is locked down: it answers one authorized user only, waits 30 seconds between commands, stops scripts after 90 seconds, and never pulls code onto the server automatically. A scrubbed copy of the workflow is in [`n8n/`](n8n/).

## License

MIT — see [LICENSE](LICENSE).
