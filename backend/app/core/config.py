import os
import base64
import hashlib
import logging
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("config.encryption")


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


# ---- Fernet symmetric encryption key management ----
# Read encryption key (Base64-encoded 32 bytes) from AGENTHUB_ENCRYPT_KEY env var.
# If not set, derive a deterministic key from machine fingerprint (local dev compat).
# Production MUST set AGENTHUB_ENCRYPT_KEY for cross-instance decryption.

def _derive_fernet_key() -> bytes:
    """Derive a Fernet-compatible 32-byte key from the environment or machine fingerprint."""
    env_key = os.environ.get("AGENTHUB_ENCRYPT_KEY", "")
    if env_key:
        raw = hashlib.sha256(env_key.encode("utf-8")).digest()
    else:
        import platform, getpass
        fingerprint = f"agenthub:{platform.node()}:{getpass.getuser()}"
        raw = hashlib.sha256(fingerprint.encode("utf-8")).digest()
        logger.info("AGENTHUB_ENCRYPT_KEY not set, using machine-derived encryption key. "
                     "Set this env var for multi-instance deployments.")
    return base64.urlsafe_b64encode(raw)


def obfuscate_key(key: str) -> str:
    """Encrypt API key with Fernet symmetric encryption to avoid plaintext on disk."""
    if not key:
        return ""
    if key.startswith("fnt::"):
        return key
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_derive_fernet_key())
        encrypted = f.encrypt(key.encode("utf-8"))
        return "fnt::" + encrypted.decode("utf-8")
    except ImportError:
        logger.warning("cryptography package not installed, falling back to plain storage for API key.")
        return key
    except Exception as e:
        logger.error(f"Failed to encrypt API key: {e}")
        return key


def deobfuscate_key(obfuscated_key: str) -> str:
    """Decrypt Fernet-encrypted key. Backward-compatible with legacy enc:: XOR format."""
    if not obfuscated_key:
        return ""
    # New format: Fernet encryption
    if obfuscated_key.startswith("fnt::"):
        try:
            from cryptography.fernet import Fernet
            f = Fernet(_derive_fernet_key())
            decrypted = f.decrypt(obfuscated_key[5:].encode("utf-8"))
            return decrypted.decode("utf-8")
        except ImportError:
            logger.warning("cryptography package not installed, cannot decrypt API key.")
            return obfuscated_key
        except Exception as e:
            logger.error(f"Failed to decrypt API key: {e}")
            return obfuscated_key
    # Legacy format backward compat: XOR encoding
    if obfuscated_key.startswith("enc::"):
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
    # Plaintext
    return obfuscated_key
