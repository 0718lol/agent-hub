"""
Shared configuration persistence module.
Eliminates duplicate LLM/HIL config read/write logic between main.py and routers/settings.py.
"""
import json
import logging
import os

logger = logging.getLogger("config_persistence")

LLM_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "llm_config.json")
HIL_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "data", "hil_config.json")


def get_hil_settings() -> dict:
    """Load HIL (Human-in-the-Loop) settings from disk."""
    from app.core.tenancy import current_tenant_id

    tenant_id = current_tenant_id()
    if tenant_id:
        from app.core.tenant_config import get_tenant_json

        return get_tenant_json(
            tenant_id,
            "hil",
            {"human_input_mode": "NEVER", "cooldown_steps": 2},
        )
    try:
        if os.path.exists(HIL_CONFIG_PATH):
            with open(HIL_CONFIG_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to read HIL config: {e}")
    return {"human_input_mode": "NEVER", "cooldown_steps": 2}


def save_hil_settings(cfg: dict):
    """Persist HIL settings to disk."""
    from app.core.tenancy import current_tenant_id

    tenant_id = current_tenant_id()
    if tenant_id:
        from app.core.tenant_config import set_tenant_json

        set_tenant_json(tenant_id, "hil", cfg)
        return
    try:
        os.makedirs(os.path.dirname(HIL_CONFIG_PATH), exist_ok=True)
        with open(HIL_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save HIL config: {e}")


def save_llm_config(llm_client, settings):
    """Persist current LLM client configuration to disk with key obfuscation."""
    from app.core.config import obfuscate_key
    from app.core.tenancy import current_tenant_id

    tenant_id = current_tenant_id()
    if tenant_id:
        from app.core.tenant_config import set_tenant_json

        set_tenant_json(tenant_id, "llm", {
            "provider": llm_client.provider,
            "api_key": obfuscate_key(llm_client.api_key),
            "base_url": llm_client.base_url,
            "model": llm_client.model,
            "temperature": llm_client.temperature,
            "max_tokens": llm_client.max_tokens,
            "thinking_enabled": getattr(llm_client, "thinking_enabled", None),
            "thinking_mode": llm_client.thinking_mode,
        }, encrypted=True)
        return
    try:
        os.makedirs(os.path.dirname(LLM_CONFIG_PATH), exist_ok=True)
        api_key_to_save = llm_client.api_key
        # If API Key matches system default or env var, blank it out for safety
        if api_key_to_save == settings.llm_api_key or api_key_to_save == os.environ.get("ANTHROPIC_API_KEY", ""):
            api_key_to_save = ""
        else:
            api_key_to_save = obfuscate_key(api_key_to_save)

        with open(LLM_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump({
                "provider": llm_client.provider,
                "api_key": api_key_to_save,
                "base_url": llm_client.base_url,
                "model": llm_client.model,
                "temperature": llm_client.temperature,
                "max_tokens": llm_client.max_tokens,
                "thinking_enabled": getattr(llm_client, "thinking_enabled", None),
                "thinking_mode": llm_client.thinking_mode,
            }, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Failed to save LLM config: {e}")


def load_llm_config(llm_client, settings):
    """Load LLM configuration from disk and apply to client."""
    from app.core.config import deobfuscate_key
    try:
        cfg = {}
        if os.path.exists(LLM_CONFIG_PATH):
            with open(LLM_CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)

        provider = cfg.get("provider") or settings.llm_provider
        api_key = cfg.get("api_key") or ""
        # Restore possibly obfuscated key from disk
        api_key = deobfuscate_key(api_key)

        if not api_key:
            api_key = settings.llm_api_key or os.environ.get("ANTHROPIC_API_KEY", "")

        base_url = cfg.get("base_url") or settings.llm_base_url
        model = cfg.get("model") or settings.llm_model

        llm_client.configure(
            provider=provider,
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=cfg.get("temperature"),
            max_tokens=cfg.get("max_tokens"),
            thinking_enabled=cfg.get("thinking_enabled"),
            thinking_mode=cfg.get("thinking_mode"),
        )
    except Exception as e:
        logger.error(f"Failed to load LLM config: {e}")
