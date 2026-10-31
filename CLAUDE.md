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

## Project pages (always use this format)

Every project page (one per study, like `nasdaq-bonds/nasdaq_bonds.html`) uses the **Lab design**. The reference implementation is the html / chart part of `nasdaq-bonds/nasdaq_bonds.py`: copy its CSS and page structure for new projects. All the **Phone-friendly HTML** rules apply.

**Look:** a header band in the **project's own colour** with a matching accent, DM Serif Display titles and DM Sans text, the key numbers as white cards overlapping the bottom of the band, then one white panel per section. Light and dark mode via colour tokens. Greys, text and backgrounds are neutral (no green tint).

**Each project has its own colour** (`--band` for the header, `--brass` for the accent: labels, numbers, the takeaway border), light value / dark value. The homepage card for the project uses the same accent for its hover highlight (`style="--c-l:…;--c-d:…"` on the card). A new project gets a new deep tone that is not in this table yet.

| Project | `--band` (light / dark) | accent `--brass` (light / dark) |
|---|---|---|
| Homepage | graphite `#17191f` / `#101115` | brass `#c49a45` / `#d8b26a` |
| Nasdaq vs bonds | navy `#142a4f` / `#0d1d38` | blue `#4a7fe0` / `#7fa8f0` |
| VIX | burgundy `#4a1626` / `#33101b` | rose `#d0506c` / `#ec8098` |
| Rates & Phillips (all 4 pages) | petrol `#0e3a46` / `#0a2832` | aqua `#2a9db0` / `#5cc4d2` |
| Trade map | indigo `#2b2257` / `#1d173d` | lavender `#8571e0` / `#ad9cf5` |
| France vs Italy spreads | oxblood `#4a2414` / `#33180d` | copper `#cf6e3a` / `#ec9665` |
| Gold vs real yields | espresso `#3a2b10` / `#281d0a` | gold `#c49a45` / `#d8b26a` |

**The title is always a question**, the one the project answers (for example *"Is money rotating between big tech and bonds?"*). A small brass label above it names the topic.

**This is for learning, not just for looking at charts.** Explain, but keep it tight. No filler, and no sentences that repeat what a chart already shows:
- **Header:** the question, then the **short answer** in 2-3 sentences with the key numbers (first words in bold, for example "Yes, for now."), then a line with the data date and source.
- **Each panel has its own question as its heading** (for example "Where did the money go on tech's bad days?"), then:
  1. **The finding:** one bold line with the number.
  2. **"How to read it":** a short box explaining what the chart shows and how to read it.
  3. The chart or table.
  4. **What it tells us:** a short paragraph with a brass left border. It interprets the result, adds context, or explains why it matters.
- **A key-ideas panel** explains the theory and the terms (for example correlation, basis point, rolling window) in plain language.
- **Last panel, "What did we learn?":** numbered takeaways, ending with the **limits** (sample size, correlation is not causation, and so on).
- **References, not a panel:** where the data comes from must not take centre stage. After the last panel, put a small, quiet "References" list: muted small text, no panel box, no question heading, no "How to read it". Just a few lines (source name, what it gave, link), each link still at least 40px tall to tap. Press articles go there too, as one line each.
- Every number in the text is computed in Python from the data, so the text stays true after a re-run. Never type a number by hand.

**Chart tooltips must be readable in both modes.** Never leave the library's default white tooltip: in dark mode it glares and is hard to read. Give every tooltip (ECharts `tooltip`, axis-pointer labels, Plotly `hoverlabel`, hand-made SVG tooltips) the page tokens: background `--surface`, border `--grid`, text `--ink`, plus a soft shadow. Rebuild the chart when the theme changes so the tooltip follows.

**Section menus** (a folder with several pages, like `Rates_and_Phillips/index.html`) are built exactly like the homepage, in the section's own colour: header band with brass label, question title and description, then a **featured** card (the section's main study) overlapping the band, then a "More in this section" heading and a grid of the other pages, with the same card markup and hover as the homepage.

**Maps** (like the trade map) have a **full-screen button** that opens the map over the whole screen (with a clear close button and the Esc key), and the map still works there: zoom buttons, country picker and info card.

This look (per-project colours, previews, the panel structure above) is the approved standard as of 30 Oct 2026: keep it when adding or changing pages.

## Homepage (`index.html`, always keep this structure)

The root `index.html` is the front page on GitHub Pages. It is written by hand (no Python script), and every change must keep this layout. It also follows all the **Phone-friendly HTML** rules above, including the 360px test.

