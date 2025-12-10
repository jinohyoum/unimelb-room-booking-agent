import asyncio
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional
from urllib.parse import urlsplit

from playwright.async_api import Page, async_playwright

LOGIN_URL = "https://library.unimelb.edu.au/services/book-a-room-or-computer"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_BOOKING_PATH = PROJECT_ROOT / "example_booking.json"
STORAGE_STATE_PATH = PROJECT_ROOT / "storage_state.json"


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


@lru_cache(maxsize=1)
def _booking_data() -> dict[str, Any]:
    """Read example_booking.json once and cache it for repeated lookups."""
    try:
        return json.loads(EXAMPLE_BOOKING_PATH.read_text())
    except Exception:
        # If the fixture is missing, fall back to empty defaults.
        return {}


def _booking_str(key: str, default: str) -> str:
    value = _booking_data().get(key, default)
    return (str(value).strip() or default) if value is not None else default


def _booking_int(key: str, default: int) -> int:
    try:
        value = _booking_data().get(key, default)
        return int(value)
    except Exception:
        return default


def get_space_label(default: str = "Book a Space in a Library") -> str:
    return _booking_str("space", default)


def get_booking_date(default: str = "") -> str:
    return _booking_str("date", default)


def get_booking_start_time(default: str = "") -> str:
    return _booking_str("start_time", default)


def get_booking_end_time(default: str = "") -> str:
    return _booking_str("end_time", default)


def get_preferred_library(default: str = "") -> str:
    return _booking_str("preferred_library", default)


def get_min_capacity(default: int = 0) -> int:
    return _booking_int("min_capacity", default)


def get_event_name(default: str = "") -> str:
    return _booking_str("event_name", default)


async def set_attendees_to_min_capacity(page: Page) -> None:
    """Fill the Number of Attendees spinner with the configured min capacity."""

    min_capacity = get_min_capacity()
    try:
        attendees_input = page.get_by_role("spinbutton", name="Number of Attendees")
        await attendees_input.wait_for(state="visible", timeout=5000)
        await attendees_input.click()
        await attendees_input.fill("")
        await attendees_input.type(str(min_capacity), delay=20)
    except Exception as exc:
        print(f"Could not set Number of Attendees: {exc}")


async def select_first_room(page: Page) -> None:
    """Pick the first room result and add it to the cart."""

    preferred_library = get_preferred_library()
    min_capacity = get_min_capacity()

    tbody_selector = (
        'tbody[data-bind="foreach: { data: listRoomResults, afterRender: bindMatchTooltips }"]'
    )
    result_rows = page.locator(f"{tbody_selector} tr[data-recordtype='1']")
    first_row = result_rows.first
    await first_row.wait_for(state="visible", timeout=5000)

    target_row = first_row
    if preferred_library or min_capacity > 0:
        row_count = await result_rows.count()
        preferred_lower = preferred_library.strip().lower()
        matched = False
        for idx in range(row_count):
            candidate = result_rows.nth(idx)

            building_locator = candidate.locator("a[data-bind*='BuildingDescription']").first
            building = ""
            try:
                building = (await building_locator.inner_text()).strip()
            except Exception:
                building = ""

            capacity_cell = candidate.locator("td[tabindex='0'][data-bind='text: Capacity']").first
            capacity_value = 0
            try:
                capacity_text = (await capacity_cell.inner_text()).strip()
                capacity_value = int(capacity_text or 0)
            except Exception:
                capacity_value = 0

            library_ok = not preferred_library or building.lower() == preferred_lower
            capacity_ok = capacity_value >= min_capacity

            if library_ok and capacity_ok:
                target_row = candidate
                matched = True
                break

        if not matched:
            # No exact match; just take the first available option.
            pass

    await target_row.scroll_into_view_if_needed()

    description_locator = target_row.locator("a[data-bind*='RoomDescription']").first
    description = ""
    try:
        description = (await description_locator.inner_text()).strip()
    except Exception:
        description = ""
    add_to_cart = target_row.locator("td.action-button-column a.add-to-cart").first
    icon = add_to_cart.locator("i.fa-plus-circle").first
    await add_to_cart.wait_for(state="visible", timeout=10_000)
    await icon.wait_for(state="visible", timeout=10_000)
    await add_to_cart.scroll_into_view_if_needed()

    await add_to_cart.click()


