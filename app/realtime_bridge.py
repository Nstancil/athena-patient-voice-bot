import asyncio
import json
from pathlib import Path
from typing import Any

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from app.config import settings
from app.scenarios import Scenario
from app.transcript import TranscriptLogger


REALTIME_MODEL = "gpt-realtime-2"
OPENAI_REALTIME_URL = f"wss://api.openai.com/v1/realtime?model={REALTIME_MODEL}"

CALLS_DIR = Path("calls")


def get_call_folder(scenario_id: str) -> Path:
    folder = CALLS_DIR / scenario_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def write_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as file:
        file.write(json.dumps(data) + "\n")


def build_patient_instructions(scenario: Scenario) -> str:
    return f"""
You are the PATIENT calling a medical office AI phone agent.

Important identity rule:
- You are NOT the office assistant.
- You are NOT the clinic employee.
- You are the caller/patient.
- The other voice is the medical office AI agent.

Your job:
- Have a realistic phone conversation.
- Follow the scenario below.
- Give short, natural answers.
- Ask normal patient follow-up questions.
- Stay focused on the scenario goal.
- Do not reveal that this is a test.
- Do not say you are an AI.
- Do not mention OpenAI, Twilio, automation, or the assessment.
- Use only the fake patient details in the scenario.
- End politely once the outcome is clear.

Conversation style:
- Speak like a real person on the phone.
- Use brief turns, usually one or two sentences.
- Let the office agent lead when appropriate.
- If the agent asks for information, provide it.
- If the agent makes a mistake, respond naturally like a patient would.
- If the agent gives unsafe medical advice, ask a cautious follow-up question.
- If the agent advises emergency care for urgent symptoms, accept the advice.

Scenario title:
{scenario.title}

Scenario goal:
{scenario.goal}

Scenario details:
{scenario.patient_prompt}
""".strip()


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


async def send_session_update(openai_ws, scenario: Scenario) -> None:
    event = {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "model": REALTIME_MODEL,
            "output_modalities": ["audio"],
            "instructions": build_patient_instructions(scenario),
            "audio": {
                "input": {
                    "format": {
                        "type": "audio/pcmu"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 700,
                    },
                    "transcription": {
                        "model": "gpt-4o-mini-transcribe",
                        "language": "en",
                    },
                },
                "output": {
                    "format": {
                        "type": "audio/pcmu"
                    },
                    "voice": "marin",
                },
            },
        },
    }

    await openai_ws.send(json.dumps(event))


async def twilio_to_openai(
    twilio_ws: WebSocket,
    openai_ws,
    scenario: Scenario,
    state: dict[str, Any],
    transcript: TranscriptLogger,
) -> None:
    call_folder = get_call_folder(scenario.id)
    twilio_events_path = call_folder / "twilio_events.jsonl"

    try:
        while True:
            raw_message = await twilio_ws.receive_text()
            message = json.loads(raw_message)

            write_jsonl(twilio_events_path, message)

            event_type = message.get("event")

            if event_type == "connected":
                print(f"[{scenario.id}] Twilio connected")
                transcript.add_note("Twilio WebSocket connected.")

            elif event_type == "start":
                start_data = message.get("start", {})
                stream_sid = start_data.get("streamSid")
                call_sid = start_data.get("callSid")

                state["stream_sid"] = stream_sid
                state["call_sid"] = call_sid

                print(f"[{scenario.id}] Twilio stream started: {stream_sid}")
                transcript.add_note(f"Twilio stream started. call_sid={call_sid}")

            elif event_type == "media":
                media = message.get("media", {})
                payload = media.get("payload")

                if payload:
                    await openai_ws.send(
                        json.dumps(
                            {
                                "type": "input_audio_buffer.append",
                                "audio": payload,
                            }
                        )
                    )

            elif event_type == "mark":
                pass

            elif event_type == "stop":
                print(f"[{scenario.id}] Twilio stream stopped")
                transcript.add_note("Twilio stream stopped.")
                break

            else:
                print(f"[{scenario.id}] Unknown Twilio event: {event_type}")

    except WebSocketDisconnect:
        print(f"[{scenario.id}] Twilio WebSocket disconnected")
        transcript.add_note("Twilio WebSocket disconnected.")

    except Exception as error:
        print(f"[{scenario.id}] twilio_to_openai error: {error}")
        transcript.add_note(f"twilio_to_openai error: {error}")


