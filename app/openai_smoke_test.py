import asyncio
import json

import websockets

from app.config import settings


REALTIME_MODEL = "gpt-realtime-2"
OPENAI_REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"


async def connect_to_openai():
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "OpenAI-Safety-Identifier": "athena-patient-voice-bot",
    }

    try:
        return await websockets.connect(
            OPENAI_REALTIME_URL,
            additional_headers=headers,
            ping_interval=20,
            ping_timeout=20,
        )
    except TypeError:
        return await websockets.connect(
            OPENAI_REALTIME_URL,
            extra_headers=headers,
            ping_interval=20,
            ping_timeout=20,
        )


async def main():
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is missing. Add it to your local .env file first."
        )

    print("Connecting to OpenAI Realtime...")

    async with await connect_to_openai() as websocket:
        print("Connected. Waiting for first server event...")

        raw_message = await websocket.recv()
        message = json.loads(raw_message)

        print("Received event:")
        print(json.dumps(message, indent=2)[:1000])

    print("OpenAI smoke test complete.")


if __name__ == "__main__":
    asyncio.run(main())