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


def _perform_sps_login(page, username: str, password: str, timeout_ms: int) -> None:
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
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
            _save_screenshot(page, "after_login")

            # ── Click Transactions tab ─────────────────────────────────────────
            page.locator("a[data-testid='transactions_tab']").click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
            _save_screenshot(page, "transactions_tab")

            # ── Clear search fields ────────────────────────────────────────────
            clear_btn = page.locator("button[data-testid='advSearchBottomClearButton']").first
            if clear_btn.is_visible(timeout=5000):
                clear_btn.click()
                page.wait_for_timeout(1000)

            # ── Search for inventory ───────────────────────────────────────────
            search_input = page.locator("input[data-testid='searchField__input']")
            search_input.wait_for(state="visible", timeout=settings.timeout_ms)
            search_input.fill("inventory")
            page.locator("i.sps-icon-search").first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
            _save_screenshot(page, "search_results")

            # ── Click New ──────────────────────────────────────────────────────
            page.locator("button[data-testid='createNewBtn']").click()
            page.wait_for_timeout(2000)
            _save_screenshot(page, "new_dialog")

            # ── Select 'Inventory Main' template from dropdown ─────────────────
            page.locator("[data-testid='createNewDocTemplateSelector-value']").click()
            page.wait_for_timeout(1000)
            page.locator("text=Inventory Main").first.click()
            page.wait_for_timeout(1000)
            _save_screenshot(page, "template_selected")

            # ── Click Create New ───────────────────────────────────────────────
            page.locator("button[data-testid='modalOkBtn'][title='Create New']").click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(3000)
            _save_screenshot(page, "form_loaded")

            # ── Expand SHORT section ───────────────────────────────────────────
            short_btn = page.locator("button[data-testid='dataEntryCard__expanding']")
            short_btn.wait_for(state="visible", timeout=settings.timeout_ms)
            short_btn.click()
            page.wait_for_timeout(1500)
            _save_screenshot(page, "short_expanded")

            # ── Set Report Date to today ───────────────────────────────────────
            date_field = page.locator("input[data-testid='inventoryAdvice.header.reportDate2-input_date_input']")
            date_field.wait_for(state="visible", timeout=settings.timeout_ms)
            date_field.triple_click()
            date_field.fill(today)
            page.keyboard.press("Tab")
            page.wait_for_timeout(500)
            _save_screenshot(page, "date_set")

            # ── Click Send (paper-plane icon button) ───────────────────────────
            page.locator("button:has(i.sps-icon-paper-plane)").first.click()
            page.wait_for_timeout(2000)
            _save_screenshot(page, "send_clicked")

            # ── Click Continue on confirmation dialog ──────────────────────────
            page.locator("button[data-testid='modalOkBtn'][title='Continue']").click()
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
