from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Page, TimeoutError, sync_playwright


CSV_PATH = Path(
    r"\\rygarcorp.com\shares\Cornerstone\Dot Com Packing Slips\zzz - Worldship Shipment Files\Export Info\UPS_CSV_EXPORT.csv"
)
DASHBOARD_URL = "https://commerce.spscommerce.com/fulfillment/dashboard/"


def normalize_po(value: str) -> str:
    return re.sub(r"\D", "", (value or "").strip())


def load_tracking_map(csv_path: Path) -> dict[str, str]:
    if not csv_path.is_file():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    rows: list[list[str]] | None = None
    for enc in ("utf-8-sig", "latin1"):
        try:
            with csv_path.open("r", newline="", encoding=enc) as f:
                rows = list(csv.reader(f))
            break
        except UnicodeDecodeError:
            continue

    if not rows:
        return {}

    out: dict[str, str] = {}
    for row in rows:
        if len(row) < 2:
            continue
        po = normalize_po(row[0])
        tracking = (row[1] or "").strip().split()[0]
        if not po or not tracking:
            continue
        out.setdefault(po, tracking)
    return out


def click_first_visible(page: Page, selectors: list[str], *, timeout_ms: int = 10000) -> bool:
    for sel in selectors:
        loc = page.locator(sel)
        if loc.count() == 0:
            continue
        try:
            loc.first.wait_for(state="visible", timeout=timeout_ms)
            loc.first.click()
            return True
        except Exception:
            continue
    return False


def goto_dashboard(page: Page) -> None:
    page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(400)
    if "login" in page.url.lower():
        raise RuntimeError("Not logged into SPS Commerce. Run after SPS inventory while logged in.")


def open_ready_for_shipment(page: Page) -> None:
    clicked = click_first_visible(
        page,
        [
            "a[data-testid='dashboard_tab']",
            "a[href*='/fulfillment/dashboard/']",
        ],
        timeout_ms=4000,
    )
    if clicked:
        page.wait_for_load_state("domcontentloaded")

    ready_locators = [
        "xpath=//*[contains(normalize-space(.), 'Ready for Shipment')]/ancestor::*[self::a or self::button or @role='button'][1]",
        "xpath=//*[contains(normalize-space(.), 'Ready for Shipment')]",
    ]
    if not click_first_visible(page, ready_locators, timeout_ms=20000):
        raise RuntimeError("Could not open 'Ready for Shipment' from dashboard.")
    page.wait_for_load_state("domcontentloaded")


@dataclass
class SelectionStats:
    rows_seen: int = 0
    rows_matched: int = 0
    rows_checked: int = 0


def select_orders_with_tracking(page: Page, tracking_by_po: dict[str, str]) -> SelectionStats:
    stats = SelectionStats()
    links = page.locator("a.text-truncate[href*='/fulfillment/transactions/document/']")
    total = links.count()
    stats.rows_seen = total
    print(f"Ready for Shipment rows found: {total}")

    for i in range(total):
        link = links.nth(i)
        po_raw = link.inner_text().strip()
        po = normalize_po(po_raw)
        if not po:
            continue
        tracking = tracking_by_po.get(po)
        if not tracking:
            continue
        stats.rows_matched += 1

        row = link.locator("xpath=ancestor::tr[1]")
        if row.count() == 0:
            continue
        checkbox_inputs = row.locator("input[type='checkbox']")
        checkbox_labels = row.locator("label.sps-checkable__label")
        try:
            if checkbox_inputs.count() > 0:
                inp = checkbox_inputs.first
                if not inp.is_checked():
                    if checkbox_labels.count() > 0:
                        checkbox_labels.first.click()
                    else:
                        inp.check()
                stats.rows_checked += 1
            elif checkbox_labels.count() > 0:
                checkbox_labels.first.click()
                stats.rows_checked += 1
        except Exception as ex:
            print(f"Could not select checkbox for PO {po}: {ex}")

    print(
        f"PO match results: matched={stats.rows_matched}, checked={stats.rows_checked}, seen={stats.rows_seen}"
    )
    return stats


def open_create_new_asn(page: Page) -> None:
    if not click_first_visible(
        page,
        [
            "button:has(i.sps-icon-ellipses)",
            "[role='button']:has(i.sps-icon-ellipses)",
            "xpath=//*[contains(@class,'sps-icon-ellipses')]/ancestor::*[self::button or @role='button'][1]",
        ],
        timeout_ms=10000,
    ):
        raise RuntimeError("Could not click bottom ellipses menu.")

    if not click_first_visible(
        page,
        [
            "span:has-text('Create New')",
            "button:has-text('Create New')",
            "[role='menuitem']:has-text('Create New')",
        ],
        timeout_ms=10000,
    ):
        raise RuntimeError("Could not click 'Create New' from actions menu.")

    if not click_first_visible(
        page,
        [
            "label.sps-checkable__label:has-text('Advance Ship Notice')",
            "text=Advance Ship Notice",
        ],
        timeout_ms=10000,
    ):
        raise RuntimeError("Could not choose 'Advance Ship Notice'.")

    # Ensure Auto Fill is selected; label click is safe if currently unselected.
    click_first_visible(
        page,
        [
            "label.sps-checkable__label:has-text('Auto Fill - Recommended')",
            "text=Auto Fill - Recommended",
        ],
        timeout_ms=3000,
    )

    if not click_first_visible(
        page,
        [
            "button[data-testid='modalOkBtn'][title='Create New']",
            "button[data-testid='modalOkBtn']:has-text('Create New')",
        ],
        timeout_ms=10000,
    ):
        raise RuntimeError("Could not click modal 'Create New'.")


