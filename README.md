# Unimelb Room Booking Agent

Playwright automation plus a light FastAPI surface and an optional LLM helper to book University of Melbourne library rooms.

## What works today
- Browser flow (`app/browser/booking_flow.py`): opens Chromium, logs in to DiBS, searches, picks a room, fills details, and saves `storage_state.json` for faster repeat runs.
- CLI helper (`app/booking_agent.py`): turns natural language into booking fields via OpenAI, then launches the Playwright flow with those values.
- FastAPI entrypoint (`app/main.py`): `/health` works; `/book_room` is a stub placeholder.

## Setup
- Python 3.11
- Install deps: `pip install fastapi uvicorn openai playwright`
- Install browser: `python -m playwright install chromium`
- Env: `DIBS_USERNAME`, `DIBS_PASSWORD`; `OPENAI_API_KEY` if using the LLM helper.

## Run the browser probe
`python -m app.browser.booking_flow`

Uses any booking details found in `example_booking.json` if you create one (keys: `space`, `preferred_library`, `min_capacity`, `date`, `start_time`, `end_time`, `event_name`). After a successful run it writes `storage_state.json` so you can reuse the session.

## Use the CLI booking helper
`python -m app.booking_agent`

Describe the booking in natural language; it normalizes the fields, summarizes them back to you, and on confirmation launches the Playwright flow (headless is currently unreliable; prefer headed).

## FastAPI (stub)
Run `uvicorn app.main:app --reload` and hit:
- `GET /health` -> `{ "status": "ok" }`
- `POST /book_room` -> placeholder status/message for now

## Repo layout
- `app/main.py` - FastAPI app with health + stub booking endpoint
- `app/schemas.py` - Pydantic request/response models
- `app/booking_agent.py` - natural-language → booking fields, optional Playwright launch
- `app/browser/booking_flow.py` - Playwright login/search/book flow
- `storage_state.json` - persisted auth state (ignored by git)

## Possible improvements
- Add cancel-booking support.
- Make the chatbot more flexible (clarifying questions, updates mid-flow).
- Reduce booking latency (tune waits, reuse context more aggressively).
- Fix headless mode.
- If a slot is full, check nearby times within ±30 minutes or suggest other libraries at the same time.
- Experiment with computer-use models like Lux; flow is mostly deterministic so keep it simple-first.
