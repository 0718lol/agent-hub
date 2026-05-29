from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTHUB_")

    app_name: str = "AgentHub"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # CORS whitelist
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # LLM config
    llm_provider: str = "openai"   # openai | anthropic
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # Redis config
    redis_url: str = "redis://localhost:6379/0"


settings = Settings()
