"""
Make the preview images the homepage cards show
-----------------------------------------------
A preview is NOT a shrunk screenshot of the whole page (its text becomes unreadable in a small card).
It is a close-up of the page's header only: the brass topic label, the question title in big type,
and the four key-number cards, in dark mode. The small paragraph, the data line and the back link are
hidden in the screenshot (the page itself is not changed).

How: each page is loaded in a 560 x 420 frame (4:3, the shape of the homepage card), the frame is
shot at double resolution (1120 x 840 image) with headless Chrome, then cropped with PIL.

Run (from the repo root):
    python tools/make_previews.py                 # every page in PAGES
    python tools/make_previews.py nasdaq-bonds    # only pages whose path contains this text

Needs Google Chrome and Pillow (pip install pillow).
"""

import subprocess                         # runs headless Chrome
import sys                                # reads the optional filter from the command line
import tempfile                           # a throw-away folder for the wrapper page and Chrome's profile
from pathlib import Path                  # file paths that work on Windows, Mac and Linux

from PIL import Image                     # crops the screenshot


# ===========================================================================
# python / data code
# ===========================================================================

ROOT = Path(__file__).resolve().parent.parent                  # the repo root (this file is in tools/)
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")   # Chrome on this machine
FRAME_W, FRAME_H = 560, 420               # the frame the page is shown in: 4:3 like the homepage card
SCALE = 2                                 # shoot at double resolution so the text stays sharp

PAGES = [                                 # (project page, preview it produces), paths from the repo root
    ("nasdaq-bonds/nasdaq_bonds.html", "nasdaq-bonds/nasdaq_bonds_preview.png"),
    ("VIX/output/shocks.html", "VIX/output/shocks_preview.png"),
    ("Rates_and_Phillips/rates_phillips.html", "Rates_and_Phillips/rates_phillips_preview.png"),
    ("Rates_and_Phillips/ecb_rates.html", "Rates_and_Phillips/ecb_rates_preview.png"),
    ("Rates_and_Phillips/fed_rates.html", "Rates_and_Phillips/fed_rates_preview.png"),
    ("Deficit_Surplus/trade_balance.html", "Deficit_Surplus/trade_balance_preview.png"),
    ("Yield_Curve/sovereign_spreads.html", "Yield_Curve/sovereign_spreads_preview.png"),
    ("tips-gold-bonds/tips_gold_bonds.html", "tips-gold-bonds/tips_gold_bonds_preview.png"),
]


def shoot(page, out, work):
    """Screenshot one page's header through the wrapper and save the cropped preview."""
    wrapper = work / "wrapper.html"                            # the small page that holds the frame
    wrapper.write_text(wrapper_html((ROOT / page).as_uri()), encoding="utf-8")   # point it at this project page
    shot = work / "shot.png"                                   # Chrome's raw screenshot
    subprocess.run([str(CHROME), "--headless=new", "--disable-gpu",
                    f"--user-data-dir={work / 'profile'}",     # its own profile: the default one is locked when Chrome is open
                    "--allow-file-access-from-files",          # lets the wrapper reach into the frame to hide the small text
                    "--blink-settings=preferredColorScheme=0", # dark mode, always (see CLAUDE.md)
                    "--hide-scrollbars", f"--force-device-scale-factor={SCALE}",
                    "--virtual-time-budget=8000",              # time for fonts and charts to load
                    "--window-size=1200,900",                  # bigger than the frame: small windows get cropped silently
                    f"--screenshot={shot}", wrapper.as_uri()],
                   check=True, capture_output=True, timeout=120)
    image = Image.open(shot).crop((0, 0, FRAME_W * SCALE, FRAME_H * SCALE))   # keep only the frame, top-left
    image.save(ROOT / out)                                     # overwrite the preview next to the page
    # returns a tuple (width, height) of the saved image, always (1120, 840), e.g. (1120, 840);
    # writes e.g. nasdaq-bonds/nasdaq_bonds_preview.png
    return image.size


def main():
    wanted = sys.argv[1] if len(sys.argv) > 1 else ""         # optional filter, e.g. "nasdaq-bonds"
    with tempfile.TemporaryDirectory() as tmp:                 # deleted automatically at the end
        work = Path(tmp)                                       # scratch folder for this run
        for page, out in PAGES:                                # one preview per project page
            if wanted in page:                                 # skip pages the filter leaves out
                size = shoot(page, out, work)                  # take and save the preview
                print(f"Saved {out} {size[0]}x{size[1]}")      # e.g. "Saved nasdaq-bonds/nasdaq_bonds_preview.png 1120x840"


# ===========================================================================
# html / chart code
# ===========================================================================

def wrapper_html(page_uri):
    """A blank page holding the project page in a 560 x 420 frame, hiding the small header text once it loads."""
    # returns a str of HTML, e.g. '<!doctype html><html><body style="margin:0;background:#101115"><iframe src="file:///C:/.../nasdaq_bonds.html" ...'
    return f"""<!doctype html><html><body style="margin:0;background:#101115">
<iframe id="f" src="{page_uri}" style="width:{FRAME_W}px;height:{FRAME_H}px;border:0;display:block"></iframe>
<script>
document.getElementById("f").onload = e => {{
  const s = e.target.contentDocument.createElement("style");   // only inside the screenshot: the page file is untouched
  s.textContent = ".answer,.meta,a.back{{display:none}} .eyebrow{{margin-top:28px}}";
  e.target.contentDocument.head.appendChild(s);
}};
</script></body></html>"""


if __name__ == "__main__":
    main()