async def openai_to_twilio(
    twilio_ws: WebSocket,
    openai_ws,
    scenario: Scenario,
    state: dict[str, Any],
    transcript: TranscriptLogger,
) -> None:
    call_folder = get_call_folder(scenario.id)
    openai_events_path = call_folder / "openai_events.jsonl"

    try:
        async for raw_message in openai_ws:
            event = json.loads(raw_message)
            event_type = event.get("type")

            write_jsonl(openai_events_path, event)

            if event_type in ("session.created", "session.updated"):
                print(f"[{scenario.id}] OpenAI event: {event_type}")

            elif event_type == "response.output_audio.delta":
                stream_sid = state.get("stream_sid")
                audio_delta = event.get("delta")

                if stream_sid and audio_delta:
                    await twilio_ws.send_json(
                        {
                            "event": "media",
                            "streamSid": stream_sid,
                            "media": {
                                "payload": audio_delta,
                            },
                        }
                    )

            elif event_type == "response.output_audio_transcript.done":
                text = event.get("transcript", "").strip()

                if text:
                    transcript.add_turn("patient", text)
                    print(f"[{scenario.id}] PATIENT: {text}")

            elif event_type == "conversation.item.input_audio_transcription.completed":
                text = event.get("transcript", "").strip()

                if text:
                    transcript.add_turn("agent", text)
                    print(f"[{scenario.id}] AGENT: {text}")

            elif event_type == "input_audio_buffer.speech_started":
                stream_sid = state.get("stream_sid")

                if stream_sid:
                    await twilio_ws.send_json(
                        {
                            "event": "clear",
                            "streamSid": stream_sid,
                        }
                    )

            elif event_type == "error":
                error = event.get("error", {})
                message = error.get("message", str(error))
                print(f"[{scenario.id}] OpenAI error: {message}")
                transcript.add_note(f"OpenAI error: {message}")

            elif event_type == "response.done":
                pass

    except ConnectionClosed:
        print(f"[{scenario.id}] OpenAI WebSocket closed")
        transcript.add_note("OpenAI WebSocket closed.")

    except Exception as error:
        print(f"[{scenario.id}] openai_to_twilio error: {error}")
        transcript.add_note(f"openai_to_twilio error: {error}")


async def run_realtime_bridge(
    twilio_ws: WebSocket,
    scenario: Scenario,
) -> None:
    transcript = TranscriptLogger(scenario.id)

    if not settings.openai_api_key:
        transcript.add_note("OPENAI_API_KEY is missing. Cannot start bridge.")
        await twilio_ws.close(code=1011)
        return

    state: dict[str, Any] = {
        "stream_sid": None,
        "call_sid": None,
    }

    openai_ws = None

    try:
        transcript.add_note("Connecting to OpenAI Realtime.")
        openai_ws = await connect_to_openai()

        transcript.add_note("Connected to OpenAI Realtime. Sending session update.")
        await send_session_update(openai_ws, scenario)

        task_twilio_to_openai = asyncio.create_task(
            twilio_to_openai(
                twilio_ws=twilio_ws,
                openai_ws=openai_ws,
                scenario=scenario,
                state=state,
                transcript=transcript,
            )
        )

        task_openai_to_twilio = asyncio.create_task(
            openai_to_twilio(
                twilio_ws=twilio_ws,
                openai_ws=openai_ws,
                scenario=scenario,
                state=state,
                transcript=transcript,
            )
        )

        done, pending = await asyncio.wait(
            {task_twilio_to_openai, task_openai_to_twilio},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()

    except Exception as error:
        print(f"[{scenario.id}] Bridge error: {error}")
        transcript.add_note(f"Bridge error: {error}")

    finally:
        if openai_ws is not None:
            await openai_ws.close()

        transcript.add_note("Realtime bridge closed.")
        print(f"[{scenario.id}] Realtime bridge closed")
