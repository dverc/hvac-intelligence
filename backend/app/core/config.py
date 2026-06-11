import warnings
from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings

# Project root .env (backend/app/core -> ../../../.env)
_ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

class Settings(BaseSettings):
    # App
    APP_NAME: str = "HVAC-Intelligence API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "development"

    # Dashboard API authentication (required — no default; set in .env)
    DASHBOARD_API_KEY: str

    # JWT authentication (set JWT_SECRET_KEY in .env for production)
    JWT_SECRET_KEY: str = "dev-secret-change-in-production"

    # Dashboard tenant scoping (stopgap until JWT carries org in a later phase).
    # Defaults to the deterministic seed org so single-tenant dev keeps working.
    DASHBOARD_ORG_ID: str = "00000000-0000-4000-8000-000000000001"

    # Vapi webhook HMAC bypass — local dev only; ignored in production
    VAPI_WEBHOOK_HMAC_BYPASS: bool = False

    # Fallback inbound number used to resolve a tenant when the webhook
    # payload does not carry the called number.
    VAPI_PHONE_NUMBER: str = ""
    
    # Database
    DATABASE_URL: str                    # postgresql+asyncpg://user:pass@host:5432/hvac_intel
    DATABASE_POOL_SIZE: int = 20
    DATABASE_MAX_OVERFLOW: int = 10
    
    # AI Services
    ANTHROPIC_API_KEY: str
    OPENAI_API_KEY: str                  # for embeddings
    VAPI_API_KEY: str
    VAPI_WEBHOOK_SECRET: str
    VAPI_ASSISTANT_ID: str
    VAPI_PHONE_NUMBER_ID: str = ""

    # SMS (Twilio — optional; empty disables outbound SMS)
    TWILIO_ACCOUNT_SID: str = ""
    TWILIO_AUTH_TOKEN: str = ""
    TWILIO_FROM_NUMBER: str = ""

    # Email reports (SendGrid — optional; empty disables outbound email)
    SENDGRID_API_KEY: str = ""
    REPORT_FROM_EMAIL: str = "reports@hvac-intelligence.com"
    REPORT_FROM_NAME: str = "HVAC Intelligence"
    
    # Vector DB
    PINECONE_API_KEY: str
    PINECONE_ENVIRONMENT: str            # "us-east-1"
    PINECONE_INDEX_NAME: str = "hvac-knowledge"
    
    # Kafka
    KAFKA_BOOTSTRAP_SERVERS: str        # "localhost:9092"
    KAFKA_TOPIC_CALL_FEATURES: str = "call.features"
    KAFKA_TOPIC_CHURN_SCORES: str = "churn.scores"
    KAFKA_TOPIC_HIGH_RISK_ALERTS: str = "alerts.high_risk"
    
    # Redis / Celery
    REDIS_URL: str                       # "redis://localhost:6379/0"
    
    # ML Model
    MODEL_ARTIFACTS_PATH: str = "/app/ml/artifacts"
    CHURN_SCORE_THRESHOLD_HIGH: float = 0.60
    CHURN_SCORE_THRESHOLD_CRITICAL: float = 0.80
    FEATURE_WINDOW_DAYS: int = 90
    SCORING_CADENCE_HOURS: int = 6

    # RAG
    RAG_MOCK_INDEX_PATH: str = "data/knowledge/.mock_vector_index.json"
    RAG_EMBEDDING_MODEL: str = "text-embedding-3-small"
    RAG_EMBEDDING_DIM: int = 1536
    RAG_MMR_LAMBDA: float = 0.5

    # Google Calendar OAuth (secrets in .env only — never commit)
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_OAUTH_REDIRECT_URI: str = (
        "http://localhost:8000/api/v1/integrations/google/oauth/callback"
    )
    GOOGLE_CALENDAR_SCOPES: list[str] = [
        "https://www.googleapis.com/auth/calendar.events",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/drive.readonly",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
    ]
    GOOGLE_TOKEN_ENCRYPTION_KEY: str = ""
    FRONTEND_BASE_URL: str = "http://localhost:3000"

    # Jobber OAuth (secrets in .env only — never commit)
    JOBBER_CLIENT_ID: str = ""
    JOBBER_CLIENT_SECRET: str = ""
    JOBBER_OAUTH_REDIRECT_URI: str = (
        "http://localhost:8000/api/v1/integrations/jobber/oauth/callback"
    )

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        if not self.DASHBOARD_API_KEY.strip():
            raise ValueError(
                "DASHBOARD_API_KEY must be set to a non-empty value. "
                "Generate one with: openssl rand -hex 32"
            )
        if (
            self.ENVIRONMENT == "production"
            and self.JWT_SECRET_KEY == "dev-secret-change-in-production"
        ):
            raise ValueError(
                "JWT_SECRET_KEY must be changed from the default value in production"
            )
        if self.ENVIRONMENT == "production" and self.VAPI_WEBHOOK_HMAC_BYPASS:
            warnings.warn(
                "VAPI_WEBHOOK_HMAC_BYPASS is enabled but ignored in production. "
                "Set VAPI_WEBHOOK_HMAC_BYPASS=false in production.",
                stacklevel=2,
            )
        return self

    class Config:
        env_file = str(_ROOT_ENV_FILE)
        case_sensitive = True
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
