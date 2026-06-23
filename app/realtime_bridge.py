import json
from pathlib import Path
from typing import Any

from app.scenarios import Scenario
from app.transcript import TranscriptLogger


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

Scenario title:
{scenario.title}

Scenario goal:
{scenario.goal}

Scenario details:
{scenario.patient_prompt}
""".strip()


async def run_realtime_bridge(twilio_ws: Any, scenario: Scenario) -> None:
    """
    Temporary bridge stub.

    This proves main.py can import and call the bridge.
    In the next step, we will replace this with the real
    Twilio <-> OpenAI Realtime audio bridge.
    """
    transcript = TranscriptLogger(scenario.id)

    transcript.add_note("Realtime bridge stub started.")
    transcript.add_note("Patient instructions were generated successfully.")

    instructions_path = get_call_folder(scenario.id) / "patient_instructions.txt"

    with instructions_path.open("w", encoding="utf-8") as file:
        file.write(build_patient_instructions(scenario))

    print(f"[{scenario.id}] Realtime bridge stub started.")
    print(f"[{scenario.id}] Saved patient instructions to {instructions_path}")

    await twilio_ws.close()