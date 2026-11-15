"""Asynchronous WebSocket client for Spotify Soloist."""

import asyncio
import json
import logging

from collections.abc import Callable
from contextlib import suppress
from datetime import datetime, timezone
from typing import Any

from aiohttp import (
    ClientError,
    ClientSession,
    ClientWebSocketResponse,
    WSMsgType,
)

from .models import PlaybackState
from .state import SoloistState

_LOGGER = logging.getLogger(__name__)

Listener = Callable[[], None]


class SoloistClient:
    """Maintain a persistent connection to Soloist."""

    def __init__(
        self,
        session: ClientSession,
        url: str,
    ) -> None:
        self._session = session
        self.url = url

        self.state = SoloistState()

        self._ws: ClientWebSocketResponse | None = None
        self._task: asyncio.Task[None] | None = None

        self._connected = False
        self._ready = asyncio.Event()

        self._listeners: set[Listener] = set()

        self.position_updated_at: datetime | None = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    @property
    def playback(self) -> PlaybackState | None:
        return self.state.last_published

    def subscribe(
        self,
        callback: Listener,
    ) -> Callable[[], None]:
        """Subscribe to changes, returning an unsubscribe callback."""

        self._listeners.add(callback)

        return lambda: self._listeners.discard(callback)

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("Soloist listener failed")

    async def connect(self) -> None:
        """Start the background connection task."""

        if self._task is not None and not self._task.done():
            return

        self._task = asyncio.create_task(
            self._run(),
            name="soloist-websocket",
        )

    async def disconnect(self) -> None:
        """Stop the background task and close the socket."""

        if self._task is None:
            return

        task = self._task
        task.cancel()

        with suppress(asyncio.CancelledError):
            await task

        self._task = None

    async def wait_ready(
        self,
        timeout: float = 5.0,
    ) -> None:
        """Wait for a recognized Soloist state event."""

        await asyncio.wait_for(
            self._ready.wait(),
            timeout,
        )

    async def send_command(
        self,
        command: str,
        **fields: Any,
    ) -> None:
        """Send a command over the current WebSocket."""

        ws = self._ws

        if ws is None or ws.closed:
            raise ConnectionError("Soloist is disconnected")

        await ws.send_json(
            {
                "type": "command",
                "command": command,
                **fields,
            }
        )

    async def get_state(self) -> None:
        await self.send_command("get_state")

    async def get_queue(self, limit: int = 10) -> None:
        await self.send_command(
            "get_queue",
            limit=limit,
        )

    def _handle_event(self, event: dict[str, Any]) -> None:
        """Process a received Soloist event."""

        kind = event.get("type")

        if kind == "error":
            _LOGGER.warning(
                "Soloist API error: %s",
                event.get("message"),
            )
            return

        if kind == "device_changed":
            for key in ("is_active", "device_name"):
                if key in event:
                    self.state.auth[key] = event[key]

            self._notify()
            return

        if kind not in {
            "auth_state",
            "playback_state",
            "track_changed",
            "playback_changed",
            "position_sync",
            "position_changed",
            "volume_changed",
            "options_changed",
            "context_changed",
            "queue_changed",
        }:
            return

        self.state.apply(event)

        if kind == "auth_state":
            if isinstance(event.get("logged_in"), bool):
                self._ready.set()

        if kind == "playback_state":
            if isinstance(event.get("status"), str):
                self._ready.set()

        if kind in {
            "playback_state",
            "position_sync",
            "position_changed",
        }:
            if isinstance(
                self.state.playback.get("position"),
                dict,
            ):
                self.position_updated_at = datetime.now(timezone.utc)

        self._notify()

    async def _run(self) -> None:
        """Connect, receive events and reconnect on failure."""

        retry = 1.0

        while True:
            try:
                _LOGGER.info(
                    "Connecting to Soloist at %s",
                    self.url,
                )

                async with asyncio.timeout(5):
                    ws = await self._session.ws_connect(
                        self.url,
                        heartbeat=30,
                    )

                async with ws:
                    self._ws = ws
                    self._connected = True
                    self._ready.clear()

                    self._notify()

                    await self.get_state()

                    retry = 1.0

                    async for message in ws:
                        if message.type == WSMsgType.TEXT:
                            try:
                                event = json.loads(message.data)
                            except json.JSONDecodeError:
                                _LOGGER.warning("Invalid Soloist JSON")
                                continue

                            if isinstance(event, dict):
                                self._handle_event(event)

                        elif message.type == WSMsgType.ERROR:
                            raise ConnectionError(str(ws.exception()))

            except asyncio.CancelledError:
                raise

            except (
                ClientError,
                OSError,
                ConnectionError,
                TimeoutError,
            ) as error:
                _LOGGER.warning(
                    "Soloist connection failed: %s",
                    error,
                )

            except Exception:
                _LOGGER.exception("Unexpected Soloist client error")

            finally:
                self._ws = None
                self._connected = False
                self._ready.clear()

                self.state = SoloistState()
                self.position_updated_at = None

                self._notify()

            _LOGGER.info(
                "Reconnecting to Soloist in %.1f seconds",
                retry,
            )

            await asyncio.sleep(retry)
            retry = min(retry * 2, 30.0)
