import json
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import PlainTextResponse, Response
from twilio.twiml.voice_response import VoiceResponse

from app.config import settings
from app.scenarios import SCENARIOS
from app.transcript import TranscriptLogger
from app.realtime_bridge import run_realtime_bridge

import requests


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
    clean_url = public_url.rstrip("/")

    if clean_url.startswith("https://"):
        return clean_url.replace("https://", "wss://", 1)

    if clean_url.startswith("http://"):
        return clean_url.replace("http://", "ws://", 1)

    raise ValueError("PUBLIC_BASE_URL must start with http:// or https://")


@app.get("/health")
async def health_check():
    return {
        "status": "ok",
        "app": "athena-patient-voice-bot",
    }


@app.post("/voice/{scenario_id}")
async def voice_webhook(scenario_id: str):
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

    transcript = TranscriptLogger(scenario_id)
    transcript.write_header(
        scenario_title=scenario.title,
        scenario_goal=scenario.goal,
    )
    transcript.add_note("Twilio voice webhook received. Call stream is being connected.")

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
    await websocket.accept()

    scenario = find_scenario(scenario_id)

    if scenario is None:
        print(f"Unknown scenario for media stream: {scenario_id}")
        await websocket.close(code=1008)
        return

    await run_realtime_bridge(
        twilio_ws=websocket,
        scenario=scenario,
    )


@app.post("/twilio/status/{scenario_id}")
async def twilio_status_callback(scenario_id: str, request: Request):
    form = await request.form()
    data = dict(form)

    call_folder = get_call_folder(scenario_id)
    save_json(call_folder / "status_callback.json", data)

    print(f"[{scenario_id}] Status callback: {data.get('CallStatus')}")

    return PlainTextResponse("ok")


def download_recording_mp3(recording_url: str, output_path: Path) -> None:
    """
    Download Twilio recording as MP3.

    Twilio recording callback usually gives RecordingUrl without the file extension.
    Adding .mp3 downloads the MP3 version.
    """
    if not recording_url:
        return

    mp3_url = recording_url + ".mp3"

    response = requests.get(
        mp3_url,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        timeout=30,
    )

    response.raise_for_status()

    with output_path.open("wb") as file:
        file.write(response.content)

@app.post("/twilio/recording/{scenario_id}")
async def twilio_recording_callback(scenario_id: str, request: Request):
    form = await request.form()
    data = dict(form)

    call_folder = get_call_folder(scenario_id)
    save_json(call_folder / "recording_callback.json", data)

    recording_url = data.get("RecordingUrl")

    if recording_url:
        recording_path = call_folder / "recording.mp3"

        try:
            download_recording_mp3(recording_url, recording_path)
            print(f"[{scenario_id}] Recording downloaded: {recording_path}")
        except Exception as error:
            print(f"[{scenario_id}] Failed to download recording: {error}")
            save_json(
                call_folder / "recording_download_error.json",
                {
                    "error": str(error),
                    "recording_url": recording_url,
                },
            )

    print(f"[{scenario_id}] Recording callback received")

    return PlainTextResponse("ok")