import asyncio
import logging
import sys

from aiohttp import ClientSession

from client import SoloistClient


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )

    url = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:9090"

    async with ClientSession() as session:
        client = SoloistClient(session, url)

        last_summary = None
        was_connected = False

        def on_update() -> None:
            nonlocal last_summary, was_connected

            if client.connected != was_connected:
                was_connected = client.connected

                if client.connected:
                    print("Connected to Soloist")
                else:
                    print("Disconnected from Soloist")
                    last_summary = None

            state = client.playback

            if state is None:
                return

            summary = (
                state.status,
                state.track_uri,
                state.volume,
                state.shuffle,
                state.repeat,
            )

            if summary == last_summary:
                return

            last_summary = summary

            print(
                f"{state.status}: "
                f"{state.title} — {', '.join(state.artists)} "
                f"[volume={state.volume}, "
                f"shuffle={state.shuffle}, "
                f"repeat={state.repeat}]"
            )

        client.subscribe(on_update)

        await client.connect()

        try:
            # Keep the probe running until interrupted.
            await asyncio.Event().wait()
        finally:
            await client.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