**Look**
- Graphite header band (`--band: #17191f`) with brass accents (`--brass`), light page in light mode, dark page in dark mode. No green. Fonts: DM Serif Display for titles, DM Sans for text.
- Header, in this order: small brass label "Macroeconomics · Machine learning · Quant trading", the title "Macro Quant Lab", then this description, word for word: *"Personal research lab at the intersection of macroeconomics, machine learning and quantitative trading — a space to test ideas and see what works."*
- Under the description, a "View the code on GitHub" button with the **GitHub logo** (inline SVG) linking to https://github.com/ManuCem/Macro-Quant-Lab. The footer link to GitHub also has the logo.

**Featured study**
- One large card overlaps the bottom of the header band, with a "Featured study" badge.
- The featured study is **chosen by me**, not automatically the newest one. Right now it is **Nasdaq 100 vs bond yields** (`nasdaq-bonds/nasdaq_bonds.html`). Only change it when I ask.

**All studies grid**
- Below "All studies", one card per project (every project except the featured one): preview image, small brass topic label, serif title, a one or two sentence description.
- **No "Open dashboard / Open the page / Open the map" text.** The whole card is the link: clicking anywhere opens the project.
- **Hover animation (mouse only):** in the **project's own accent colour** (`--c`, from the card's `--c-l` / `--c-d`), the border lights up, a soft glow appears, the card lifts 4px, the image zooms in slightly and the title turns that colour. The topic label also uses it. Keep it inside `@media (hover: hover)` so a tap on a phone does not leave a card stuck highlighted.
- **Preview images** are shown in a 4:3 box with `object-fit: cover; object-position: top center`.
- **Preview images are made with `python tools/make_previews.py`**, never by hand. A preview is a readable close-up of the page header, not a shrunk screenshot of the whole page (its text was unreadable in a small card). It shows the brass topic label, the question title in big type and the four key-number cards, in **dark mode**, 4:3 (1120x840). The small paragraph, the data line and the back link are hidden in the screenshot only. When you add a project, add its page to `PAGES` in that script and run it (`python tools/make_previews.py <folder>` does one project). On this machine, headless Chrome only works with its own profile (`--user-data-dir`), which the script handles. The image boxes on the homepage have a dark (`--band`) background, so no white edges show.

**Adding a new project**
- Add a card to the grid with the same markup as the others (image, topic, title, description), with links relative to the repo root (for example `nasdaq-bonds/nasdaq_bonds.html`). Give the card its project's colours (`style="--c-l:…;--c-d:…"`) and update the "N more" count next to "All studies".
- Make its preview with `python tools/make_previews.py <folder>` and add its section to the README (see the README section below).
- Check that every link and image path exists, then run the phone test.

## README (`README.md`, always keep this structure)

The README is **minimalist: the website is the protagonist.** It is written by hand (no script), and every change must keep this layout, in this order:

1. **Title:** just `# [Macro Quant Lab](https://manucem.github.io/Macro-Quant-Lab/)`. The title itself is the link to the website. No icon or emoji, no highlight box, no separate "Website" line, and never the website name or address written out a second time.
2. **Description:** the same sentence as the homepage, word for word: *"A personal research lab at the intersection of macroeconomics, machine learning and quantitative trading — a space to test ideas and see what works."*
3. **`## Projects`:** one `###` section per project, in the same order as the homepage. Each section has:
   - **A heading that is the project's question, linked to its live page** (plain Markdown link, e.g. `### [Is money rotating between big tech and bonds?](…)`). No "Open live dashboard" / "Open the page" / "▶" links, and no yellow `<mark>` highlighter: it looked wrong on GitHub.
   - **A table with the project's data**, fairly wide (several columns, not just two or three): the same figures the page shows.
   - **4-5 bullet points** with the most important numbers.
   - **A bold `**Conclusion:**` line** (1-2 sentences) saying what the project taught.
4. **`## Automation`:** how the n8n + Telegram workflow runs the model scripts on the server (30-year Treasury yield and S&P 500), pulls the latest data, has an AI model write a short brief, and replies in Telegram, plus the safeguards (one authorized user, 30 s cooldown, 90 s script limit, never pulls code automatically) and the link to `n8n/`.
5. **`## License`:** MIT, with the link to `LICENSE`.

**Never put in the README:** screenshots or preview images, "Run it yourself" install/run blocks, a "What's here" list, a "How it runs" section, a "short answer" per project, or hover-only tricks. All the learning content lives on the website, not here.

The README numbers are typed by hand from the live pages (the pages are the source of truth), so after a project page is rebuilt with new data, update that project's table and bullets. When you add a project, add its section to the README (heading, table, bullets, conclusion) in the same order as the homepage.

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
