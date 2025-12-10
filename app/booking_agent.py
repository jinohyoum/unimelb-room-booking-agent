"""Lightweight natural-language booking parser powered by OpenAI + local validation."""

from __future__ import annotations

import json
import os
import re
import sys
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo

from openai import OpenAI

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_BOOKING_PATH = PROJECT_ROOT / "example_booking.json"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

MEL_TZ = ZoneInfo("Australia/Melbourne")

SPACE_LABEL = "Book a Space in a Library"
ALLOWED_LIBRARIES = {
    "fbe building": "FBE Building",
    "eastern resource centre library": "EASTERN RESOURCE CENTRE LIBRARY",
    "baillieu library": "Baillieu Library",
    "southbank the hub": "Southbank The Hub",
    "werribee learning & teaching building": "Werribee Learning & Teaching Building",
}

LIBRARY_SYNONYMS = {
    "fbe": "FBE Building",
    "business and economics": "FBE Building",
    "erc": "EASTERN RESOURCE CENTRE LIBRARY",
    "eastern resource center": "EASTERN RESOURCE CENTRE LIBRARY",
    "baillieu": "Baillieu Library",
    "southbank": "Southbank The Hub",
    "the hub": "Southbank The Hub",
    "werribee": "Werribee Learning & Teaching Building",
    "learning and teaching building": "Werribee Learning & Teaching Building",
}


def _agent_prefix() -> str:
    """Return a bold/cyan Agent prefix, falling back to plain if color is disabled."""

    if os.getenv("NO_COLOR"):
        return "Agent:"
    return "\033[1;36m\033[1mAgent\033[0m:"


AGENT_PREFIX = _agent_prefix()


def _agent_print(message: str) -> None:
    """Print chatbot responses with a distinct prefix for readability."""

    if os.getenv("NO_COLOR"):
        print(f"Agent: {message}")
    else:
        print(f"{AGENT_PREFIX} \033[1m{message}\033[0m")


def _headless_flag(default: bool = True) -> bool:
    """Return True if headless browser is requested via env (default True)."""

    value = os.getenv("BOOKING_HEADLESS") or os.getenv("HEADLESS")
    if value == "1":
        return True
    if value == "0":
        return False
    return default


