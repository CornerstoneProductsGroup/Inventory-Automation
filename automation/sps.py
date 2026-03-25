from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from automation.config import load_settings


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _save_screenshot(page, name: str) -> None:
    shots_dir = Path("screenshots")
    shots_dir.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(shots_dir / f"{_timestamp()}_sps_{name}.png"), full_page=True)


def _get_frame(page, selector: str, timeout_ms: int = 5000):
    """Return the first frame (main page or iframe) where selector is visible."""
    # Try main page first
    try:
        loc = page.locator(selector).first
        if loc.is_visible(timeout=timeout_ms):
            return page
    except Exception:
        pass
    # Search all iframes
    for frame in page.frames:
        try:
            loc = frame.locator(selector).first
            if loc.is_visible(timeout=timeout_ms):
                return frame
        except Exception:
            continue
    raise RuntimeError(f"Could not find '{selector}' on page or in any iframe.")



    # Step 1: Enter username and click Next.
    page.locator("input[name='username']").wait_for(state="visible", timeout=timeout_ms)
    page.locator("input[name='username']").fill(username)
    page.locator("button._button-login-id").click()

    # Step 2: Enter password and click Next.
    page.locator("input[name='password']").wait_for(state="visible", timeout=timeout_ms)
    page.locator("input[name='password']").fill(password)
    page.locator("button._button-login-password").click()
    page.wait_for_load_state("domcontentloaded")


def run_sps_inventory_update() -> None:
    settings = load_settings()
    today = datetime.now().strftime("%m/%d/%Y")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(settings.timeout_ms)

        try:
            # ── Login ──────────────────────────────────────────────────────────
            page.goto(settings.sps_url, wait_until="domcontentloaded")
            _perform_sps_login(page, settings.sps_username, settings.sps_password, settings.timeout_ms)
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(5000)
            _save_screenshot(page, "after_login")

            # ── Click Fulfillment tile ─────────────────────────────────────────────
            # The tile is an <a> or clickable parent wrapping the cube svg img.
            # Try direct page first, then fall back to searching inside iframes.
            fulfillment_selectors = [
                "a:has(img[src*='cube'])",
                "a:has(img.sps-tile--image)",
                "button:has(img[src*='cube'])",
                "div.sps-tile:has(img[src*='cube'])",
                "img[src*='cube.svg']",
                "img.sps-tile--image",
            ]

            clicked = False
            for sel in fulfillment_selectors:
                try:
                    loc = page.locator(sel).first
                    if loc.is_visible(timeout=3000):
                        loc.click()
                        clicked = True
                        break
                except Exception:
                    continue

            if not clicked:
                # Portal may render inside an iframe — search all frames
                for frame in page.frames:
                    if clicked:
                        break
                    for sel in fulfillment_selectors:
                        try:
                            loc = frame.locator(sel).first
                            if loc.is_visible(timeout=3000):
                                loc.click()
                                clicked = True
                                break
                        except Exception:
                            continue

            if not clicked:
                raise RuntimeError("Could not find Fulfillment tile. Check screenshots for current page state.")
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(5000)
            _save_screenshot(page, "fulfillment_selected")

            # ── Navigate directly to Transactions list ────────────────────────────
            # The tab lives inside an iframe so direct navigation is more reliable.
            page.goto("https://commerce.spscommerce.com/fulfillment/transactions/list/", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            _save_screenshot(page, "transactions_tab")

            # ── Clear search fields ────────────────────────────────────────────
            try:
                f = _get_frame(page, "button[data-testid='advSearchBottomClearButton']", 5000)
                f.locator("button[data-testid='advSearchBottomClearButton']").first.click()
                page.wait_for_timeout(1000)
            except Exception:
                pass  # Clear button may not always be present

            # ── Type inventory in search bar and click search ──────────────────
            f = _get_frame(page, "input[data-testid='searchField__input']", settings.timeout_ms)
            f.locator("input[data-testid='searchField__input']").first.fill("inventory")
            f.locator("i.sps-icon-search").first.click()
            page.wait_for_timeout(2000)
            _save_screenshot(page, "search_results")

            # ── Click New ──────────────────────────────────────────────────────
            f = _get_frame(page, "button[data-testid='createNewBtn']", settings.timeout_ms)
            f.locator("button[data-testid='createNewBtn']").click()
            page.wait_for_timeout(2000)
            _save_screenshot(page, "new_dialog")

            # ── Select 'Inventory Main' template from dropdown ─────────────────
            f = _get_frame(page, "[data-testid='createNewDocTemplateSelector-value']", settings.timeout_ms)
            f.locator("[data-testid='createNewDocTemplateSelector-value']").click()
            page.wait_for_timeout(1000)
            f.locator("text=Inventory Main").first.click()
            page.wait_for_timeout(1000)
            _save_screenshot(page, "template_selected")

            # ── Click Create New ───────────────────────────────────────────────
            f = _get_frame(page, "button[data-testid='modalOkBtn'][title='Create New']", settings.timeout_ms)
            f.locator("button[data-testid='modalOkBtn'][title='Create New']").click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(3000)
            _save_screenshot(page, "form_loaded")

            # ── Expand SHORT section ───────────────────────────────────────────
            f = _get_frame(page, "button[data-testid='dataEntryCard__expanding']", settings.timeout_ms)
            f.locator("button[data-testid='dataEntryCard__expanding']").first.click()
            page.wait_for_timeout(1500)
            _save_screenshot(page, "short_expanded")

            # ── Set Report Date to today ───────────────────────────────────────
            f = _get_frame(page, "input[data-testid='inventoryAdvice.header.reportDate2-input_date_input']", settings.timeout_ms)
            date_field = f.locator("input[data-testid='inventoryAdvice.header.reportDate2-input_date_input']")
            date_field.triple_click()
            date_field.fill(today)
            f.locator("body").press("Tab")
            page.wait_for_timeout(500)
            _save_screenshot(page, "date_set")

            # ── Click Send (paper-plane icon button) ───────────────────────────
            f = _get_frame(page, "button:has(i.sps-icon-paper-plane)", settings.timeout_ms)
            f.locator("button:has(i.sps-icon-paper-plane)").first.click()
            page.wait_for_timeout(2000)
            _save_screenshot(page, "send_clicked")

            # ── Click Continue on confirmation dialog ──────────────────────────
            f = _get_frame(page, "button[data-testid='modalOkBtn'][title='Continue']", settings.timeout_ms)
            f.locator("button[data-testid='modalOkBtn'][title='Continue']").click()
            page.wait_for_load_state("domcontentloaded")
            _save_screenshot(page, "submitted")

            print(f"SPS Commerce (Tractor Supply) inventory update submitted successfully for {today}.")
        except PlaywrightTimeoutError as exc:
            _save_screenshot(page, "timeout_error")
            raise RuntimeError(f"SPS timed out during automation: {exc}") from exc
        except Exception as exc:
            _save_screenshot(page, "general_error")
            raise RuntimeError(f"SPS automation failed: {exc}") from exc
        finally:
            context.close()
            browser.close()