def fill_asn_date(page: Page) -> None:
    date_text = datetime.now().strftime("%m/%d/%Y")
    date_input = page.locator("[data-testid='asn.header.shipment.shippedDate-input_date_input']")
    date_input.first.wait_for(state="visible", timeout=60000)
    date_input.first.fill(date_text)
    print(f"Set ASN shipped date to {date_text}")


def fill_tracking_on_asn(page: Page, tracking_by_po: dict[str, str]) -> tuple[int, int]:
    po_links = page.locator("a.text-truncate.d-block[href*='/fulfillment/transactions/document/']")
    total = po_links.count()
    filled = 0
    for i in range(total):
        po_raw = po_links.nth(i).inner_text().strip()
        po = normalize_po(po_raw)
        if not po:
            continue
        tracking = tracking_by_po.get(po)
        if not tracking:
            print(f"ASN row {i}: no tracking for PO {po}")
            continue
        tracking_input = page.locator(f"[data-testid='asn.order.{i}.packInfo.0.trackingNumber-input__input']")
        if tracking_input.count() == 0:
            print(f"ASN row {i}: tracking input not found for PO {po}")
            continue
        tracking_input.first.fill(tracking)
        filled += 1
    print(f"ASN tracking filled: {filled}/{total} rows")
    return filled, total


def select_all_asn_orders(page: Page) -> None:
    # Prefer header checkbox in ASN table.
    if click_first_visible(
        page,
        [
            "thead label.sps-checkable__label",
            "xpath=(//label[contains(@class,'sps-checkable__label')])[1]",
        ],
        timeout_ms=8000,
    ):
        return
    raise RuntimeError("Could not click ASN 'select all' checkbox.")


def send_documents(page: Page) -> None:
    if not click_first_visible(
        page,
        [
            "button:has(i.sps-icon-paper-plane)",
            "[role='button']:has(i.sps-icon-paper-plane)",
            "xpath=//*[contains(@class,'sps-icon-paper-plane')]/ancestor::*[self::button or @role='button'][1]",
        ],
        timeout_ms=10000,
    ):
        raise RuntimeError("Could not click 'Send Documents' button.")

    if not click_first_visible(
        page,
        [
            "button[data-testid='modalOkBtn'][title='Continue']",
            "button[data-testid='modalOkBtn']:has-text('Continue')",
        ],
        timeout_ms=10000,
    ):
        raise RuntimeError("Could not click modal 'Continue'.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SPS Commerce Tractor Supply tracking automation after inventory submission."
    )
    parser.add_argument(
        "--csv-path",
        default=str(CSV_PATH),
        help=f"Path to UPS CSV export. Default: {CSV_PATH}",
    )
    parser.add_argument(
        "--submit",
        action="store_true",
        help="Actually send documents. Omit for dry run (fills/selects but does not send).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser headless (default false).",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    csv_path = Path(args.csv_path)
    try:
        tracking_by_po = load_tracking_map(csv_path)
        print(f"Loaded {len(tracking_by_po)} PO->tracking entries from {csv_path}")
        if not tracking_by_po:
            print("No tracking rows loaded from CSV; stopping.")
            return 1

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=bool(args.headless))
            context = browser.new_context()
            page = context.new_page()
            try:
                goto_dashboard(page)
                open_ready_for_shipment(page)
                stats = select_orders_with_tracking(page, tracking_by_po)
                if stats.rows_checked == 0:
                    print("No SPS orders matched CSV tracking. Nothing to send.")
                    return 0

                open_create_new_asn(page)
                fill_asn_date(page)
                filled, total = fill_tracking_on_asn(page, tracking_by_po)
                if filled == 0:
                    print("No ASN rows were filled with tracking; stopping.")
                    return 1

                select_all_asn_orders(page)
                if args.submit:
                    send_documents(page)
                    print(f"Send Documents submitted (filled {filled}/{total} ASN rows).")
                else:
                    print("Dry run: skipping Send Documents. Re-run with --submit to finalize.")
                return 0
            finally:
                context.close()
                browser.close()
    except TimeoutError as ex:
        print(f"Playwright timeout: {ex}")
        return 2
    except Exception as ex:
        print(f"Error: {ex}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
