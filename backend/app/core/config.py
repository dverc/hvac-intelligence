from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # App
    APP_NAME: str = "HVAC-Intelligence API"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
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

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

@lru_cache()
def get_settings() -> Settings:
    return Settings()
