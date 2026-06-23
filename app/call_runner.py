import argparse
import json
from pathlib import Path

from twilio.rest import Client

from app.config import (
    settings,
    validate_assessment_number,
    require_env_for_live_calls,
)
from app.scenarios import list_scenarios


CALLS_DIR = Path("calls")


def create_call_folder(call_id: str) -> Path:
    folder = CALLS_DIR / call_id
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def save_call_metadata(folder: Path, data: dict) -> None:
    metadata_path = folder / "metadata.json"

    with metadata_path.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)


def dry_run_calls(count: int) -> None:
    scenarios = list_scenarios()

    print("\nDRY RUN ONLY — no phone calls will be placed.\n")

    for index in range(count):
        scenario = scenarios[index % len(scenarios)]
        folder = create_call_folder(scenario.id)

        metadata = {
            "call_id": scenario.id,
            "title": scenario.title,
            "goal": scenario.goal,
            "status": "dry-run",
            "to_number": settings.assessment_number,
        }

        save_call_metadata(folder, metadata)

        print(f"[DRY RUN] {scenario.id}: {scenario.title}")
        print(f"Goal: {scenario.goal}")
        print(f"Saved: {folder / 'metadata.json'}")
        print("-" * 60)


def place_live_calls(count: int) -> None:
    require_env_for_live_calls()
    validate_assessment_number(settings.assessment_number)

    client = Client(
        settings.twilio_account_sid,
        settings.twilio_auth_token,
    )

    scenarios = list_scenarios()

    for index in range(count):
        scenario = scenarios[index % len(scenarios)]
        folder = create_call_folder(scenario.id)

        voice_url = f"{settings.public_base_url}/voice/{scenario.id}"
        status_callback_url = f"{settings.public_base_url}/twilio/status/{scenario.id}"
        recording_callback_url = f"{settings.public_base_url}/twilio/recording/{scenario.id}"

        print(f"Placing call for scenario: {scenario.id} - {scenario.title}")
        print(f"Voice webhook: {voice_url}")

        call = client.calls.create(
            to=settings.assessment_number,
            from_=settings.twilio_from_number,
            url=voice_url,
            method="POST",
            status_callback=status_callback_url,
            status_callback_method="POST",
            record=True,
            recording_status_callback=recording_callback_url,
            recording_status_callback_method="POST",
        )

        metadata = {
            "call_id": scenario.id,
            "title": scenario.title,
            "goal": scenario.goal,
            "status": "started",
            "twilio_call_sid": call.sid,
            "to_number": settings.assessment_number,
            "voice_url": voice_url,
            "status_callback_url": status_callback_url,
            "recording_callback_url": recording_callback_url,
        }

        save_call_metadata(folder, metadata)

        print(f"Started Twilio call SID: {call.sid}")
        print(f"Saved: {folder / 'metadata.json'}")
        print("-" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Athena patient voice bot test calls."
    )

    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of scenarios/calls to run.",
    )

    parser.add_argument(
        "--live",
        action="store_true",
        help="Actually place calls through Twilio. Default is dry-run only.",
    )

    args = parser.parse_args()

    if args.count < 1:
        raise ValueError("--count must be at least 1")

    if args.live:
        place_live_calls(args.count)
    else:
        dry_run_calls(args.count)


if __name__ == "__main__":
    main()
