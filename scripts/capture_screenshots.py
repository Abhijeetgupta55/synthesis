"""Save every demo page as a PNG (fallback if the live demo cannot run during the presentation).

Requires: pip install playwright && python -m playwright install chromium
Usage:    start the demo (scripts/run_demo.ps1), then: python scripts/capture_screenshots.py [--url http://localhost:8501]
Output:   reports/figures/demo_<page>.png
"""
from __future__ import annotations

import argparse
from pathlib import Path

PAGES = ["Try it on a real repo", "The 108k-build study", "Why this test?", "Scoreboard", "Honesty"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:8501")
    a = ap.parse_args()
    from playwright.sync_api import sync_playwright

    out = Path(__file__).resolve().parents[1] / "reports" / "figures"
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": 1400, "height": 1000})
        page.goto(a.url)
        page.wait_for_timeout(5000)
        for name in PAGES:
            page.get_by_text(name, exact=True).click()
            page.wait_for_timeout(6000)
            f = out / f"demo_{name.lower().replace(' ', '_').replace('?', '')}.png"
            page.screenshot(path=str(f), full_page=True)
            print("saved", f)
        b.close()


if __name__ == "__main__":
    main()
