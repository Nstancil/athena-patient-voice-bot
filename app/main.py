import json
from pathlib import Path


from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import PlainTextResponse, Response

from twilio.twiml.voice_response import VoiceResponse

from app.config import settings
from app.scenarios import SCENARIOS

app = FastAPI(title="Athena Patient Voice Bot")

CALLS_DIR = Path("calls")


def get_call_folder(scenario_id: str) -> Path:
    folder = CALLS_DIR / scenario_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder

def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def find_scenario(scenario_id: str):
    for scenario in SCENARIOS:
        if scenario.id == scenario_id:
            return scenario

    return None

def public_url_to_websocket_url(public_url: str) -> str:
    """
    For WebSocket connections, we need to convert the public URL to a WebSocket URL.
    """
    clean_url = public_url.rstrip("/")

    if clean_url.startswith("https://"):
        return clean_url.replace("https://", "wss://", 1)

    if clean_url.startswith("http://"):
        return clean_url.replace("http://", "ws://", 1)

    raise ValueError(
        "PUBLIC_BASE_URL must start with http:// or https://"
    )

@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "app": "athena-patient-voice-bot",
    }


@app.post("/voice/{scenario_id}")
async def voice_webhook(scenario_id: str):
    """
    Twilio hits this endpoint when the outbound call connects.

    We respond with TwiML telling Twilio:
    """
    scenario = find_scenario(scenario_id)

    if scenario is None:
        response = VoiceResponse()
        response.say("Sorry, this test scenario was not found.")
        response.hangup()

        return Response(
            content=str(response),
            media_type="application/xml",
        )

    websocket_base_url = public_url_to_websocket_url(settings.public_base_url)
    stream_url = f"{websocket_base_url}/media/{scenario_id}"

    call_folder = get_call_folder(scenario_id)

    save_json(
        call_folder / "voice_webhook.json",
        {
            "scenario_id": scenario_id,
            "scenario_title": scenario.title,
            "stream_url": stream_url,
        },
    )

    response = VoiceResponse()

    connect = response.connect()
    connect.stream(url=stream_url)

    return Response(
        content=str(response),
        media_type="application/xml",
    )


@app.websocket("/media/{scenario_id}")
async def media_stream(websocket: WebSocket, scenario_id: str):
    """
    Twilio connects here after receiving the TwiML from /voice/{scenario_id}.

   
    """
    await websocket.accept()

    call_folder = get_call_folder(scenario_id)
    events_path = call_folder / "twilio_events.jsonl"

    print(f"WebSocket connected for scenario: {scenario_id}")

    try:
        while True:
            raw_message = await websocket.receive_text()
            message = json.loads(raw_message)

            event_type = message.get("event")

            with events_path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(message) + "\n")

            if event_type == "connected":
                print(f"[{scenario_id}] Twilio connected")

            elif event_type == "start":
                start_data = message.get("start", {})
                stream_sid = start_data.get("streamSid")
                call_sid = start_data.get("callSid")

                print(f"[{scenario_id}] Stream started")
                print(f"  streamSid: {stream_sid}")
                print(f"  callSid: {call_sid}")

                save_json(
                    call_folder / "stream_start.json",
                    {
                        "scenario_id": scenario_id,
                        "stream_sid": stream_sid,
                        "call_sid": call_sid,
                        "raw_start": start_data,
                    },
                )

            elif event_type == "media":
                # Audio chunks arrive here.
                
                pass

            elif event_type == "stop":
                print(f"[{scenario_id}] Stream stopped")
                save_json(
                    call_folder / "stream_stop.json",
                    {
                        "scenario_id": scenario_id,
                        "raw_stop": message.get("stop", {}),
                    },
                )
                break

            else:
                print(f"[{scenario_id}] Event: {event_type}")

    except WebSocketDisconnect:
        print(f"WebSocket disconnected for scenario: {scenario_id}")

    except Exception as error:
        print(f"WebSocket error for {scenario_id}: {error}")

    finally:
        print(f"WebSocket closed for scenario: {scenario_id}")


@app.post("/twilio/status/{scenario_id}")
async def twilio_status_callback(scenario_id: str, request: Request):
    """
    Twilio sends call status updates here.
    """
    form = await request.form()
    data = dict(form)

    call_folder = get_call_folder(scenario_id)
    save_json(call_folder / "status_callback.json", data)

    print(f"[{scenario_id}] Status callback: {data.get('CallStatus')}")

    return PlainTextResponse("ok")


@app.post("/twilio/recording/{scenario_id}")
async def twilio_recording_callback(scenario_id: str, request: Request):
    """
    Twilio sends recording info here after a recording is available.

    """
    form = await request.form()
    data = dict(form)

    call_folder = get_call_folder(scenario_id)
    save_json(call_folder / "recording_callback.json", data)

    print(f"[{scenario_id}] Recording callback received")

    return PlainTextResponse("ok")
