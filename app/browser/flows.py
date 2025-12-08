"""Reusable Playwright flows for UniMelb library room bookings.

These helpers are intentionally selector-driven so that you can drop in
the locators produced by `playwright codegen` without rewriting control
flow. Each function assumes you pass selectors that make sense for the
current page.
"""

from __future__ import annotations

from datetime import date, time
from typing import Optional

from playwright.async_api import Page, TimeoutError  # type: ignore[import-untyped]

# Base timeout used across steps; override per call if needed.
DEFAULT_TIMEOUT_MS = 15_000


def _date_str(value: date) -> str:
    return value.strftime("%d-%m-%Y")


def _time_str(value: time) -> str:
    return value.strftime("%H:%M")


async def login_if_needed(
    page: Page,
    *,
    login_url: str,
    username: str,
    password: str,
    username_selector: str,
    password_selector: str,
    submit_selector: str,
    logged_in_selector: str,
    two_factor_pause_ms: int = 20_000,
) -> None:
    """Log in only when the logged-in marker is absent.

    The function pauses after submitting credentials to allow manual 2FA.
    """

    if await page.query_selector(logged_in_selector):
        return

    await page.goto(login_url, wait_until="networkidle")
    await page.fill(username_selector, username)
    await page.fill(password_selector, password)
    await page.click(submit_selector)
    await page.wait_for_timeout(two_factor_pause_ms)
    await page.wait_for_selector(
        logged_in_selector,
        timeout=DEFAULT_TIMEOUT_MS + two_factor_pause_ms,
    )


async def select_template(
    page: Page,
    *,
    library_selector: str,
    library_value: str,
    event_name_selector: str,
    event_name: str,
    event_type_selector: str,
    event_type_value: str,
    continue_selector: Optional[str] = None,
) -> None:
    """Fill the template or initial booking form."""

    await page.select_option(library_selector, label=library_value)
    await page.fill(event_name_selector, event_name)
    await page.select_option(event_type_selector, label=event_type_value)

    if continue_selector:
        await page.click(continue_selector)


async def select_date_and_time(
    page: Page,
    *,
    date_selector: str,
    booking_date: date,
    start_time_selector: str,
    start_time_value: time,
    end_time_selector: str,
    end_time_value: time,
    search_selector: Optional[str] = None,
    wait_selector: Optional[str] = None,
) -> None:
    """Apply date and time filters to show available rooms."""

    await page.fill(date_selector, _date_str(booking_date))
    await page.fill(start_time_selector, _time_str(start_time_value))
    await page.fill(end_time_selector, _time_str(end_time_value))

    if search_selector:
        await page.click(search_selector)

    if wait_selector:
        await page.wait_for_selector(wait_selector, timeout=DEFAULT_TIMEOUT_MS)


async def select_room(
    page: Page,
    *,
    room_name: str,
    room_card_selector: str,
    reserve_button_selector: str,
    continue_selector: Optional[str] = None,
    wait_selector: Optional[str] = None,
) -> None:
    """Pick a room card by name and proceed."""

    room_card = await page.wait_for_selector(
        room_card_selector.format(room=room_name),
        timeout=DEFAULT_TIMEOUT_MS,
    )
    await room_card.click()

    await page.click(reserve_button_selector)

    if wait_selector:
        await page.wait_for_selector(wait_selector, timeout=DEFAULT_TIMEOUT_MS)

    if continue_selector:
        await page.click(continue_selector)


async def confirm_booking(
    page: Page,
    *,
    confirm_selector: str,
    success_selector: Optional[str] = None,
    screenshot_path: Optional[str] = None,
) -> None:
    """Finalize the booking and optionally wait for success."""

    await page.click(confirm_selector)

    if success_selector:
        try:
            await page.wait_for_selector(success_selector, timeout=DEFAULT_TIMEOUT_MS)
        except TimeoutError:
            # If the page changes immediately, the selector may not be present; let caller decide.
            pass

    if screenshot_path:
        await page.screenshot(path=screenshot_path, full_page=True)
