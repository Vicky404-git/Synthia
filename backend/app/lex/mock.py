"""Simulated command provider.

Used when AWS Lex is disabled or not configured, so the voice-command flow
remains demonstrable and testable offline. It performs a tiny rule-based
intent match over the transcript and a *simulated* device state. Every result
is labelled ``simulated=True`` and the fulfilment text says so explicitly.

This is deliberately not a reimplementation of AWS Lex or of a Lambda
fulfilment function: it is demo scaffolding behind the same replaceable
contract.
"""

from __future__ import annotations

import re
import time

from ..config import Settings
from ..schemas import ProviderStatus
from .base import LexHealth, LexIntentResult, LexProvider
from .policy import (
    DEFAULT_INTENT,
    normalize_intent,
    sanitize_slots,
)

_CONTROL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("turn on", "turn_on"),
    ("switch on", "turn_on"),
    ("power on", "turn_on"),
    ("enable", "turn_on"),
    ("turn off", "turn_off"),
    ("switch off", "turn_off"),
    ("power off", "turn_off"),
    ("disable", "turn_off"),
    ("set ", "set"),
    ("lock", "lock"),
    ("unlock", "unlock"),
)

_DEVICE_WORDS = (
    "light",
    "lamp",
    "fan",
    "ac",
    "air conditioner",
    "heater",
    "thermostat",
    "lock",
    "tv",
    "television",
    "speaker",
)

_ROOM_WORDS = (
    "bedroom",
    "living room",
    "kitchen",
    "office",
    "garage",
    "bathroom",
)

_QUERY_WORDS = ("status", "state", "is the", "are the", "what is", "what's")


def _canonical_device(text: str) -> str | None:
    for word in _DEVICE_WORDS:
        if word in text:
            if word in {"lamp"}:
                return "light"
            if word in {"air conditioner"}:
                return "ac"
            if word in {"television"}:
                return "tv"
            return word
    return None


def _canonical_room(text: str) -> str | None:
    return next((room for room in _ROOM_WORDS if room in text), None)


class MockLexProvider(LexProvider):
    id = "mock-lex"
    simulated = True

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Simulated device state, keyed by "room:device". Never real hardware.
        self._state: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return True

    def health(self) -> LexHealth:
        return LexHealth(
            status=ProviderStatus.demo,
            detail=(
                "Simulated command provider. Intents and device state are "
                "local demo data, not a live AWS Lex response."
            ),
            provider=self.id,
            simulated=True,
            setup_hint=(
                "Set LEX_ENABLED=true with LEX_BOT_ID and LEX_BOT_ALIAS_ID to "
                "use a real AWS Lex V2 bot."
            ),
        )

    def reset(self) -> None:
        self._state.clear()

    def recognize_text(self, text: str, *, session_id: str) -> LexIntentResult:
        started = time.perf_counter()
        lowered = text.lower()

        slots: dict[str, str] = {}
        action = next(
            (value for needle, value in _CONTROL_PATTERNS if needle in lowered),
            None,
        )
        device = _canonical_device(lowered)
        room = _canonical_room(lowered)

        number = re.search(r"\b(\d{1,3})\b", lowered)
        if number:
            slots["Value"] = number.group(1)
        if action:
            slots["Action"] = action
        if device:
            slots["Device"] = device
        if room:
            slots["Room"] = room

        if action:
            intent = "DeviceControlIntent"
        elif any(word in lowered for word in _QUERY_WORDS):
            intent = "QueryStatusIntent"
        else:
            intent = DEFAULT_INTENT

        intent, warnings = normalize_intent(intent)
        clean_slots, slot_warnings = sanitize_slots(slots)
        warnings.extend(slot_warnings)

        message = self._fulfil(intent, clean_slots, room, device)
        return LexIntentResult(
            transcript=text,
            intent=intent,
            slots=clean_slots,
            fulfillment_message=message,
            provider=self.id,
            simulated=True,
            session_id=session_id,
            latency_ms=int((time.perf_counter() - started) * 1000),
            warnings=warnings,
        )

    # -- simulated fulfilment --------------------------------------------

    def _fulfil(
        self,
        intent: str,
        slots: dict[str, str],
        room: str | None,
        device: str | None,
    ) -> str:
        if intent == "FallbackIntent":
            return (
                "DEMO — I did not recognize a command. Try 'turn on the "
                "bedroom fan' or 'set the AC to 22'."
            )

        target = self._target(room, device)
        if intent == "QueryStatusIntent":
            state = self._state.get(target, "off")
            return f"DEMO — {target} is currently {state} (simulated state)."

        action = slots.get("Action", "turn_on")
        value = slots.get("Value")
        if action == "turn_on" or action == "set":
            self._state[target] = value or "on"
        elif action in {"turn_off", "disable"}:
            self._state[target] = "off"
        else:
            self._state[target] = action

        state = self._state[target]
        return (
            f"DEMO — {target} set to {state}. This is a simulated command; "
            "no real device or infrastructure was changed."
        )

    @staticmethod
    def _target(room: str | None, device: str | None) -> str:
        room_part = room or "room"
        device_part = device or "device"
        return f"{room_part} {device_part}"
