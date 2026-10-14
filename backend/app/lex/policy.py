"""Safety policy for Lex-derived data.

Lex intents, slots, and slot values are untrusted input: they originate from a
cloud service and, upstream, from whatever a user said. Everything is
validated against explicit allowlists here before it is surfaced or acted on.
Unknown intents collapse to ``FallbackIntent`` and unknown slots are dropped,
so a misconfigured or compromised bot can never smuggle arbitrary keys or
values into the application layer.
"""

from __future__ import annotations

from typing import Any

DEFAULT_INTENT = "FallbackIntent"

# Intents Synthia understands. Anything else is treated as a fallback.
ALLOWED_INTENTS: frozenset[str] = frozenset(
    {"DeviceControlIntent", "QueryStatusIntent", "FallbackIntent"}
)

# Slot names Synthia understands.
ALLOWED_SLOTS: frozenset[str] = frozenset({"Action", "Device", "Room", "Value"})

# Slot value vocabularies. Values not in these sets are kept as free text but
# flagged, because they may be colloquial device names or numbers.
_ALLOWED_ACTIONS = frozenset(
    {"turn_on", "turn_off", "set", "lock", "unlock", "increase", "decrease"}
)
_ALLOWED_DEVICES = frozenset(
    {"light", "fan", "ac", "heater", "lock", "tv", "speaker", "thermostat"}
)
_ALLOWED_ROOMS = frozenset(
    {"bedroom", "living room", "kitchen", "office", "garage", "bathroom"}
)

# A sanity bound so a malformed response cannot inject huge strings.
_MAX_SLOT_VALUE_LEN = 120


def normalize_intent(name: str | None) -> tuple[str, list[str]]:
    """Return an allowlisted intent name plus any warning."""
    candidate = (name or "").strip()
    if candidate in ALLOWED_INTENTS:
        return candidate, []
    return DEFAULT_INTENT, [
        f"Unrecognized intent {candidate!r} treated as {DEFAULT_INTENT}."
    ]


def sanitize_slots(raw: dict[str, Any] | None) -> tuple[dict[str, str], list[str]]:
    """Keep only allowlisted slot names with bounded string values."""
    slots: dict[str, str] = {}
    warnings: list[str] = []
    for key, value in (raw or {}).items():
        if key not in ALLOWED_SLOTS:
            warnings.append(f"Dropped unrecognized slot {key!r}.")
            continue
        text = str(value).strip()[:_MAX_SLOT_VALUE_LEN]
        if text:
            slots[key] = text
    return slots, warnings


def is_known_action(value: str) -> bool:
    return value.strip().lower().replace(" ", "_") in _ALLOWED_ACTIONS


def is_known_device(value: str) -> bool:
    return value.strip().lower() in _ALLOWED_DEVICES


def is_known_room(value: str) -> bool:
    return value.strip().lower() in _ALLOWED_ROOMS
