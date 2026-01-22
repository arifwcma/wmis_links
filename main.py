import csv
import html
import re
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


START_URL = (
    "https://data.water.vic.gov.au/WMIS/#/overview/stations"
    "?ww-station-table-_hiddenColumns=null"
    "&ww-station-table-sort=%5B%7B%22field%22%3A%22station_name%22%2C%22ascending%22%3Atrue%7D%5D"
)


def _normalize_text(s: str) -> str:
    s = html.unescape(s or "")
    s = s.replace("\u00A0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _extract_id_text_after_sh(sh_element) -> str:
    """
    Matches the DOM rule you specified:
    - `$id` = the text element that appears right after `$sh`
    - trimmed and HTML entities (&nbsp;) removed

    Implementation details:
    - Walk `nextSibling` from the `.sh` element.
    - Collect *text node* content (nodeType=3).
    - Skip comment nodes (nodeType=8).
    - Stop when the first element sibling is encountered (nodeType=1), e.g. `<wmis-chip ...>`.
    """
    raw = sh_element.evaluate(
        """
        (sh) => {
          let out = "";
          let n = sh.nextSibling;
          while (n) {
            if (n.nodeType === Node.ELEMENT_NODE) break;
            if (n.nodeType === Node.TEXT_NODE) out += n.textContent || "";
            // comments (and other node types) are ignored
            n = n.nextSibling;
          }
          return out;
        }
        """
    )
    return _normalize_text(raw)


def main() -> int:
    # Recreate CSV on each run
    out_path = Path("links.csv")
    if out_path.exists():
        out_path.unlink()

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "id", "link"])

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context()
            page = context.new_page()

            page.goto(START_URL, wait_until="domcontentloaded")

            # Click Surface Water (tolerant match)
            surface = (
                page.locator("div.topicCardHeadingText")
                .filter(has_text=re.compile(r"surface\s*water", re.IGNORECASE))
                .first
            )
            surface.wait_for(state="visible", timeout=30_000)
            surface.click()

            # Locate list container (prefer exact ID, then fallback)
            list_container = page.locator("#wmis-sites-list")
            if list_container.count() == 0:
                list_container = page.locator('[id*="wmis-sites-list"]')
            list_container.first.wait_for(state="attached", timeout=30_000)
            list_container = list_container.first

            # Capture the currently loaded station IDs (no scrolling, as requested)
            station_ids = list_container.locator("div.st").evaluate_all(
                "els => els.map(e => e.id).filter(Boolean)"
            )

            for sid in station_ids:
                station = list_container.locator(f"div.st#{sid}")
                sh = station.locator("div.sh").first

                try:
                    sh.wait_for(state="visible", timeout=10_000)
                except PlaywrightTimeoutError:
                    # Station got virtualized/removed; skip
                    continue

                name = _normalize_text(sh.inner_text(timeout=5_000))
                station_id = _extract_id_text_after_sh(sh)

                before_url = page.url
                sh.scroll_into_view_if_needed(timeout=5_000)
                sh.click(timeout=10_000)

                # WMIS is an SPA: URL may change without full navigation.
                try:
                    page.wait_for_function(
                        "(prev) => window.location.href !== prev",
                        arg=before_url,
                        timeout=7_500,
                    )
                except PlaywrightTimeoutError:
                    pass

                link = page.url

                writer.writerow([name, station_id, link])

            context.close()
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

