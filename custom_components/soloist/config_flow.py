"""Configuration flow for Spotify Soloist."""

import asyncio
import json

from typing import Any

import probatio

from aiohttp import ClientError, WSMsgType
from yarl import URL

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import (
    async_get_clientsession,
)
from homeassistant.helpers.service_info.zeroconf import (
    ZeroconfServiceInfo,
)

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONNECTION_TIMEOUT,
    DEFAULT_PORT,
    DOMAIN,
)
from .discovery import async_get_soloist_info


class CannotConnect(Exception):
    """WebSocket connection failed."""


class InvalidResponse(Exception):
    """The WebSocket did not return a recognized Soloist event."""


async def validate_connection(
    hass: HomeAssistant,
    host: str,
    port: int,
) -> None:
    """Verify WebSocket connectivity and protocol identity."""

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
                            continue

                        if not isinstance(event, dict):
                            continue

                        kind = event.get("type")

                        if kind == "auth_state" and isinstance(
                            event.get("logged_in"),
                            bool,
                        ):
                            return

                        if kind == "playback_state" and isinstance(
                            event.get("status"),
                            str,
                        ):
                            return

                    elif message.type in (
                        WSMsgType.ERROR,
                        WSMsgType.CLOSE,
                        WSMsgType.CLOSED,
                    ):
                        break

    except (
        ClientError,
        OSError,
        TimeoutError,
    ) as error:
        raise CannotConnect from error

    raise InvalidResponse


class SoloistConfigFlow(
    ConfigFlow,
    domain=DOMAIN,
):
    """Configure a Spotify Soloist instance."""

    VERSION = 1

    def __init__(self) -> None:
        self._host = ""
        self._port = DEFAULT_PORT
        self._title = "Soloist"

    async def async_step_user(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Manually configure a Soloist endpoint."""

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
                        user_input.get(
                            CONF_PORT,
                            DEFAULT_PORT,
                        )
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

    async def async_step_zeroconf(
        self,
        discovery_info: ZeroconfServiceInfo,
    ) -> ConfigFlowResult:
        """Handle a Spotify Connect mDNS advertisement."""

        host = discovery_info.host
        service_port = discovery_info.port

        if service_port is None:
            return self.async_abort(reason="missing_service_port")

        info = await async_get_soloist_info(
            self.hass,
            host,
            service_port,
            discovery_info.properties,
        )

        if info is None:
            return self.async_abort(reason="not_soloist")

        device_id = info.get("deviceID")

        if not isinstance(device_id, str) or not device_id:
            return self.async_abort(reason="missing_device_id")

        self._host = host
        self._port = DEFAULT_PORT

        name = info.get("remoteName")

        self._title = (
            name.strip() if isinstance(name, str) and name.strip() else "Soloist"
        )

        # Avoid rediscovering a manually configured endpoint.
        for entry in self._async_current_entries():
            if entry.data.get(CONF_HOST) == self._host:
                return self.async_abort(reason="already_configured")

        await self.async_set_unique_id(device_id)

        self._abort_if_unique_id_configured(
            updates={CONF_HOST: self._host},
        )

        try:
            await validate_connection(
                self.hass,
                self._host,
                self._port,
            )

        except (CannotConnect, InvalidResponse):
            return await self.async_step_troubleshoot()

        return await self.async_step_confirm()

    async def async_step_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Ask for confirmation before adding a discovered device."""

        if user_input is None:
            return self.async_show_form(
                step_id="confirm",
                description_placeholders={
                    "device_name": self._title,
                    "host": self._host,
                    "port": str(self._port),
                },
            )

        try:
            await validate_connection(
                self.hass,
                self._host,
                self._port,
            )

        except (CannotConnect, InvalidResponse):
            return await self.async_step_troubleshoot()

        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=self._title,
            data={
                CONF_HOST: self._host,
                CONF_PORT: self._port,
            },
        )

    async def async_step_troubleshoot(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> ConfigFlowResult:
        """Help configure an inaccessible WebSocket."""

        errors: dict[str, str] = {}

        if user_input is not None:
            self._port = user_input[CONF_PORT]

            try:
                await validate_connection(
                    self.hass,
                    self._host,
                    self._port,
                )

            except CannotConnect:
                errors["base"] = "cannot_connect"

            except InvalidResponse:
                errors["base"] = "invalid_response"

            else:
                return await self.async_step_confirm()

        schema = probatio.Schema(
            {
                probatio.Required(
                    CONF_PORT,
                    default=self._port,
                ): probatio.All(
                    probatio.Coerce(int),
                    probatio.Range(min=1, max=65535),
                ),
            }
        )

        return self.async_show_form(
            step_id="troubleshoot",
            data_schema=schema,
            errors=errors,
            description_placeholders={
                "device_name": self._title,
                "host": self._host,
                "port": str(self._port),
            },
        )
