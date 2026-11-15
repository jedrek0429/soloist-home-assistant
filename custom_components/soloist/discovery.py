"""Spotify Connect Zeroconf identification."""

import asyncio
import logging

from typing import Any, Mapping

from aiohttp import ClientError
from yarl import URL

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession,
)

_LOGGER = logging.getLogger(__name__)


def get_cpath(properties: Mapping[str, Any]) -> str:
    """Extract the HTTP path from a Spotify Connect advertisement."""

    for key, value in properties.items():
        if key.lower() != "cpath":
            continue

        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="replace")

        if isinstance(value, str):
            if value.startswith("/") and not value.startswith("//"):
                return value

    return "/zc"


async def async_get_soloist_info(
    hass: HomeAssistant,
    host: str,
    port: int,
    properties: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Identify Soloist using Spotify Connect getInfo."""

    path = get_cpath(properties)

    url = URL.build(
        scheme="http",
        host=host,
        port=port,
        path=path,
    ).with_query(action="getInfo")

    session = async_get_clientsession(hass)

    try:
        async with asyncio.timeout(5):
            async with session.get(url) as response:
                response.raise_for_status()
                data = await response.json(content_type=None)

    except (ClientError, OSError, TimeoutError, ValueError):
        _LOGGER.debug(
            "Could not query Spotify Connect getInfo at %s",
            host,
        )
        return None

    if not isinstance(data, dict):
        return None

    if (
        data.get("brandDisplayName") != "Soloist"
        or data.get("modelDisplayName") != "Soloist"
    ):
        return None

    return data
