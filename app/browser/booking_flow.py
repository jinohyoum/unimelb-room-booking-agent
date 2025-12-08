import asyncio
import json
import os
from pathlib import Path
from typing import Awaitable, Callable, Optional
from urllib.parse import urlsplit

from playwright.async_api import Page, async_playwright

LOGIN_URL = "https://library.unimelb.edu.au/services/book-a-room-or-computer"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_BOOKING_PATH = PROJECT_ROOT / "example_booking.json"


def load_env() -> None:
    """Lightweight .env loader without external deps."""
    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def load_space_label(default: str = "Book a Space in a Library") -> str:
    """Return the space label from example_booking.json, falling back to default."""
    try:
        data = json.loads(EXAMPLE_BOOKING_PATH.read_text())
        return str(data.get("space", default)) or default
    except Exception:
        return default


async def run_login_probe(
    *,
    slow_mo_ms: int = 400,
    headless: bool = False,
    post_login: Optional[Callable[[Page], Awaitable[None]]] = None,
    pause_before_close: bool = True,
) -> None:
    """Open the booking site, log in, then optionally run extra steps."""

    load_env()
    username = os.getenv("DIBS_USERNAME", "")
    password = os.getenv("DIBS_PASSWORD", "")

    space_label = load_space_label()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo_ms)
        page = await browser.new_page()

        await page.goto(LOGIN_URL, wait_until="domcontentloaded")

        # Optional: check we're on the right host BEFORE clicking
        current = page.url
        expected_host = urlsplit(LOGIN_URL).netloc
        assert urlsplit(current).netloc == expected_host

        # Click the DiBS button
        await page.get_by_role("link", name="Book a room - DiBS").click()
        await page.wait_for_load_state("networkidle")

        if username:
            try:
                await page.get_by_role("textbox", name="Username").fill(username)
                await page.get_by_role("button", name="Next").click()
                if password:
                    await page.get_by_role("textbox", name="Password").fill(password)
                    await page.get_by_role("button", name="Verify").click()
                    print("Awaiting 2FA on phone...")
                    try:
                        # Click the Okta Verify push option explicitly
                        push_button = page.locator(
                            'div.authenticator-button[data-se="okta_verify-push"] a[data-se="button"]'
                        )
                        await push_button.wait_for(state="visible")
                        await push_button.click()
                    except Exception as exc:
                        print(f"Could not click the second 'Select' button: {exc}")
            except Exception as exc:
                print(f"Could not auto-fill username: {exc}")
        else:
            print("Set DIBS_USERNAME in .env to auto-fill the username field.")

        # Proceed into the booking flow landing page (footer link)
        try:
            footer_link = page.locator("a.link-footer[href*='RoomRequest.aspx']")
            await footer_link.wait_for(state="visible", timeout=10_000)
            await footer_link.scroll_into_view_if_needed()
            await footer_link.click()
        except Exception:
            try:
                # Fallback: sidebar link id if footer not present
                await page.wait_for_selector("a#sidebar-wrapper-home", timeout=10_000)
                link = page.locator("a#sidebar-wrapper-home")
                await link.scroll_into_view_if_needed()
                await link.click()
            except Exception as exc:
                print(f"Could not click 'Create A Reservation': {exc}")
        await page.wait_for_load_state("networkidle")

        # After the reservation landing page loads, click the configured space tile,
        # then click the specific "book now" button shown in the inspected markup.
        try:
            book_space_tile = page.get_by_text(space_label, exact=True)
            await book_space_tile.wait_for(state="visible", timeout=10_000)
            await book_space_tile.scroll_into_view_if_needed()
            await book_space_tile.click()

            # Button aria-label pattern: Book Now With The "<space_label>" Template
            book_now_button = page.get_by_role(
                "button",
                name=f'Book Now With The "{space_label}" Template',
            )
            await book_now_button.wait_for(state="visible", timeout=10_000)
            await book_now_button.scroll_into_view_if_needed()
            await book_now_button.click()
        except Exception as exc:
            print(f"Could not click space '{space_label}' / book-now button: {exc}")

        if post_login:
            await post_login(page)

        # Keep the browser open until YOU decide to close it
        if pause_before_close:
            print("Browser is open. Do your thing, then press Enter in the terminal to close it...")
            input()  # blocks until you press Enter

        await browser.close()


async def main() -> None:
    await run_login_probe()


if __name__ == "__main__":
    asyncio.run(main())