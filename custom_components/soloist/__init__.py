"""Home Assistant integration for Soloist."""

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Set up a Soloist configuration entry.

    The persistent WebSocket client will be added
    in a later implementation stage.
    """


async def async_unload_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> None:
    """Unload a Soloist configuration entry."""
