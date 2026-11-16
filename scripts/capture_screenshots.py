"""Save every demo page as a PNG (the fallback if the live demo cannot run during the presentation).

Requires: pip install playwright   (then either `python -m playwright install chromium`, or use --channel msedge to
          drive the Microsoft Edge that ships with Windows)
Usage:    start the demo (scripts/run_demo.ps1), then:
          python scripts/capture_screenshots.py [--url http://localhost:8501] [--channel msedge]
Output:   reports/demo_screenshots/<nn>_<page>.png (plus one per ML-pipeline tab and per race source)
"""
from __future__ import annotations

import argparse
from pathlib import Path

PAGES = ["Overview", "The ML pipeline", "Predict live", "Race replay", "Results", "Limits and honesty"]
TABS = ["1 EDA", "2 Features", "3 Classification", "4 Regularization", "5 Tuning", "6 Ensembles", "7 Performance"]


def slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
    ap.add_argument("--channel", default=None, help="e.g. msedge or chrome (use an installed browser)")
    ap.add_argument("--wait", type=int, default=8000, help="ms to wait after each click")
    ap.add_argument("--height", type=int, default=2800, help="viewport height: Streamlit scrolls inside the page, "
                    "so a tall viewport is what captures the whole page")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    out = Path(__file__).resolve().parents[1] / "reports" / "demo_screenshots"
    out.mkdir(parents=True, exist_ok=True)

    def shot(page, name):
        page.wait_for_function("!document.body.innerText.includes('CONNECTING') && "
                               "!document.body.innerText.includes('Running...')", timeout=120000)
        page.wait_for_timeout(1000)
        f = out / f"{name}.png"
        page.screenshot(path=str(f), full_page=True)
        print("saved", f)

    with sync_playwright() as p:
        b = p.chromium.launch(channel=a.channel) if a.channel else p.chromium.launch()
        page = b.new_page(viewport={"width": 1440, "height": a.height})
        page.goto(a.url)
        page.wait_for_timeout(a.wait)
        for i, name in enumerate(PAGES, 1):
            page.goto(a.url)                       # fresh load per page: no stale websocket or half-loaded chunk
            page.wait_for_selector("section[data-testid='stSidebar']", timeout=60000)
            page.wait_for_timeout(a.wait)
            page.locator("section[data-testid='stSidebar']").get_by_text(name, exact=True).click()
            page.wait_for_timeout(a.wait * (3 if name == "Predict live" else 1))
            shot(page, f"{i:02d}_{slug(name)}")
            if name == "The ML pipeline":
                for j, tab in enumerate(TABS, 1):
                    page.get_by_role("tab", name=tab).click()
                    page.wait_for_timeout(1500)
                    shot(page, f"{i:02d}_{j}_{slug(tab)}")
            if name == "Race replay":
                page.get_by_text("LRTS held-out builds", exact=True).click()
                page.wait_for_timeout(a.wait)
                shot(page, f"{i:02d}_b_lrts")
        b.close()


if __name__ == "__main__":
    main()
