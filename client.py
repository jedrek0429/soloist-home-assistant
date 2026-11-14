import asyncio
import json
import logging
from collections.abc import Callable
from contextlib import suppress
from typing import Any

from aiohttp import (
    ClientError,
    ClientSession,
    ClientWebSocketResponse,
    WSMsgType,
)

from state import SoloistState

_LOGGER = logging.getLogger(__name__)

StateListener = Callable[[], None]
EventListener = Callable[[dict[str, Any]], None]


class SoloistClient:
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

        self._listeners: set[StateListener] = set()
        self._event_listeners: set[EventListener] = set()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    @property
    def playback(self):
        return self.state.last_published

    def subscribe(
        self,
        callback: StateListener,
    ) -> Callable[[], None]:
        self._listeners.add(callback)
        return lambda: self._listeners.discard(callback)

    def subscribe_events(
        self,
        callback: EventListener,
    ) -> Callable[[], None]:
        self._event_listeners.add(callback)
        return lambda: self._event_listeners.discard(callback)

    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("State listener failed")

    def _notify_event(self, event: dict[str, Any]) -> None:
        for listener in tuple(self._event_listeners):
            try:
                listener(event)
            except Exception:
                _LOGGER.exception("Event listener failed")

    async def connect(self) -> None:
        if self._task is not None and not self._task.done():
            return

        self._task = asyncio.create_task(
            self._run(),
            name="soloist-websocket",
        )

    async def disconnect(self) -> None:
        if self._task is None:
            return

        task = self._task
        task.cancel()

        with suppress(asyncio.CancelledError):
            await task

        self._task = None

    async def wait_ready(self, timeout: float = 5.0) -> None:
        await asyncio.wait_for(
            self._ready.wait(),
            timeout=timeout,
        )

    async def get_state(self) -> None:
        if self._ws is None or self._ws.closed:
            raise ConnectionError("Soloist is not connected")

        await self._ws.send_json(
            {
                "type": "command",
                "command": "get_state",
            }
        )

    def _handle_event(self, event: dict[str, Any]) -> None:
        kind = event.get("type")

        updated = self.state.apply(event)

        self._notify_event(event)

        if (kind == "auth_state" and isinstance(event.get("logged_in"), bool)) or (
            kind == "playback_state" and "status" in event
        ):
            self._ready.set()

        if updated is not None or kind in (
            "auth_state",
            "queue_changed",
        ):
            self._notify()

    async def _run(self) -> None:
        retry = 1.0

        while True:
            try:
                _LOGGER.info("Connecting to %s", self.url)

                async with asyncio.timeout(5):
                    ws = await self._session.ws_connect(
                        self.url,
                        heartbeat=30,
                    )

                async with ws:
                    self._ws = ws
                    self._connected = True
                    self._notify()

                    await self.get_state()

                    retry = 1.0

                    async for message in ws:
                        if message.type == WSMsgType.TEXT:
                            try:
                                event = json.loads(message.data)
                            except json.JSONDecodeError:
                                _LOGGER.warning("Invalid JSON from Soloist")
                                continue

                            if not isinstance(event, dict):
                                continue

                            self._handle_event(event)

                        elif message.type == WSMsgType.ERROR:
                            raise ConnectionError(str(ws.exception()))

                    _LOGGER.warning("Soloist connection closed")

            except asyncio.CancelledError:
                raise

            except (
                ClientError,
                OSError,
                ConnectionError,
                asyncio.TimeoutError,
            ) as error:
                _LOGGER.warning(
                    "Soloist connection error: %s",
                    error,
                )

            except Exception:
                _LOGGER.exception("Unexpected Soloist client error")

            finally:
                self._ws = None
                self._connected = False
                self._ready.clear()

                # Never expose stale playback after disconnect.
                self.state = SoloistState()
                self._notify()

            _LOGGER.info(
                "Reconnecting in %.1f seconds",
                retry,
            )

            await asyncio.sleep(retry)
            retry = min(retry * 2, 30.0)
