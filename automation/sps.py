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
    # SPS Commerce uses Auth0 two-step login (same pattern as Rithum/CommerceHub).
    # Step 1: Enter username and click Next.
    page.locator("input[name='username']").wait_for(state="visible", timeout=timeout_ms)
    page.locator("input[name='username']").fill(username)
    page.locator("button._button-login-id").click()

    # Step 2: Enter password and click Continue.
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
            page.goto(settings.sps_url, wait_until="domcontentloaded")
            _perform_sps_login(page, settings.sps_username, settings.sps_password, settings.timeout_ms)
            _save_screenshot(page, "after_login")

            # Allow portal dashboard to fully render after auth redirect.
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
            _save_screenshot(page, "dashboard")

            # Click "Create New Transaction"
            page.locator("button:has-text('Create New Transaction'), a:has-text('Create New Transaction')").first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1500)
            _save_screenshot(page, "create_transaction")

            # Select "Inventory" from transaction type options
            page.locator("text=Inventory").first.click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(1500)
            _save_screenshot(page, "inventory_selected")

            # Set date to today
            date_field = page.locator("input[type='date'], input[name*='date'], input[id*='date']").first
            date_field.wait_for(state="visible", timeout=settings.timeout_ms)
            date_field.triple_click()
            date_field.fill(today)
            _save_screenshot(page, "date_set")

            # Click Send
            page.locator("button:has-text('Send'), input[value='Send']").first.click()
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
