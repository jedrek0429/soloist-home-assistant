"""Configuration flow for Soloist."""

import asyncio
import json
from typing import Any

from aiohttp import ClientError, WSMsgType
from yarl import URL
import probatio

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONNECTION_TIMEOUT,
    DEFAULT_PORT,
    DOMAIN,
)


class CannotConnect(Exception):
    """Cannot connect to Soloist."""


class InvalidResponse(Exception):
    """The WebSocket did not respond as Soloist."""


async def validate_connection(
    hass,
    host: str,
    port: int,
) -> None:
    """Verify that a Soloist WebSocket is accessible."""

    url = URL.build(
        scheme="ws",
        host=host,
        port=port,
    )

    session = async_get_clientsession(hass)

    try:
        async with asyncio.timeout(CONNECTION_TIMEOUT):
            async with session.ws_connect(url) as ws:
                await ws.send_json(
                    {
                        "type": "command",
                        "command": "get_state",
                    }
                )

                async for message in ws:
                    if message.type == WSMsgType.TEXT:
                        try:
                            event = json.loads(message.data)
                        except json.JSONDecodeError:
                            raise InvalidResponse from None

                        if not isinstance(event, dict):
                            continue

                        kind = event.get("type")

                        if kind == "auth_state" and isinstance(
                            event.get("logged_in"), bool
                        ):
                            return

                        if kind == "playback_state" and isinstance(
                            event.get("status"), str
                        ):
                            return

                    elif message.type in (
                        WSMsgType.CLOSE,
                        WSMsgType.CLOSED,
                        WSMsgType.ERROR,
                    ):
                        break

    except (TimeoutError, ClientError, OSError) as err:
        raise CannotConnect from err

    raise InvalidResponse


class SoloistConfigFlow(
    config_entries.ConfigFlow,
    domain=DOMAIN,
):
    """Handle configuration of Soloist."""

    VERSION = 1

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Handle manual setup."""

        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            port = user_input[CONF_PORT]

            if not host:
                errors[CONF_HOST] = "invalid_host"
            else:
                self._async_abort_entries_match(
                    {
                        CONF_HOST: host,
                        CONF_PORT: port,
                    }
                )

                try:
                    await validate_connection(
                        self.hass,
                        host,
                        port,
                    )

                except CannotConnect:
                    errors["base"] = "cannot_connect"

                except InvalidResponse:
                    errors["base"] = "invalid_response"

                else:
                    return self.async_create_entry(
                        title=f"Soloist ({host})",
                        data={
                            CONF_HOST: host,
                            CONF_PORT: port,
                        },
                    )

        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_HOST,
                    default=(user_input.get(CONF_HOST, "") if user_input else ""),
                ): str,
                probatio.Required(
                    CONF_PORT,
                    default=(
                        user_input.get(CONF_PORT, DEFAULT_PORT)
                        if user_input
                        else DEFAULT_PORT
                    ),
                ): probatio.All(
                    probatio.Coerce(int),
                    probatio.Range(min=1, max=65535),
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )
