"""Browser automation flows for room booking."""

# Import the main booking_flow module explicitly to avoid circular imports
# when loaded from app.booking_agent.
from app.browser import booking_flow as booking_flow  # type: ignore

__all__ = ["booking_flow"]
