"""Browser automation flows for room booking."""

from app.browser.flows import (
    confirm_booking,
    login_if_needed,
    select_date_and_time,
    select_room,
    select_template,
)

__all__ = [
    "confirm_booking",
    "login_if_needed",
    "select_date_and_time",
    "select_room",
    "select_template",
]
