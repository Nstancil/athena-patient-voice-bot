from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")

    twilio_account_sid: str = Field(default="", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(default="", alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field(default="", alias="TWILIO_FROM_NUMBER")

    public_base_url: str = Field(default="", alias="PUBLIC_BASE_URL")

    assessment_number: str = Field(
        default="+18054398008",
        alias="ASSESSMENT_NUMBER",
    )


settings = Settings()


def validate_assessment_number(to_number: str) -> None:
    normalized = to_number.replace("-", "").replace(" ", "")

    if normalized != settings.assessment_number:
        raise ValueError(
            f"Blocked unsafe outbound call to {to_number}. "
            f"This bot can only call {settings.assessment_number}."
        )


def require_env_for_live_calls() -> None:
    missing = []

    if not settings.twilio_account_sid:
        missing.append("TWILIO_ACCOUNT_SID")

    if not settings.twilio_auth_token:
        missing.append("TWILIO_AUTH_TOKEN")

    if not settings.twilio_from_number:
        missing.append("TWILIO_FROM_NUMBER")

    if not settings.public_base_url:
        missing.append("PUBLIC_BASE_URL")

    if missing:
        raise RuntimeError(
            "Missing required environment variables for live calls: "
            + ", ".join(missing)
        )
