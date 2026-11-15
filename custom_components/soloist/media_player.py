"""Media player entity for Spotify Soloist."""

from typing import Any

from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
)

from . import SoloistConfigEntry
from .client import SoloistClient
from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoloistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Soloist media player."""

    async_add_entities(
        [
            SoloistMediaPlayer(entry),
        ]
    )


class SoloistMediaPlayer(MediaPlayerEntity):
    """Representation of a Spotify Soloist instance."""

    _attr_name = "Soloist"
    _attr_has_entity_name = False
    _attr_should_poll = False

    def __init__(self, entry: SoloistConfigEntry) -> None:
        self._client: SoloistClient = entry.runtime_data

        identifier = entry.unique_id or entry.entry_id

        self._attr_unique_id = f"{identifier}_player"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=entry.title,
            manufacturer="Soloist",
            model="Soloist",
        )

    async def async_added_to_hass(self) -> None:
        """Subscribe to Soloist updates."""

        await super().async_added_to_hass()

        self.async_on_remove(self._client.subscribe(self.async_write_ha_state))

    @property
    def available(self) -> bool:
        return self._client.connected and self._client.ready

    @property
    def state(self) -> MediaPlayerState:
        playback = self._client.playback

        if playback is None:
            return MediaPlayerState.IDLE

        return {
            "playing": MediaPlayerState.PLAYING,
            "paused": MediaPlayerState.PAUSED,
            "buffering": MediaPlayerState.BUFFERING,
            "stopped": MediaPlayerState.IDLE,
            "idle": MediaPlayerState.IDLE,
        }.get(
            playback.status,
            MediaPlayerState.IDLE,
        )

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        playback = self._client.playback

        if playback is None:
            return MediaPlayerEntityFeature(0)

        actions = playback.available_actions

        features = MediaPlayerEntityFeature(0)

        if "play" in actions:
            features |= (
                MediaPlayerEntityFeature.PLAY | MediaPlayerEntityFeature.PLAY_MEDIA
            )

        if "pause" in actions:
            features |= MediaPlayerEntityFeature.PAUSE

        if "skip_next" in actions:
            features |= MediaPlayerEntityFeature.NEXT_TRACK

        if "skip_prev" in actions:
            features |= MediaPlayerEntityFeature.PREVIOUS_TRACK

        if "seek" in actions:
            features |= MediaPlayerEntityFeature.SEEK

        if playback.volume is not None:
            features |= MediaPlayerEntityFeature.VOLUME_SET

        if playback.shuffle is not None:
            features |= MediaPlayerEntityFeature.SHUFFLE_SET

        if playback.repeat is not None:
            features |= MediaPlayerEntityFeature.REPEAT_SET

        return features

    @property
    def media_title(self) -> str | None:
        state = self._client.playback
        return state.title if state else None

    @property
    def media_artist(self) -> str | None:
        state = self._client.playback

        if not state or not state.artists:
            return None

        return ", ".join(state.artists)

    @property
    def media_album_name(self) -> str | None:
        state = self._client.playback
        return state.album if state else None

    @property
    def media_image_url(self) -> str | None:
        state = self._client.playback
        return state.cover_url if state else None

    @property
    def media_image_remotely_accessible(self) -> bool:
        return True

    @property
    def media_content_id(self) -> str | None:
        state = self._client.playback
        return state.track_uri if state else None

    @property
    def media_content_type(self) -> MediaType | None:
        uri = self.media_content_id

        if not uri:
            return None

        if uri.startswith("spotify:episode:"):
            return MediaType.EPISODE

        return MediaType.MUSIC

    @property
    def media_duration(self) -> float | None:
        state = self._client.playback

        if state is None:
            return None

        return state.duration_ms / 1000

    @property
    def media_position(self) -> float | None:
        state = self._client.playback

        if state is None:
            return None

        return state.position_ms / 1000

    @property
    def media_position_updated_at(self):
        return self._client.position_updated_at

    @property
    def volume_level(self) -> float | None:
        state = self._client.playback

        if state is None or state.volume is None:
            return None

        return state.volume / 100

    @property
    def shuffle(self) -> bool | None:
        state = self._client.playback
        return state.shuffle if state else None

    @property
    def repeat(self) -> str | None:
        state = self._client.playback

        if state is None or state.repeat is None:
            return None

        return {
            "off": RepeatMode.OFF,
            "context": RepeatMode.ALL,
            "track": RepeatMode.ONE,
        }.get(
            state.repeat,
            RepeatMode.OFF,
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        state = self._client.playback

        if state is None:
            return {}

        queue = self._client.state.queue

        return {
            "spotify_uri": state.track_uri,
            "album_uri": state.album_uri,
            "is_active": self._client.state.auth.get("is_active"),
            "queue_upcoming_count": len(queue.get("upcoming", [])),
            "queue_previous_count": len(queue.get("previous", [])),
        }

    async def _send(
        self,
        command: str,
        **fields: Any,
    ) -> None:
        try:
            await self._client.send_command(
                command,
                **fields,
            )
        except ConnectionError as error:
            raise HomeAssistantError("Soloist is disconnected") from error

    async def async_media_play(self) -> None:
        await self._send("play")

    async def async_media_pause(self) -> None:
        await self._send("pause")

    async def async_media_next_track(self) -> None:
        await self._send("skip_next")

    async def async_media_previous_track(self) -> None:
        await self._send("skip_prev")

    async def async_media_seek(
        self,
        position: float,
    ) -> None:
        await self._send(
            "seek",
            position_ms=max(0, round(position * 1000)),
        )

    async def async_set_volume_level(
        self,
        volume: float,
    ) -> None:
        await self._send(
            "set_volume",
            volume=round(max(0.0, min(1.0, volume)) * 100),
        )

    async def async_set_shuffle(
        self,
        shuffle: bool,
    ) -> None:
        await self._send(
            "set_shuffle",
            enabled=shuffle,
        )

    async def async_set_repeat(
        self,
        repeat: str,
    ) -> None:
        if repeat == RepeatMode.OFF:
            await self._send(
                "set_repeat_track",
                enabled=False,
            )
            await self._send(
                "set_repeat_context",
                enabled=False,
            )

        elif repeat == RepeatMode.ALL:
            await self._send(
                "set_repeat_track",
                enabled=False,
            )
            await self._send(
                "set_repeat_context",
                enabled=True,
            )

        elif repeat == RepeatMode.ONE:
            await self._send(
                "set_repeat_context",
                enabled=False,
            )
            await self._send(
                "set_repeat_track",
                enabled=True,
            )

        else:
            raise HomeAssistantError(f"Unsupported repeat mode: {repeat}")

    async def async_play_media(
        self,
        media_type: str,
        media_id: str,
        **kwargs: Any,
    ) -> None:
        if not media_id.startswith("spotify:"):
            raise HomeAssistantError("Soloist requires a Spotify URI")

        await self._send(
            "play",
            uri=media_id,
        )
