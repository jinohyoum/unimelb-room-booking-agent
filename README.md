
# Unimelb Room Booking Agent

Autonomous browser agent that books University of Melbourne library rooms using FastAPI, Playwright, and OpenRouter (with a path to Lux + E2B for “real” computer-use in the cloud).

---

## What this does

This service exposes HTTP endpoints that:

1. **Book a room via API**  
   - `POST /book_room` with structured JSON  
   - Uses Playwright to open Chromium, navigate to the UniMelb library booking site, and complete the booking flow.

2. **Book via natural language (later phase)**  
   - `POST /chat_book` with messages like:  
     > “Book me a Baillieu room tomorrow 2–4pm for 4 people”  
   - LLM (via OpenRouter) parses to structured booking params, then calls the same booking flow.

3. **Evolve into a real “computer-use” agent (later)**  
   - Local Playwright loop → E2B remote desktop + Lux as the action-selection model.

---

## Stack Overview

**Language & runtime**

- Python 3.11

**Backend / Orchestrator**

- [FastAPI](https://fastapi.tiangolo.com/) – HTTP API (`/health`, `/book_room`, `/chat_book`)
- [Uvicorn](https://www.uvicorn.org/) – ASGI server
- SQLite / JSON logs – store booking traces & debugging info

**Browser / “Computer” (local-first)**

- [Playwright for Python](https://playwright.dev/python/) – launches Chromium, handles login, clicks, forms  
- Runs non-headless in dev so you can visually debug flows

**LLM Layer (via OpenRouter)**

- OpenRouter HTTP API
- Start with a cheap reasoning model for:
  - Natural language → structured booking request
  - (Later) step-by-step “next action” for browser control

**Later: Cloud & computer-use**

- [E2B](https://e2b.dev/) – remote Ubuntu desktop + browser
- [Lux](https://agiopen.org/) – computer-use model for selecting actions inside the browser

---

## Repo structure

Planned structure:

```bash
room-agent/
  app/
    __init__.py
    main.py          # FastAPI app, endpoints (/health, /book_room, /chat_book)
    config.py        # Settings, env vars, API keys
    schemas.py       # Pydantic models (BookingRequest, BookingResult, ChatRequest, etc.)
    orchestrator.py  # High-level booking flow
    llm_client.py    # OpenRouter / Lux wrappers
    browser/
      __init__.py
      playwright_client.py  # Browser lifecycle + basic helpers
      flows.py              # Scripted booking steps (login, select date, room, confirm)
  tests/
    test_health.py
    test_schemas.py
  .env.example
  pyproject.toml or requirements.txt
  README.md
