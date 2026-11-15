"""Home Assistant integration for Spotify Soloist."""

from yarl import URL

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession,
)

from .client import SoloistClient
from .const import CONF_HOST, CONF_PORT

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SENSOR]

type SoloistConfigEntry = ConfigEntry[SoloistClient]


async def async_update_entry(
    hass: HomeAssistant,
    entry: SoloistConfigEntry,
) -> None:
    """Reload the integration when its configuration changes."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SoloistConfigEntry,
) -> None:
    """Set up Soloist from a configuration entry."""
    url = URL.build(
        scheme="ws",
        host=entry.data[CONF_HOST],
        port=entry.data[CONF_PORT],
    )

    client = SoloistClient(
        async_get_clientsession(hass),
        str(url),
    )

    entry.runtime_data = client
    await client.connect()

    try:
        await hass.config_entries.async_forward_entry_setups(
            entry,
            PLATFORMS,
        )
    except Exception:
        await client.disconnect()
        raise

    entry.async_on_unload(entry.add_update_listener(async_update_entry))


async def async_unload_entry(
    hass: HomeAssistant,
    entry: SoloistConfigEntry,
) -> None:
    """Unload the Soloist integration."""
    await hass.config_entries.async_unload_platforms_or_raise(
        entry,
        PLATFORMS,
    )
    await entry.runtime_data.disconnect()