async def add_space_and_next_step(page: Page) -> None:
    """Click Add Space and proceed to Next Step."""

    try:
        add_space_btn = page.get_by_role("button", name="Add Space")
        await add_space_btn.wait_for(state="visible", timeout=10_000)
        await add_space_btn.scroll_into_view_if_needed()
        await add_space_btn.click()
    except Exception as exc:
        print(f"Could not click Add Space: {exc}")

    # Small pause to let the UI update before proceeding.
    await page.wait_for_timeout(5000)

    try:
        next_step_btn = page.get_by_role("button", name="Next Step")
        await next_step_btn.wait_for(state="visible", timeout=10_000)
        await next_step_btn.scroll_into_view_if_needed()
        await next_step_btn.click()
    except Exception as exc:
        print(f"Could not click Next Step: {exc}")


async def fill_event_and_submit(page: Page) -> None:
    """Fill event details, accept terms, and create the reservation."""

    # Event name textbox
    event_name = get_event_name()
    try:
        event_input = page.get_by_role("textbox", name="Event Name * Event Name *")
        await event_input.wait_for(state="visible", timeout=5000)
        await event_input.scroll_into_view_if_needed()
        await event_input.click()
        await event_input.fill("")
        await event_input.type(event_name, delay=20)
    except Exception as exc:
        print(f"Could not fill event name: {exc}")

    # Terms and conditions checkbox (via label click)
    try:
        terms_label = page.locator("label").filter(
            has_text="I have read and agree to the Terms and Conditions"
        ).first
        await terms_label.wait_for(state="visible", timeout=5000)
        await terms_label.scroll_into_view_if_needed()
        await terms_label.click()
    except Exception as exc:
        print(f"Could not check Terms and Conditions: {exc}")

    # Create Reservation
    try:
        create_btn = page.locator("#details").get_by_role("button", name="Create Reservation")
        await create_btn.wait_for(state="visible", timeout=5000)
        await create_btn.scroll_into_view_if_needed()
        await create_btn.click()
        print("Room booked.")
    except Exception as exc:
        print(f"Could not click Create Reservation: {exc}")


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

    space_label = get_space_label()
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, slow_mo=slow_mo_ms)
        storage_state = str(STORAGE_STATE_PATH) if STORAGE_STATE_PATH.exists() else None
        context = await browser.new_context(
            storage_state=storage_state,
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()
        page.set_default_timeout(30_000)
        reached_landing = False

        await page.goto(LOGIN_URL, wait_until="domcontentloaded")
        await page.wait_for_load_state("networkidle")
        if headless:
            try:
                await page.screenshot(path="headless-pre-dibs.png", full_page=True)
            except Exception as exc:
                print(f"Could not take pre-click screenshot: {exc}")

        # Optional: check we're on the right host BEFORE clicking
        current = page.url
        expected_host = urlsplit(LOGIN_URL).netloc
        assert urlsplit(current).netloc == expected_host

        # Click the DiBS button (more patiently for headless)
        try:
            await page.wait_for_load_state("networkidle")
            dibs_link = page.get_by_role("link", name="Book a room - DiBS")
            await dibs_link.wait_for(state="visible", timeout=15_000)
            await dibs_link.scroll_into_view_if_needed()
            await dibs_link.click()
        except Exception as exc:
            print(f"Could not click 'Book a room - DiBS': {exc}")
            try:
                await page.screenshot(path="headless-fail-dibs.png", full_page=True)
            except Exception:
                pass
            await browser.close()
            return
        await page.wait_for_load_state("networkidle")
        await page.wait_for_timeout(1000)

        login_prompt_visible = False
        try:
            login_prompt_visible = await page.get_by_role("textbox", name="Username").is_visible()
        except Exception:
            login_prompt_visible = False

        if username and login_prompt_visible:
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
        elif not login_prompt_visible:
            pass

        # Proceed into the booking flow landing page (footer link)
        try:
            footer_link = page.locator("a.link-footer[href*='RoomRequest.aspx']")
            await footer_link.wait_for(state="visible", timeout=5000)
            await footer_link.scroll_into_view_if_needed()
            await footer_link.click()
        except Exception:
            try:
                # Fallback: sidebar link id if footer not present
                await page.wait_for_selector("a#sidebar-wrapper-home", timeout=5000)
                link = page.locator("a#sidebar-wrapper-home")
                await link.scroll_into_view_if_needed()
                await link.click()
            except Exception as exc:
                print(f"Could not click 'Create A Reservation': {exc}")
        await page.wait_for_load_state("networkidle")
        reached_landing = True

        # After the reservation landing page loads, click the configured space tile,
        # then click the specific "book now" button shown in the inspected markup.
        try:
            await page.wait_for_load_state("networkidle")
            book_space_tile = page.get_by_text(space_label, exact=True)
            await book_space_tile.wait_for(state="visible", timeout=5000)
            await book_space_tile.scroll_into_view_if_needed()
            await book_space_tile.click()

            # Button aria-label pattern: Book Now With The "<space_label>" Template
            book_now_button = page.get_by_role(
                "button",
                name=f'Book Now With The "{space_label}" Template',
            )
            await book_now_button.wait_for(state="visible", timeout=5000)
            await book_now_button.scroll_into_view_if_needed()
            await book_now_button.click()

            # Fill the date field using the booking-date container locator.
            booking_date = get_booking_date()
            if booking_date:
                try:
                    date_input = page.locator("#booking-date input").first
                    await date_input.wait_for(state="visible", timeout=5000)
                    await date_input.click()
                    await date_input.fill("")
                    await date_input.type(booking_date, delay=20)
                    await date_input.press("Enter")
                except Exception as exc:
                    print(f"Could not fill date via #booking-date input: {exc}")

            # Fill start time
            start_time = get_booking_start_time()
            if start_time:
                try:
                    start_input = page.get_by_label("StartTime Required.")
                    await start_input.wait_for(state="visible", timeout=5000)
                    await start_input.click()
                    await start_input.fill("")
                    await start_input.type(start_time, delay=20)
                    await start_input.press("Enter")
                except Exception as exc:
                    print(f"Could not fill start time: {exc}")

            # Fill end time
            end_time = get_booking_end_time()
            if end_time:
                try:
                    end_input = page.get_by_label("EndTime Required.")
                    await end_input.wait_for(state="visible", timeout=5000)
                    await end_input.click()
                    await end_input.fill("")
                    await end_input.type(end_time, delay=20)
                    await end_input.press("Enter")
                except Exception as exc:
                    print(f"Could not fill end time: {exc}")

            # Click Search within Date & Time group
            try:
                search_button = page.get_by_label("Date & Time").get_by_role("button", name="Search")
                await search_button.wait_for(state="visible", timeout=5000)
                await search_button.click()
                try:
                    await select_first_room(page)
                    await set_attendees_to_min_capacity(page)
                    await add_space_and_next_step(page)
                    await fill_event_and_submit(page)
                except Exception as exc:
                    print(f"Could not select first room: {exc}")
            except Exception as exc:
                print(f"Could not click Search button: {exc}")
        except Exception as exc:
            print(f"Could not click space '{space_label}' / book-now button: {exc}")

        if post_login:
            await post_login(page)

        # Keep the browser open until YOU decide to close it
        if pause_before_close:
            # Leave the browser open so a human can poke around before exit.
            print("Browser is open. Do your thing, then press Enter in the terminal to close it...")
            input()  # blocks until you press Enter

        if reached_landing:
            try:
                await page.context.storage_state(path=str(STORAGE_STATE_PATH))
            except Exception as exc:
                print(f"Could not save storage state: {exc}")

        await browser.close()


async def main() -> None:
    await run_login_probe()


if __name__ == "__main__":
    asyncio.run(main())

