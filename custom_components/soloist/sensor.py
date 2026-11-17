"""Push-based album artwork colour sensor for Spotify Soloist."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import suppress

from aiohttp import ClientSession

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import SoloistConfigEntry
from .artwork import async_artwork_colour
from .artwork_colour import rgb_from_hex
from .client import SoloistClient
from .const import DOMAIN

CACHE_SIZE = 64


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoloistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register the artwork colour sensor."""
    display = SoloistArtworkColourSensor(entry, async_get_clientsession(hass))
    async_add_entities([
        display,
        SoloistDerivedColourSensor(display, "Average", "average"),
        SoloistDerivedColourSensor(display, "Lighting", "lighting"),
    ])


class SoloistArtworkColourSensor(SensorEntity):
    """Expose an accent colour from the currently playing album cover."""

    _attr_name = "Album colour"
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:palette"

    def __init__(
        self,
        entry: SoloistConfigEntry,
        session: ClientSession,
    ) -> None:
        self._entry = entry
        self._client: SoloistClient = entry.runtime_data
        self._session = session
        identifier = entry.unique_id or entry.entry_id
        self._attr_unique_id = f"{identifier}_album_colour"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=entry.title,
            manufacturer="Soloist",
            model="Soloist",
        )

        self._artwork_url: str | None = None
        self._colour: str | None = None
        self._cache: OrderedDict[str, tuple[str, str, str]] = OrderedDict()
        self._colours: tuple[str, str, str] | None = None
        self._derived: list[SoloistDerivedColourSensor] = []
        self._task: asyncio.Task[None] | None = None
        self._was_available = False

    @property
    def available(self) -> bool:
        """Report unavailable when the Soloist WebSocket is offline."""
        return self._client.connected and self._client.ready

    @property
    def native_value(self) -> str | None:
        return self._colour

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        if not self._colour:
            return {}
        return {
            "rgb_color": list(rgb_from_hex(self._colour)),
            "artwork_url": self._artwork_url,
        }

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._client.subscribe(self._on_client_update))
        self._on_client_update()

    async def async_will_remove_from_hass(self) -> None:
        """Cancel in-flight work when the entity is unloaded."""
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await super().async_will_remove_from_hass()

    @callback
    def _on_client_update(self) -> None:
        """Ignore position syncs; react to artwork and availability changes."""
        available = self.available
        availability_changed = available != self._was_available
        self._was_available = available

        playback = self._client.playback if available else None
        url = playback.cover_url if playback else None

        if url == self._artwork_url:
            if availability_changed:
                self.async_write_ha_state()
            return

        self._artwork_url = url

        if self._task is not None:
            self._task.cancel()
            self._task = None

        self._colour = None
        self._colours = None
        if url is not None and url in self._cache:
            self._cache.move_to_end(url)
            self._colours = self._cache[url]
            self._colour = self._colours[1]

        self._publish()

        if url is not None and self._colour is None:
            self._task = self._entry.async_create_task(
                self.hass,
                self._async_extract(url),
                name="soloist-artwork-colour",
                eager_start=False,
            )

    async def _async_extract(self, url: str) -> None:
        colour = await async_artwork_colour(self.hass, self._session, url)
        if url != self._artwork_url or not self.available or colour is None:
            return

        self._cache[url] = colour
        self._cache.move_to_end(url)
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)

        self._colours = colour
        self._colour = colour[1]
        self._publish()


    @callback
    def _publish(self) -> None:
        self.async_write_ha_state()
        for entity in self._derived:
            if entity.hass is not None:
                entity.async_write_ha_state()


class SoloistDerivedColourSensor(SensorEntity):
    """A colour mode backed by the same artwork fetch and cache."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:palette"

    def __init__(self, source: SoloistArtworkColourSensor, name: str, mode: str) -> None:
        self._source = source
        self._index = {"average": 0, "lighting": 2}[mode]
        self._attr_name = f"Album {name.lower()} colour"
        self._attr_unique_id = f"{source.unique_id}_{mode}"
        self._attr_device_info = source.device_info
        source._derived.append(self)

    @property
    def available(self) -> bool:
        return self._source.available

    @property
    def native_value(self) -> str | None:
        colours = self._source._colours
        return colours[self._index] if colours else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        colour = self.native_value
        if not colour:
            return {}
        return {
            "rgb_color": list(rgb_from_hex(colour)),
            "artwork_url": self._source._artwork_url,
        }
