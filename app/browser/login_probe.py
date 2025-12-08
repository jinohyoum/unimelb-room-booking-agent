import asyncio
from urllib.parse import urlsplit

from playwright.async_api import async_playwright

LOGIN_URL = "https://library.unimelb.edu.au/services/book-a-room-or-computer"


async def main() -> None:
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

        # Keep the browser open until YOU decide to close it
        print("Browser is open. Do your thing, then press Enter in the terminal to close it...")
        input()  # blocks until you press Enter

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
