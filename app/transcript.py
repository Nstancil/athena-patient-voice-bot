import json
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path


CALLS_DIR = Path("calls")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def readable_time() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@dataclass
class TranscriptTurn:
    timestamp: str
    speaker: str
    text: str
    kind: str = "turn"


class TranscriptLogger:
    """
    Saves call transcripts in two formats:

    1. transcript.txt
       Easy for humans to read.

    2. transcript.jsonl
       Easy for code or an AI analyzer to process later.
    """

    def __init__(self, scenario_id: str):
        self.scenario_id = scenario_id
        self.call_folder = CALLS_DIR / scenario_id
        self.call_folder.mkdir(parents=True, exist_ok=True)

        self.transcript_path = self.call_folder / "transcript.txt"
        self.jsonl_path = self.call_folder / "transcript.jsonl"

    def write_header(self, scenario_title: str, scenario_goal: str) -> None:
        header = (
            f"Scenario ID: {self.scenario_id}\n"
            f"Scenario Title: {scenario_title}\n"
            f"Scenario Goal: {scenario_goal}\n"
            f"Started At: {readable_time()}\n"
            f"{'=' * 70}\n\n"
        )

        with self.transcript_path.open("w", encoding="utf-8") as file:
            file.write(header)

        self._write_jsonl(
            {
                "kind": "header",
                "scenario_id": self.scenario_id,
                "scenario_title": scenario_title,
                "scenario_goal": scenario_goal,
                "timestamp": utc_now_iso(),
            }
        )

    def add_turn(self, speaker: str, text: str) -> None:
        clean_speaker = speaker.strip().upper()
        clean_text = text.strip()

        if not clean_text:
            return

        turn = TranscriptTurn(
            timestamp=utc_now_iso(),
            speaker=clean_speaker,
            text=clean_text,
        )

        human_line = f"[{readable_time()}] {clean_speaker}: {clean_text}\n"

        with self.transcript_path.open("a", encoding="utf-8") as file:
            file.write(human_line)

        self._write_jsonl(asdict(turn))

    def add_note(self, text: str) -> None:
        clean_text = text.strip()

        if not clean_text:
            return

        note = {
            "kind": "note",
            "timestamp": utc_now_iso(),
            "text": clean_text,
        }

        human_line = f"[{readable_time()}] NOTE: {clean_text}\n"

        with self.transcript_path.open("a", encoding="utf-8") as file:
            file.write(human_line)

        self._write_jsonl(note)

    def _write_jsonl(self, data: dict) -> None:
        with self.jsonl_path.open("a", encoding="utf-8") as file:
            file.write(json.dumps(data) + "\n")