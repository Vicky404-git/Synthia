"""Bounded in-memory transcription event store.

Server-side history is optional: the frontend keeps the authoritative V1
history in localStorage. This store exists so the documented transcription
endpoints work and so the demo can show server-side recording. It is
deliberately ephemeral (no filesystem state) and bounded.
"""

from __future__ import annotations

import threading
import uuid
from collections import OrderedDict

from .schemas import TranscriptionEvent, TranscriptionEventCreate


class TranscriptionStore:
    def __init__(self, max_events: int = 500) -> None:
        self._max = max_events
        self._events: OrderedDict[str, TranscriptionEvent] = OrderedDict()
        self._lock = threading.Lock()

    def create(self, payload: TranscriptionEventCreate) -> TranscriptionEvent:
        event = TranscriptionEvent(
            event_id=uuid.uuid4().hex,
            **payload.model_dump(),
        )
        with self._lock:
            self._events[event.event_id] = event
            while len(self._events) > self._max:
                self._events.popitem(last=False)
        return event

    def list(self) -> list[TranscriptionEvent]:
        with self._lock:
            return list(reversed(self._events.values()))

    def get(self, event_id: str) -> TranscriptionEvent | None:
        with self._lock:
            return self._events.get(event_id)

    def clear(self) -> int:
        with self._lock:
            count = len(self._events)
            self._events.clear()
            return count


_store: TranscriptionStore | None = None


def get_transcription_store() -> TranscriptionStore:
    global _store
    if _store is None:
        _store = TranscriptionStore()
    return _store


def reset_transcription_store() -> None:
    global _store
    _store = None