def load_env() -> None:
    """Lightweight .env loader (only sets variables that aren't already set)."""

    env_path = PROJECT_ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def _normalize_library(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    value = raw.strip().lower()
    if value in ALLOWED_LIBRARIES:
        return ALLOWED_LIBRARIES[value]
    # Accept loose nicknames by mapping to the canonical label.
    for key, canonical in LIBRARY_SYNONYMS.items():
        if key in value:
            return canonical
    return None


def _mel_now() -> datetime:
    return datetime.now(MEL_TZ)


def _next_weekday(target_weekday: int, *, prefer_next_week: bool = False) -> datetime:
    """Return the next occurrence of the weekday (0=Mon)."""

    today = _mel_now().date()
    base = today + (timedelta(days=7) if prefer_next_week else timedelta())
    days_ahead = (target_weekday - base.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    result_date = base + timedelta(days=days_ahead)
    return datetime.combine(result_date, datetime.min.time(), MEL_TZ)


def _parse_relative_date(text: str) -> Optional[datetime]:
    lowered = text.lower()
    weekdays = {
        "monday": 0,
        "tuesday": 1,
        "wednesday": 2,
        "thursday": 3,
        "friday": 4,
        "saturday": 5,
        "sunday": 6,
    }
    target = None
    for name, idx in weekdays.items():
        if name in lowered:
            target = idx
            break
    if target is None:
        return None

    prefer_next_week = "next week" in lowered
    return _next_weekday(target, prefer_next_week=prefer_next_week)


def _normalize_date(raw: Optional[str]) -> str:
    if not raw:
        return ""

    # Relative phrases like "next Thursday"
    relative = _parse_relative_date(raw)
    if relative:
        return relative.strftime("%d/%m/%Y")

    # Explicit formats with a year.
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%y", "%d %b %Y", "%d %B %Y"):
        try:
            parsed = datetime.strptime(raw.strip(), fmt).replace(tzinfo=MEL_TZ)
            return parsed.strftime("%d/%m/%Y")
        except Exception:
            continue

    # Day/month without a year -> assume this year, or next if already passed.
    for fmt in ("%d/%m", "%d-%m", "%d %b", "%d %B"):
        try:
            today = _mel_now().date()
            text = raw.strip()
            if "%b" in fmt or "%B" in fmt:
                text_fmt = f"{fmt} %Y"
                text_val = f"{text} {today.year}"
            elif "/" in fmt:
                text_fmt = fmt + "/%Y"
                text_val = f"{text}/{today.year}"
            elif "-" in fmt:
                text_fmt = fmt + "-%Y"
                text_val = f"{text}-{today.year}"
            else:
                text_fmt = fmt + " %Y"
                text_val = f"{text} {today.year}"

            candidate = datetime.strptime(text_val, text_fmt).replace(tzinfo=MEL_TZ)
            if candidate.date() < today:
                candidate = candidate.replace(year=today.year + 1)
            return candidate.strftime("%d/%m/%Y")
        except Exception:
            continue

    return ""


def _normalize_time(raw: Optional[str]) -> str:
    if not raw:
        return ""
    for fmt in ("%H:%M", "%H%M", "%I:%M%p", "%I:%M %p", "%I%p", "%I %p"):
        try:
            parsed = datetime.strptime(raw.strip(), fmt)
            return parsed.strftime("%H:%M")
        except Exception:
            continue
    return ""


def _normalize_capacity(raw: Any) -> int:
    try:
        return max(0, int(raw))
    except Exception:
        return 0


def _parse_json_payload(text: str) -> Dict[str, Any]:
    try:
        return json.loads(text)
    except Exception:
        # If the model wrapped JSON in chatter, grab the first brace block.
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise


def _validate_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    # Ensure every downstream consumer sees a consistent shape.
    return {
        "space": SPACE_LABEL,
        "preferred_library": _normalize_library(payload.get("preferred_library"))
        or None,
        "min_capacity": _normalize_capacity(payload.get("min_capacity")),
        "date": _normalize_date(payload.get("date")),
        "start_time": _normalize_time(payload.get("start_time")),
        "end_time": _normalize_time(payload.get("end_time")),
        "event_name": str(payload.get("event_name") or "").strip(),
    }


def booking_agent(prompt: str, *, model: str = "gpt-4o-mini") -> Dict[str, Any]:
    """Use OpenAI to draft booking fields, then enforce local normalization."""
    load_env()
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=api_key)
    system = (
        "You extract UniMelb library room booking fields from user messages. "
        "Respond ONLY with JSON with keys: space, preferred_library, min_capacity, "
        "date, start_time, end_time, event_name. "
        "space must be exactly 'Book a Space in a Library'. "
        "preferred_library must be null or one of: "
        "FBE Building, EASTERN RESOURCE CENTRE LIBRARY, Baillieu Library, "
        "Southbank The Hub, Werribee Learning & Teaching Building. "
        "For date, copy the user's wording (e.g., 'next Thursday' or '12/12'); "
        "do NOT invent or assume a year. "
        "time is HH:MM 24-hour. "
        "min_capacity is an integer. event_name is a short string."
    )

    completion = client.chat.completions.create(
        model=model,
        temperature=0,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
    )
    content = completion.choices[0].message.content or "{}"
    raw_payload = _parse_json_payload(content)
    return _validate_payload(raw_payload)


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.strip().lower())
    return slug.strip("-") or "booking"


def _filename_for_result(result: Dict[str, Any]) -> str:
    event_slug = _slugify(result.get("event_name", ""))
    date_str = result.get("date", "")
    day_month = ""
    if date_str and "/" in date_str:
        parts = date_str.split("/")
        if len(parts) >= 2:
            day_month = f"{parts[0]}-{parts[1]}"
    suffix = f"{event_slug}-{day_month}" if day_month else event_slug
    return f"{suffix}.json"


