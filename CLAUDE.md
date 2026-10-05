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

## Phone-friendly HTML (always use this method)

Every HTML page or chart I ask for must look great on a phone, not only on a computer. The pages are published on GitHub Pages and I open them on my phone. Build it phone-ready from the start and **prove it with a test**; never assume it works.

**How to build it**
- **Viewport:** always `<meta name="viewport" content="width=device-width, initial-scale=1">` (add `viewport-fit=cover` plus `env(safe-area-inset-*)` padding if the page uses the full screen).
- **No sideways scrolling of the page.** Only a table or a code block may scroll sideways, inside its own `overflow-x: auto` box. Leave at least 16px of side margin, use relative units, and let flex and grid rows wrap or stack on narrow screens (one breakpoint around 640-720px).
- **Finger-sized tap targets:** every link, button and tab is about 44px tall (at least 40px). If the text must stay small, enlarge the hit area with padding or an invisible `::after`.
- **Tables:** let the text wrap, drop the least useful column on a phone, or keep sideways scrolling with a "Swipe the table sideways" hint and the first column pinned (`position: sticky`).
- **Charts must have a separate phone layout** (read with `matchMedia("(max-width: 640px)")`): the legend stacked one entry per line or placed below the plot, never on top of it or on the right; the plot starts below the legend; two side-by-side charts stack vertically; the first and last axis labels are not cut off; the chart box is taller on a phone. Rebuild the chart when the screen crosses that line (phone rotation).
- **Never trap the finger:** on touch screens (`matchMedia("(pointer: coarse)")`) turn off drag-zoom and "inside" zoom so the page still scrolls; keep a zoom slider if zoom is useful. Write "tap" instead of "hover" for touch users.
- Do not use hover as the only way to reach information.

**How to prove it (run these every time, and fix what they show)**
1. Render the page in a **real 360px-wide frame** (an `<iframe style="width:360px">` inside a test page, shot with headless Chrome using `--allow-file-access-from-files`). Do not trust a small headless window: Chrome has a minimum window width and the screenshot is silently cropped.
2. **Look at the screenshots** of every tab or section, at 360px and at desktop width. Desktop must not get worse.
3. **Measure, don't guess:** from a test page, read the frame's document and check that the page has no sideways overflow (`scrollWidth <= clientWidth`), that every chart canvas has a sensible size, and that links and buttons are tall enough.
4. If the page is generated by a Python script, change the script (the HTML is rebuilt on every run), never the generated file by hand.
5. Tell me what I should still try on a real phone: touch behaviour cannot be fully tested in a desktop browser.

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
