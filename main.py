import csv
import html
import os
import re
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


DEV_MODE = False

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


def _ts() -> str:
    return time.strftime("%H:%M:%S")


def _log(msg: str) -> None:
    print(f"[{_ts()}] {msg}", flush=True)


def _safe_click(
    locator, *, label: str, timeout_ms: int = 20_000, prefer_dom: bool = False
) -> None:
    """
    Click helper with verbose logging.
    Tries a normal Playwright click first; if pointer interception blocks it,
    falls back to a DOM click (el.click()) so we can keep moving.
    """
    if prefer_dom:
        _log(f"Clicking {label} (DOM click preferred: el.click())...")
        locator.evaluate("(el) => el.click()")
        _log(f"Clicked {label} (DOM click)")
        return

    _log(f"Clicking {label} (normal click)...")
    try:
        locator.click(timeout=timeout_ms)
        _log(f"Clicked {label} (normal click OK)")
        return
    except PlaywrightTimeoutError as e:
        msg = str(e)
        _log(
            f"Normal click timed out for {label}: {msg.splitlines()[0] if msg else 'timeout'}"
        )
        _log(f"Falling back to DOM click for {label} (el.click())...")
        locator.evaluate("(el) => el.click()")
        _log(f"Clicked {label} (DOM click fallback)")