def booking_agent_to_file(
    prompt: str,
    *,
    model: str = "gpt-4o-mini",
    path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Run booking_agent and persist the result as example_booking-style JSON."""

    result = booking_agent(prompt, model=model)
    target = Path(path) if path else PROJECT_ROOT / _filename_for_result(result)
    target.write_text(json.dumps(result, indent=2))
    return result


def _write_payload_to_file(payload: Dict[str, Any], path: Optional[Path] = None) -> Path:
    target = Path(path) if path else PROJECT_ROOT / _filename_for_result(payload)
    target.write_text(json.dumps(payload, indent=2))
    return target


def _format_booking_summary(payload: Dict[str, Any]) -> str:
    """Return a compact, human summary of the booking."""
    library = payload.get("preferred_library") or "<?>"
    date = payload.get("date") or "<?>"
    start = payload.get("start_time") or "<?>"
    end = payload.get("end_time") or "<?>"
    capacity = payload.get("min_capacity") or 0
    event = payload.get("event_name") or "Booking"
    return f"{event} at {library} on {date} from {start}–{end} for {capacity} people."


class BookingSession:
    """Stateful helper to collect booking fields across turns."""

    def __init__(self, *, model: str = "gpt-4o-mini") -> None:
        self.model = model
        # Start with a blank-but-valid payload shape.
        self.fields: Dict[str, Any] = {
            "space": SPACE_LABEL,
            "preferred_library": None,
            "min_capacity": 0,
            "date": "",
            "start_time": "",
            "end_time": "",
            "event_name": "",
        }
        self.awaiting_confirmation = False

    def update_from_prompt(self, prompt: str, allowed: Optional[set[str]] = None) -> None:
        parsed = booking_agent(prompt, model=self.model)
        for key in self.fields:
            # When tweaking an existing summary, only touch the allowed fields.
            if allowed is not None and key not in allowed:
                continue
            value = parsed.get(key)
            if key == "min_capacity":
                if isinstance(value, int) and value > 0:
                    self.fields[key] = value
            elif isinstance(value, str):
                if value.strip():
                    self.fields[key] = value.strip()
            elif value:
                self.fields[key] = value

    def missing_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.fields["preferred_library"]:
            missing.append("library (pick from the allowed list)")
        if not self.fields["date"]:
            missing.append("date (DD/MM/YYYY)")
        if not self.fields["start_time"]:
            missing.append("start time (HH:MM)")
        if not self.fields["end_time"]:
            missing.append("end time (HH:MM)")
        if not self.fields["min_capacity"]:
            missing.append("capacity (integer)")
        if not self.fields["event_name"]:
            missing.append("event name")
        return missing

    def has_all_fields(self) -> bool:
        return not self.missing_fields()

    def payload(self) -> Dict[str, Any]:
        return {
            "space": SPACE_LABEL,
            "preferred_library": self.fields["preferred_library"],
            "min_capacity": int(self.fields["min_capacity"] or 0),
            "date": self.fields["date"],
            "start_time": self.fields["start_time"],
            "end_time": self.fields["end_time"],
            "event_name": self.fields["event_name"],
        }


def _looks_like_booking_intent(text: str) -> bool:
    lowered = text.lower()
    return any(
        kw in lowered
        for kw in ["book", "booking", "reserve", "room", "library room", "dibs"]
    )


def _is_yes(text: str) -> bool:
    """Detect natural 'yes' style confirmations."""
    normalized = text.strip().lower()
    direct_yes = {
        "yes",
        "y",
        "yeah",
        "yep",
        "yup",
        "ok",
        "okay",
        "sure",
        "confirm",
        "fine",
        "alright",
        "all good",
        "sounds good",
        "looks good",
        "go ahead",
        "go for it",
        "do it",
        "that’s fine",
        "thats fine",
        "lock it in",
    }
    if normalized in direct_yes:
        return True
    # Catch simple phrases like "looks good to me", "yeah that’s fine"
    return any(
        phrase in normalized
        for phrase in [
            "looks good",
            "sounds good",
            "all good",
            "that’s fine",
            "thats fine",
            "good to me",
            "happy with that",
        ]
    )


def chat_loop(*, model: str = "gpt-4o-mini", persist: bool = True) -> None:
    """Interactive CLI chatbot that switches into booking mode when asked."""

    _agent_print(
        "Hi! I’m your UniMelb library booking helper. Type 'exit' or press Ctrl+C to quit."
    )
    session: Optional[BookingSession] = None
    booking_mode = False
    just_entered_booking = False
    # Simple state machine to switch between small talk and booking.

    while True:
        try:
            prompt = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not prompt or prompt.lower() in {"exit", "quit"}:
            break

        # Detect booking intent and kick off a session
        if not booking_mode and _looks_like_booking_intent(prompt):
            booking_mode = True
            session = BookingSession(model=model)
            try:
                session.update_from_prompt(prompt)
            except Exception as exc:
                _agent_print(
                    "I had a bit of trouble reading that automatically, "
                    f"but we can sort it out together. (Error: {exc})"
                )
            missing_now = session.missing_fields() if session else []
            if session and not missing_now:
                session.awaiting_confirmation = True
                payload = session.payload()
                _agent_print(
                    "Nice, here’s what I’m thinking: "
                    + _format_booking_summary(payload)
                    + " Does that look right? If not, tell me what you'd like to change."
                )
                continue
            just_entered_booking = True
            _agent_print(
                "Great, let’s book a room. Tell me the library, date, "
                "start time, end time, how many people, and what the event is called."
            )
            continue

        # If we’re not in booking mode, just be a simple helper
        if not booking_mode:
            _agent_print(
                "If you want to book a library room, try something like "
                "'book Baillieu on 14/12, 2–4pm, 5 people, call it Test 6'."
            )
            continue

        # Booking mode
        assert session is not None

        # If we're waiting for confirmation and the user confirms, finalize.
        if session.awaiting_confirmation and _is_yes(prompt):
            payload = session.payload()
            target_path = _write_payload_to_file(payload) if persist else None
            if persist:
                try:
                    EXAMPLE_BOOKING_PATH.write_text(json.dumps(payload, indent=2))
                except Exception as exc:
                    _agent_print(f"Could not update example booking file: {exc}")
            if persist:
                try:
                    from app.browser import booking_flow

                    # Kick off the browser flow with the confirmed payload.
                    _agent_print("Starting browser booking flow to search for this slot...")
                    asyncio.run(
                        booking_flow.run_login_probe(
                            headless=_headless_flag(),
                            pause_before_close=not _headless_flag(),
                        )
                    )
                except Exception as exc:
                    _agent_print(f"Booking flow failed to launch: {exc}")
            booking_mode = False
            session = None
            continue

        try:
            allowed_fields: Optional[set[str]] = None
            if session.awaiting_confirmation:
                lowered = prompt.lower()
                allowed_fields = set()
                # Only nudge the fields the user actually mentioned.
                if any(word in lowered for word in ["event", "name", "title"]):
                    allowed_fields.add("event_name")
                if "library" in lowered:
                    allowed_fields.add("preferred_library")
                if "date" in lowered:
                    allowed_fields.add("date")
                if "start" in lowered or "time" in lowered:
                    allowed_fields.add("start_time")
                if "end" in lowered or "time" in lowered:
                    allowed_fields.add("end_time")
                if any(word in lowered for word in ["capacity", "people", "attendees"]):
                    allowed_fields.add("min_capacity")
                # If nothing matched, fall back to not changing anything to avoid overwriting.
                if not allowed_fields:
                    allowed_fields = set()

            session.update_from_prompt(prompt, allowed=allowed_fields)
        except Exception as exc:
            _agent_print(
                "I couldn’t quite map that to the booking details, "
                f"but keep going and I’ll adjust what I can. (Error: {exc})"
            )

        if just_entered_booking:
            just_entered_booking = False
            initial_missing = session.missing_fields()
            if initial_missing:
                _agent_print(
                    "To kick things off, send me one message with: library, date, "
                    "start time, end time (HH:MM), capacity, and event name."
                )
                continue

        missing = session.missing_fields()
        if missing:
            session.awaiting_confirmation = False
            missing_str = ", ".join(missing)
            _agent_print(
                f"Almost there — I still need: {missing_str}. "
                "Just send those details and I’ll plug them in."
            )
            continue

        if session.awaiting_confirmation:
            # We already applied the change; re-summarize.
            updated = session.payload()
            _agent_print(
                "Updated version: "
                + _format_booking_summary(updated)
                + " How does that look now? If you’re happy with it, just say "
                  "'yes' or anything similar; otherwise tell me what to tweak."
            )
            session.awaiting_confirmation = True
            continue

        # All fields present, ask for confirmation
        payload = session.payload()
        _agent_print(
            "Here’s what I’ve put together: "
            + _format_booking_summary(payload)
            + " Happy with that?"
              " If not, tell me what to change."
        )
        session.awaiting_confirmation = True


if __name__ == "__main__":
    chat_loop()


__all__ = ["booking_agent", "booking_agent_to_file", "chat_loop", "EXAMPLE_BOOKING_PATH"]
