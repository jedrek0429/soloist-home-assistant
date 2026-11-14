from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PlaybackState:
    status: str
    track_uri: str | None
    title: str | None
    artists: tuple[str, ...]
    album: str | None
    album_uri: str | None
    cover_url: str | None
    duration_ms: int
    position_ms: int
    volume: int | None
    shuffle: bool | None
    repeat: str | None
    available_actions: frozenset[str]

    @classmethod
    def from_event(cls, event: dict[str, Any]) -> "PlaybackState":
        item = event.get("item") or {}
        decorations = item.get("decorations") or {}

        album = (decorations.get("parent") or {}).get("entity") or {}

        creators = decorations.get("creators") or []
        artists = tuple(
            name
            for creator in creators
            if (
                name := (
                    ((creator.get("entity") or {}).get("decorations") or {}).get(
                        "identity"
                    )
                    or {}
                ).get("name")
            )
        )

        covers = (decorations.get("visual_identity") or {}).get("cover") or []
        cover = next(
            (c.get("url") for c in covers if c.get("size") == "xlarge"),
            next((c.get("url") for c in covers if c.get("url")), None),
        )

        position = event.get("position") or {}
        options = event.get("options") or {}

        return cls(
            status=event.get("status", "unknown"),
            track_uri=item.get("uri"),
            title=(decorations.get("identity") or {}).get("name"),
            artists=artists,
            album=((album.get("decorations") or {}).get("identity") or {}).get("name"),
            album_uri=album.get("uri"),
            cover_url=cover,
            duration_ms=((decorations.get("playback") or {}).get("duration_ms") or 0),
            position_ms=position.get("position_ms") or 0,
            volume=event.get("volume"),
            shuffle=options.get("shuffle"),
            repeat=options.get("repeat"),
            available_actions=frozenset((event.get("available_actions") or {}).keys()),
        )
