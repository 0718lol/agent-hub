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

    # Sandbox config
    docker_sandbox: bool = True

    # Security config
    api_secret: str = ""
    allow_unsandboxed_shell: bool = False
    shell_timeout: float = 15.0
    shell_memory_limit_mb: int = 256


settings = Settings()


import base64

def obfuscate_key(key: str) -> str:
    """对密钥进行轻量级异或 Base64 编码，避免明文落盘持久化。"""
    if not key:
        return ""
    # 若已经是混淆后的密钥（Base64特征校验），则不重复处理
    if key.startswith("enc::"):
        return key
    salt = b"agenthub_secret_salt_2026"
    key_bytes = key.encode("utf-8")
    obfuscated = bytearray()
    for i, b in enumerate(key_bytes):
        obfuscated.append(b ^ salt[i % len(salt)])
    return "enc::" + base64.b64encode(obfuscated).decode("utf-8")


def deobfuscate_key(obfuscated_key: str) -> str:
    """还原经过混淆的密钥值。"""
    if not obfuscated_key:
        return ""
    if not obfuscated_key.startswith("enc::"):
        return obfuscated_key
    try:
        raw_encoded = obfuscated_key[5:]
        salt = b"agenthub_secret_salt_2026"
        obfuscated_bytes = base64.b64decode(raw_encoded.encode("utf-8"))
        deobfuscated = bytearray()
        for i, b in enumerate(obfuscated_bytes):
            deobfuscated.append(b ^ salt[i % len(salt)])
        return deobfuscated.decode("utf-8")
    except Exception:
        return obfuscated_key


