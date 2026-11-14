from typing import Any

from models import PlaybackState

EVENT_FIELDS = {
    "track_changed": "item",
    "playback_changed": "status",
    "position_sync": "position",
    "position_changed": "position",
    "volume_changed": "volume",
    "options_changed": "options",
    "context_changed": "context",
}


class SoloistState:
    def __init__(self) -> None:
        self.playback: dict[str, Any] = {}
        self.auth: dict[str, Any] = {}
        self.queue: dict[str, Any] = {}
        self.last_published: PlaybackState | None = None

    def apply(self, event: dict[str, Any]) -> PlaybackState | None:
        kind = event.get("type")

        if not isinstance(kind, str):
            return None

        if kind == "auth_state":
            self.auth = dict(event)
            return None

        if kind == "queue_changed":
            self.queue = {
                "previous": event.get("previous", []),
                "upcoming": event.get("upcoming", []),
            }
            return None

        if kind == "playback_state":
            self.playback = dict(event)

        elif kind in EVENT_FIELDS:
            field = EVENT_FIELDS[kind]

            if field not in event:
                return None

            self.playback[field] = event[field]

        else:
            return None

        if not self.playback.get("item"):
            return None

        state = PlaybackState.from_event(self.playback)

        if state == self.last_published:
            return None

        self.last_published = state
        return state
