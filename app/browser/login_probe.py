import asyncio
import os
from pathlib import Path
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

LOGIN_URL = "https://library.unimelb.edu.au/services/book-a-room-or-computer"
PROJECT_ROOT = Path(__file__).resolve().parents[2]


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


async def main() -> None:
    load_env()
    username = os.getenv("DIBS_USERNAME", "")
    password = os.getenv("DIBS_PASSWORD", "")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, slow_mo=400)
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

        # Keep the browser open until YOU decide to close it
        print("Browser is open. Do your thing, then press Enter in the terminal to close it...")
        input()  # blocks until you press Enter

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())