def main() -> int:
    # Recreate CSV on each run.
    # On Windows, deleting can fail if the file is open (Excel/preview/etc),
    # so we prefer opening with mode="w" (truncate) and give a clear message if locked.
    out_path = Path("links.csv")
    _log("Creating links.csv with header: name,id,link")

    try:
        f = out_path.open("w", newline="", encoding="utf-8")
    except PermissionError:
        _log("ERROR: links.csv is locked by another process. Close it (Excel/preview/editor) and re-run.")
        return 2

    with f:
        writer = csv.writer(f)
        writer.writerow(["name", "id", "link"])
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            # Best-effort; some environments/filesystems may not support fsync.
            pass

        def collect_station_ids(browser_) -> list[str]:
            _log("Collecting station ids once (base session)...")
            context_ = browser_.new_context()
            page_ = context_.new_page()

            _log(f"Opening start URL (will follow redirects): {START_URL}")
            page_.goto(START_URL, wait_until="domcontentloaded", timeout=60_000)
            _log(f"Current URL after load: {page_.url}")

            _log('Locating "Surface Water" card heading...')
            surface_ = (
                page_.locator("div.topicCardHeadingText")
                .filter(has_text=re.compile(r"surface\s*water", re.IGNORECASE))
                .first
            )
            surface_.wait_for(state="visible", timeout=30_000)
            # The normal click can be blocked by an overlay; DOM click is consistently faster here.
            _safe_click(surface_, label='"Surface Water"', prefer_dom=True)
            _log(f"URL after clicking Surface Water: {page_.url}")

            _log("Waiting for station rows (div.st[id]) to appear...")
            station_rows_ = page_.locator("div.st[id]")
            try:
                station_rows_.first.wait_for(state="attached", timeout=30_000)
            except PlaywrightTimeoutError:
                _log("Timed out waiting for station rows. Writing debug screenshot: debug_no_station_rows.png")
                page_.screenshot(path="debug_no_station_rows.png", full_page=True)
                raise

            _log("Collecting currently loaded station row IDs (div.st[id])...")
            ids = station_rows_.evaluate_all("els => els.map(e => e.id).filter(Boolean)")
            _log(f"Collected {len(ids)} station IDs.")
            context_.close()
            return ids

        def process_station_id(browser_, sid: str) -> tuple[str, str, str] | None:
            """
            Unique session per station row:
            - new context
            - open WMIS start url
            - click Surface Water
            - find station by sid
            - click station, then Documents -> Gaugings and Ratings
            - return name, id, final link
            """
            context_ = browser_.new_context()
            page_ = context_.new_page()

            try:
                _log(f"  Opening start URL: {START_URL}")
                page_.goto(START_URL, wait_until="domcontentloaded", timeout=60_000)

                surface_ = (
                    page_.locator("div.topicCardHeadingText")
                    .filter(has_text=re.compile(r"surface\s*water", re.IGNORECASE))
                    .first
                )
                surface_.wait_for(state="visible", timeout=30_000)
                _safe_click(surface_, label='"Surface Water"', prefer_dom=True)

                station_ = page_.locator(f"div.st#{sid}")
                try:
                    station_.wait_for(state="attached", timeout=30_000)
                except PlaywrightTimeoutError:
                    _log(f"  station row {sid!r} not found in this session; skip")
                    return None

                sh_ = station_.locator("div.sh").first
                sh_.wait_for(state="visible", timeout=10_000)

                name_ = _normalize_text(sh_.inner_text(timeout=5_000))
                station_id_ = _extract_id_text_after_sh(sh_)
                _log(f"  name={name_!r}")
                _log(f"  id={station_id_!r}")

                before_url_ = page_.url
                sh_.scroll_into_view_if_needed(timeout=5_000)
                _safe_click(sh_, label=f"station .sh ({name_})", prefer_dom=True, timeout_ms=1_000)

                try:
                    page_.wait_for_function(
                        "(prev) => window.location.href !== prev",
                        arg=before_url_,
                        timeout=5_000,
                    )
                except PlaywrightTimeoutError:
                    pass

                _log(f"  station URL={page_.url!r}")

                documents_ = (
                    page_.locator("div.text")
                    .filter(has_text=re.compile(r"\bdocuments\b", re.IGNORECASE))
                    .first
                )
                try:
                    documents_.wait_for(state="visible", timeout=20_000)
                except PlaywrightTimeoutError:
                    _log("  timed out waiting for Documents; writing debug screenshot: debug_no_documents.png")
                    page_.screenshot(path="debug_no_documents.png", full_page=True)
                    raise
                _safe_click(documents_, label='"Documents"', prefer_dom=True, timeout_ms=2_000)

                gr_ = (
                    page_.locator("div.doclabel")
                    .filter(has_text=re.compile(r"gaugings\s*and\s*ratings", re.IGNORECASE))
                    .first
                )
                try:
                    gr_.wait_for(state="visible", timeout=20_000)
                except PlaywrightTimeoutError:
                    _log(
                        "  timed out waiting for Gaugings and Ratings; writing debug screenshot: debug_no_gaugings_and_ratings.png"
                    )
                    page_.screenshot(path="debug_no_gaugings_and_ratings.png", full_page=True)
                    raise

                before_url_ = page_.url
                _safe_click(gr_, label='"Gaugings and Ratings"', prefer_dom=True, timeout_ms=2_000)
                try:
                    page_.wait_for_function(
                        "(prev) => window.location.href !== prev",
                        arg=before_url_,
                        timeout=10_000,
                    )
                except PlaywrightTimeoutError:
                    pass

                link_ = page_.url
                _log(f"  final link={link_!r}")
                return (name_, station_id_, link_)
            finally:
                context_.close()

        with sync_playwright() as p:
            _log("Launching Chromium (headless)")
            browser = p.chromium.launch(headless=True)

            station_ids = collect_station_ids(browser)

            written_rows = 0
            for idx, sid in enumerate(station_ids, start=1):
                _log(f"[{idx}/{len(station_ids)}] Processing station row id={sid!r} (unique session)")
                result = process_station_id(browser, sid)
                if result is None:
                    continue

                name, station_id, link = result
                writer.writerow([name, station_id, link])
                f.flush()
                try:
                    os.fsync(f.fileno())
                except OSError:
                    pass
                _log("  wrote CSV row")

                written_rows += 1
                if DEV_MODE and written_rows >= 5:
                    _log("DEV_MODE=True -> stopping after 5 rows")
                    break

            _log("Done. Closing browser.")
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

