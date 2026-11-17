"""Push-based artwork colour sensors for Spotify Soloist."""

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
MODES = ("Average", "Display", "Lighting")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoloistConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Register the three colour sensors backed by one artwork subscription."""
    session = async_get_clientsession(hass)
    sensors = [
        SoloistArtworkColourSensor(entry, session, index)
        for index in range(len(MODES))
    ]
    for sensor in sensors:
        sensor._siblings = sensors
    async_add_entities(sensors)


class SoloistArtworkColourSensor(SensorEntity):
    """Expose one of three colours computed from a single cover."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_icon = "mdi:palette"

    def __init__(self, entry: SoloistConfigEntry, session: ClientSession, index: int) -> None:
        self._entry = entry
        self._client: SoloistClient = entry.runtime_data
        self._session = session
        self._index = index
        self._siblings: list[SoloistArtworkColourSensor] = []
        identifier = entry.unique_id or entry.entry_id
        self._attr_name = f"Album {MODES[index].lower()} colour"
        self._attr_unique_id = f"{identifier}_album_{MODES[index].lower()}_colour"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, identifier)},
            name=entry.title,
            manufacturer="Soloist",
            model="Soloist",
        )
        self._artwork_url: str | None = None
        self._colours: tuple[str, str, str] | None = None
        self._cache: OrderedDict[str, tuple[str, str, str]] = OrderedDict()
        self._task: asyncio.Task[None] | None = None
        self._was_available = False

    @property
    def available(self) -> bool:
        return self._client.connected and self._client.ready

    @property
    def native_value(self) -> str | None:
        colours = self._siblings[0]._colours
        return colours[self._index] if colours else None

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        colour = self.native_value
        return {
            "rgb_color": list(rgb_from_hex(colour)),
            "artwork_url": self._siblings[0]._artwork_url,
        } if colour else {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if self._index == 0:
            self.async_on_remove(self._client.subscribe(self._on_client_update))
            self._on_client_update()

    async def async_will_remove_from_hass(self) -> None:
        if self._index == 0 and self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        await super().async_will_remove_from_hass()

    @callback
    def _publish(self) -> None:
        for sensor in self._siblings:
            if sensor.hass is not None:
                sensor.async_write_ha_state()

    @callback
    def _on_client_update(self) -> None:
        available = self.available
        availability_changed = available != self._was_available
        self._was_available = available
        playback = self._client.playback if available else None
        url = playback.cover_url if playback else None
        if url == self._artwork_url:
            if availability_changed:
                self._publish()
            return

        self._artwork_url = url
        if self._task is not None:
            self._task.cancel()
            self._task = None

        self._colours = None
        if url is not None and url in self._cache:
            self._cache.move_to_end(url)
            self._colours = self._cache[url]
        self._publish()

        if url is not None and self._colours is None:
            self._task = self._entry.async_create_task(
                self.hass, self._async_extract(url),
                name="soloist-artwork-colour", eager_start=False,
            )

    async def _async_extract(self, url: str) -> None:
        colours = await async_artwork_colour(self.hass, self._session, url)
        if url != self._artwork_url or not self.available or colours is None:
            return
        self._cache[url] = colours
        self._cache.move_to_end(url)
        if len(self._cache) > CACHE_SIZE:
            self._cache.popitem(last=False)
        self._colours = colours
        self._publish()
