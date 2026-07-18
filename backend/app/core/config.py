import base64
import hashlib
import logging
import os

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("config.encryption")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTHUB_")

    app_name: str = "AgentHub"
    debug: bool = True
    host: str = "0.0.0.0"  # nosec B104
    port: int = 8000

    # CORS whitelist
    allowed_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:80",
        "http://localhost",
        "http://127.0.0.1",
    ]

    def __init__(self, **values):
        super().__init__(**values)
        env_origins = os.environ.get("AGENTHUB_ALLOWED_ORIGINS", "")
        if env_origins:
            self.allowed_origins = [o.strip() for o in env_origins.split(",") if o.strip()]

    # LLM config
    llm_provider: str = "openai"   # openai | anthropic
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""

    # Redis config
    redis_url: str = "redis://localhost:6379/0"
    auto_migrate: bool = True

    # Sandbox config
    docker_sandbox: bool = True
    runtime_sandbox_image: str = "agenthub-runtime-sandbox:local"
    runtime_sandbox_memory: str = "768m"
    runtime_sandbox_cpus: str = "1.5"
    runtime_sandbox_pids: int = 128
    runtime_sandbox_timeout: int = 120
    runtime_sandbox_max_concurrency: int = 4
    runtime_sandbox_max_per_tenant: int = 1
    runtime_sandbox_queue_timeout: int = 30
    runtime_sandbox_dependency_timeout: int = 300
    runtime_sandbox_dependency_cache_max: int = 100
    runtime_sandbox_docker_probe_ttl: float = 15.0
    runtime_sandbox_archive_max_bytes: int = 50 * 1024 * 1024
    runtime_sandbox_archive_max_files: int = 2_000
    preview_runtime_max_total: int = 8
    preview_runtime_max_per_tenant: int = 2
    runtime_dependency_network: str = "bridge"
    runtime_npm_registry: str = "https://registry.npmjs.org"
    runtime_pypi_index_url: str = "https://pypi.org/simple"
    e2b_template_id: str = "code-interpreter"

    # Security config
    api_secret: str = ""
    auth_mode: str = "shared"  # shared | proxy
    trusted_proxy_secret: str = ""
    trusted_identity_header: str = "x-agenthub-auth-user"
    trusted_role_header: str = "x-agenthub-auth-role"
    api_client_tokens_json: str = ""
    login_attempts_per_minute: int = 10
    allow_unsandboxed_shell: bool = False
    shell_timeout: float = 15.0
    shell_memory_limit_mb: int = 256
    upload_max_bytes: int = 50 * 1024 * 1024
    knowledge_upload_max_bytes: int = 25 * 1024 * 1024
    speech_upload_max_bytes: int = 25 * 1024 * 1024

    # Shared file/vector storage for multi-host deployments
    storage_backend: str = "local"  # local | s3
    s3_bucket: str = ""
    s3_prefix: str = "agenthub"
    s3_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_access_key_id: str = ""
    s3_secret_access_key: str = ""
    chroma_host: str = ""
    chroma_port: int = 8000
    chroma_ssl: bool = False

    # Static site deployment (Netlify Deploy API)
    netlify_token: str = ""
    netlify_site_id: str = ""

    # Persistent deployment workers and generated API runtimes
    deployment_queue: str = "agenthub:deployments"
    deployment_status_ttl: int = 30 * 24 * 60 * 60
    public_base_url: str = ""
    runtime_network: str = "agenthub_runtime"
    api_runtime_memory: str = "512m"
    api_runtime_cpus: str = "1.0"
    api_runtime_pids: int = 128
    builder_image: str = "agenthub-deployment-worker:local"
    generated_projects_volume: str = "agenthub_generated_projects"
    deployment_build_network: str = "default"
    deployment_build_memory: str = "2g"
    deployment_build_cpus: str = "2.0"
    deployment_build_pids: int = 256
    allow_host_docker_socket: bool = False
    deployment_retention_days: int = 7
    deployment_max_per_user: int = 20
    scheduler_leader_ttl: int = 20
    generation_worker_enabled: bool = False
    generation_queue: str = "agenthub:generations"
    generation_status_ttl: int = 7 * 24 * 60 * 60
    generation_reclaim_idle_ms: int = 2 * 60_000
    generation_max_attempts: int = 1
    generation_lease_ttl: int = 90
    generation_max_per_user: int = 2
    llm_daily_token_quota: int = 0

    def validate_production_security(self) -> None:
        """Reject production startup when required secrets are absent."""
        if self.debug:
            return
        missing = []
        if not self.api_secret or len(self.api_secret) < 32:
            missing.append("AGENTHUB_API_SECRET (at least 32 characters)")
        if not os.environ.get("AGENTHUB_ENCRYPT_KEY", ""):
            missing.append("AGENTHUB_ENCRYPT_KEY")
        if self.auth_mode == "proxy" and len(self.trusted_proxy_secret) < 32:
            missing.append("AGENTHUB_TRUSTED_PROXY_SECRET (at least 32 characters)")
        if self.auth_mode not in {"shared", "proxy"}:
            missing.append("AGENTHUB_AUTH_MODE (shared or proxy)")
        if self.storage_backend not in {"local", "s3"}:
            missing.append("AGENTHUB_STORAGE_BACKEND (local or s3)")
        if self.storage_backend == "s3" and not self.s3_bucket.strip():
            missing.append("AGENTHUB_S3_BUCKET")
        if missing:
            raise RuntimeError("Production security configuration missing: " + ", ".join(missing))

    def validate_deployment_worker_security(self) -> None:
        """Reject an implicit privileged host Docker endpoint."""
        docker_host = os.environ.get("DOCKER_HOST", "").strip()
        host_socket = os.path.exists("/var/run/docker.sock")
        if host_socket and not docker_host and not self.allow_host_docker_socket:
            raise RuntimeError(
                "Host Docker socket detected but AGENTHUB_ALLOW_HOST_DOCKER_SOCKET is false. "
                "Use an isolated remote Docker endpoint or the explicit local-development override."
            )
        if self.deployment_build_network not in {"none", "default"}:
            raise RuntimeError(
                "AGENTHUB_DEPLOYMENT_BUILD_NETWORK must be 'none' or 'default'; host networking is forbidden."
            )
        if self.storage_backend not in {"local", "s3"}:
            raise RuntimeError("AGENTHUB_STORAGE_BACKEND must be 'local' or 's3'")


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
        import getpass
        import platform
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
    except ImportError as e:
        raise RuntimeError("cryptography is required to store API keys securely") from e
    except Exception as e:
        raise RuntimeError("Failed to encrypt API key; refusing plaintext storage") from e


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
            return ""
        except Exception as e:
            logger.error(f"Failed to decrypt API key (possible key mismatch): {e}")
            return ""
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
            logger.error("Failed to decrypt legacy enc:: API key.")
            return ""
    # Plaintext
    return obfuscated_key
