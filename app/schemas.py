"""Pydantic schemas for the booking API."""

from datetime import date, time
from typing import Optional

from pydantic import BaseModel, Field


class BookingRequest(BaseModel):

    library: str = Field(..., description="Library name, e.g., Baillieu")
    event_name: str = Field(..., description="Name of the event to display in booking")
    event_type: str = Field(..., description="Type/category of the event to select")
    date: date = Field(..., description="Booking date (DD-MM-YYYY)")
    start_time: time = Field(..., description="Start time (HH:MM, 24-hour)")
    end_time: time = Field(..., description="End time (HH:MM, 24-hour)")
    room_size: int = Field(..., description="Number of people")
    notes: Optional[str] = Field(None, description="Optional notes for the booking")


class BookingResponse(BaseModel):
    status: str = Field(..., description="Status of the booking request")
    message: str = Field(..., description="Additional details about the outcome")

