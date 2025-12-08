"""FastAPI entrypoint for the room booking agent."""

from fastapi import FastAPI

from app.schemas import BookingRequest, BookingResponse

app = FastAPI(title="Unimelb Room Booking Agent", version="0.1.0")


@app.post("/book_room", response_model=BookingResponse)
async def book_room(request: BookingRequest) -> BookingResponse:
    """Stub endpoint that accepts booking details and returns a placeholder response."""
    return BookingResponse(
        status="stubbed",
        message="Booking not actually implemented yet",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    """Simple health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)

