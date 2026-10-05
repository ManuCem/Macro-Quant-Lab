# Macro-Quant-Lab

## Primary Goal
This is a **learning project** — a space to break down complex concepts in macroeconomics, machine learning, and quantitative trading. The goal is to:
- Understand foundational ideas deeply
- Test hypotheses and approaches
- Build working prototypes and tools
- Document learnings along the way

Not a production system, but a lab for experimentation and research.

## Working with Code

When reviewing or writing code:
- **Break down code line by line** — explain what each line does, not just the overall function
- **Add comments liberally** — document the "what" and the "why" for every non-obvious operation
- **Explain variable names** — if a variable name isn't self-explanatory, add a comment
- **Show intermediate steps** — don't skip logic; walk through the reasoning
- **Test incrementally** — run small chunks of code, verify each step works before moving on

The goal is clarity and learning, not brevity.

## Code Structure (always use this layout)

Every script I ask for is split into two clearly separated parts, in this order:

1. **`# python / data code`** — everything that downloads, cleans or calculates, ending in a `def main():` that runs the steps in order.
2. **`# html / chart code`** — everything that draws the charts or builds the HTML page, kept below the data code and never mixed into it.

Rules for the python / data part:
- **Comment every line.** Put a `#` comment explaining what the line does (and why, if it isn't obvious). No line is left unexplained.
- **Every function ends with a documented return.** Right at the `return`, add a comment showing what the returned value looks like: its type, its shape, and a small example (a few rows, or an example dictionary with real-looking values).
- **The `return` comment is the most important comment in the function.** Never skip it. Every `return` inside a `def` must be preceded by a `#` comment block that *prints out the output* so I can see it without running the code: the type (DataFrame, Series, dict, list, str, float...), the shape (rows x columns or number of items), and a small example of the real values, laid out the way Python would print them. If a function returns nothing and only prints or saves a file, say so and show the printed text or the file it writes.
- **`def main():` is the conductor.** It only calls the other functions in order and prints or saves the results; the calculations live in their own functions.
- Finish with `if __name__ == "__main__": main()` so the file can also be imported without running.

Example of the shape I expect:

```python
# ---------------------------------------------------------------
# python / data code
# ---------------------------------------------------------------

def build_dataset():
    prices = fetch_prices("^GSPC", "30y")   # download 30 years of S&P 500 closes from Yahoo Finance
    vix = fetch_prices("^VIX", "30y")       # download the VIX over the same period
    data = pd.DataFrame({"sp500": prices, "vix": vix})  # join both series into one table, matched by date
    data = data.dropna()                    # drop days where either value is missing
    # returns a DataFrame, one row per trading day (~7,500 rows):
    #               sp500    vix
    # Date
    # 1996-10-02   694.01  16.78
    # 1996-10-03   692.78  16.77
    return data

def main():
    data = build_dataset()                  # step 1: build the table
    print(data.tail())                      # step 2: show the last rows to check it worked

# ---------------------------------------------------------------
# html / chart code
# ---------------------------------------------------------------
# (chart and page-building functions go here)

if __name__ == "__main__":
    main()
```

## Do Not Commit
- `.env` files or API keys
- Real account data, trade logs, or balances
- Large data files (`.sqlite`, `.parquet` with real data)
- Any credentials or secrets

## Philosophy
Expect to:
- Try things that don't work
- Refactor and rebuild
- Document what you learn (good and bad)
- Keep the code clean enough to understand later

This is a **learning lab**, not production — focus on understanding over performance.
