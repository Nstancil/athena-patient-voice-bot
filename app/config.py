from pydantic_settings import BaseSettings
from pydantic import Field  


class Settings(BaseSettings):
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    twilio_account_sid: str = Field(..., env="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field(..., env="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field(..., env="TWILIO_FROM_NUMBER")

    public_base_url: str = Field(..., env="PUBLIC_BASE_URL")

    # Default assessment number (safety guard) can be overridden via env
    assessment_number: str = Field("+18054398008", env="ASSESSMENT_NUMBER")

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()


def validate_assessment_number(to_number: str) -> None:
    """
    Safety guard.

    The challenge says all test calls must go only to +1-805-439-8008.
    This prevents accidental calls to any other number.
    """
    normalized = to_number.replace("-", "").replace(" ", "")

    if normalized != settings.assessment_number:
        raise ValueError(
            f"Blocked unsafe outbound call to {to_number}. "
            f"This bot can only call {settings.assessment_number}."
        )


def require_env_for_live_calls() -> None:
    
    " Add the required environment variables 6/22 " 
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