from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTHUB_")

    app_name: str = "AgentHub"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000

    # LLM config
    llm_provider: str = "openai"   # openai | anthropic
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""


settings = Settings()
