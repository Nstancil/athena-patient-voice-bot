import argparse
import json
import time
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


def get_selected_scenarios(start: int, count: int):
    scenarios = list_scenarios()

    start_index = start - 1
    end_index = start_index + count

    if start_index < 0:
        raise ValueError("--start must be 1 or higher")

    if end_index > len(scenarios):
        raise ValueError(
            f"You requested calls {start} through {start + count - 1}, "
            f"but only {len(scenarios)} scenarios exist."
        )

    return scenarios[start_index:end_index]


def dry_run_calls(start: int, count: int) -> None:
    scenarios = get_selected_scenarios(start=start, count=count)

    print("\nDRY RUN ONLY — no phone calls will be placed.\n")

    for scenario in scenarios:
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


def place_live_calls(start: int, count: int, delay_seconds: int) -> None:
    require_env_for_live_calls()
    validate_assessment_number(settings.assessment_number)

    client = Client(
        settings.twilio_account_sid,
        settings.twilio_auth_token,
    )

    scenarios = get_selected_scenarios(start=start, count=count)

    for index, scenario in enumerate(scenarios):
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

        if index < len(scenarios) - 1:
            print(f"Waiting {delay_seconds} seconds before next call...")
            time.sleep(delay_seconds)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run Athena patient voice bot test calls."
    )

    parser.add_argument(
        "--start",
        type=int,
        default=1,
        help="Scenario number to start from. Example: --start 2 starts at call-002.",
    )

    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of scenarios/calls to run.",
    )

    parser.add_argument(
        "--delay-seconds",
        type=int,
        default=180,
        help="Delay between live calls so conversations do not overlap.",
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
        place_live_calls(
            start=args.start,
            count=args.count,
            delay_seconds=args.delay_seconds,
        )
    else:
        dry_run_calls(
            start=args.start,
            count=args.count,
        )


if __name__ == "__main__":
    main()
