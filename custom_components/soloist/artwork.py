"""Secure asynchronous Spotify artwork retrieval and colour extraction."""

from __future__ import annotations

import asyncio
import logging
from io import BytesIO
from urllib.parse import urlsplit

from aiohttp import ClientError, ClientSession
from PIL import Image, UnidentifiedImageError

from homeassistant.core import HomeAssistant

from .artwork_colour import dominant_colour_from_pixels

_LOGGER = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_PIXELS = 16_000_000
IMAGE_SIZE = (64, 64)


def _is_spotify_artwork(url: str) -> bool:
    """Allow known HTTPS Spotify artwork URLs."""

    try:
        parsed = urlsplit(url)

        return (
            parsed.scheme == "https"
            and parsed.hostname == "i.scdn.co"
            and parsed.port in (None, 443)
            and parsed.username is None
            and parsed.password is None
            and parsed.path.startswith("/image/")
            and len(parsed.path) <= 256
            and not parsed.query
            and not parsed.fragment
        )

    except ValueError:
        return False


def _extract_image_colour(contents: bytes) -> str | None:
    """Decode and downsample artwork outside the HA event loop."""

    with Image.open(BytesIO(contents)) as original:
        if original.width * original.height > MAX_IMAGE_PIXELS:
            raise ValueError("Spotify artwork exceeds decoded pixel limit")

        image = original.convert("RGBA").resize(
            IMAGE_SIZE,
            Image.Resampling.BILINEAR,
        )

        return dominant_colour_from_pixels(
            image.tobytes(),
            *IMAGE_SIZE,
        )


async def async_artwork_colour(
    hass: HomeAssistant,
    session: ClientSession,
    url: str,
) -> str | None:
    """Return a hex colour for Spotify artwork."""

    if not _is_spotify_artwork(url):
        _LOGGER.debug("Ignoring non-Spotify artwork URL")
        return None

    try:
        async with asyncio.timeout(10):
            async with session.get(
                url,
                allow_redirects=False,
            ) as response:

                if response.status != 200:
                    _LOGGER.debug(
                        "Spotify artwork returned HTTP %s",
                        response.status,
                    )
                    return None

                if not response.content_type.startswith("image/"):
                    _LOGGER.debug("Spotify artwork has unexpected content type")
                    return None

                if (
                    response.content_length is not None
                    and response.content_length > MAX_IMAGE_BYTES
                ):
                    _LOGGER.debug("Spotify artwork exceeds download limit")
                    return None

                # Read until EOF, not just the first available buffer.
                chunks = bytearray()

                async for chunk in response.content.iter_chunked(65536):
                    if len(chunks) + len(chunk) > MAX_IMAGE_BYTES:
                        _LOGGER.debug("Spotify artwork exceeds download limit")
                        return None

                    chunks.extend(chunk)

        if not chunks:
            return None

        return await hass.async_add_executor_job(
            _extract_image_colour,
            bytes(chunks),
        )

    except asyncio.CancelledError:
        raise

    except (
        ClientError,
        TimeoutError,
        OSError,
        ValueError,
        UnidentifiedImageError,
    ) as error:
        _LOGGER.warning(
            "Could not extract Soloist artwork colour: %s",
            error,
        )
        return None
