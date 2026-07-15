"""Webhook callback endpoints for Slack and Telegram integrations."""
import contextlib
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request

logger = logging.getLogger("routers.webhook")
router = APIRouter(tags=["webhook"])


@router.get("/webhook/channels")
async def webhook_channel_status():
    from app.services.webhook_gateway import webhook_gateway
    return {"status": "ok", "channels": webhook_gateway.channel_status()}


@router.post("/webhook/channels/{channel}/test")
async def test_webhook_channel(channel: str):
    if channel not in ("slack", "telegram"):
        raise HTTPException(status_code=404, detail="Unknown notification channel")
    from app.services.webhook_gateway import webhook_gateway
    if not webhook_gateway.channel_status()[channel]:
        raise HTTPException(status_code=503, detail=f"{channel.title()} is not configured")
    if not await webhook_gateway.test_channel(channel):
        raise HTTPException(status_code=502, detail=f"{channel.title()} delivery test failed")
    return {"status": "ok", "channel": channel}


@router.post("/webhook/callback/slack")
async def slack_webhook_callback(request: Request):
    """Slack interactive actions callback endpoint."""
    try:
        timestamp = request.headers.get("X-Slack-Request-Timestamp")
        signature = request.headers.get("X-Slack-Signature")
        body_bytes = await request.body()

        signing_secret = os.environ.get("AGENTHUB_SLACK_SIGNING_SECRET")
        if signing_secret:
            if not timestamp or not signature:
                raise HTTPException(status_code=401, detail="Missing Slack verification headers")
            from app.services.webhook_gateway import verify_slack_signature
            if not verify_slack_signature(signing_secret, body_bytes, timestamp, signature):
                raise HTTPException(status_code=403, detail="Invalid Slack signature")
        else:
            raise HTTPException(status_code=503, detail="Slack webhook not configured. Set AGENTHUB_SLACK_SIGNING_SECRET to enable.")

        import urllib.parse
        body_str = body_bytes.decode("utf-8")
        payload = None

        if body_str.startswith("payload="):
            parsed = urllib.parse.parse_qs(body_str)
            payload_str = parsed.get("payload", [None])[0]
            if payload_str:
                payload = json.loads(payload_str)

        if not payload:
            with contextlib.suppress(json.JSONDecodeError):
                payload = json.loads(body_str)

        if not payload:
            return {"success": False, "error": "Invalid form-data or JSON payload"}

        from app.services.webhook_gateway import webhook_gateway
        res = await webhook_gateway.handle_slack_callback(payload)
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Slack webhook error: {e}")
        return {"success": False, "error": str(e)}


@router.post("/webhook/callback/telegram")
async def telegram_webhook_callback(request: Request):
    """Telegram inline keyboard button click callback endpoint."""
    try:
        received_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
        secret_token = os.environ.get("AGENTHUB_TELEGRAM_SECRET_TOKEN")

        if secret_token:
            if not received_token:
                raise HTTPException(status_code=401, detail="Missing Telegram verification token")
            from app.services.webhook_gateway import verify_telegram_secret_token
            if not verify_telegram_secret_token(secret_token, received_token):
                raise HTTPException(status_code=403, detail="Invalid Telegram secret token")
        else:
            raise HTTPException(status_code=503, detail="Telegram webhook not configured. Set AGENTHUB_TELEGRAM_SECRET_TOKEN to enable.")

        payload = await request.json()
        from app.services.webhook_gateway import webhook_gateway
        res = await webhook_gateway.handle_telegram_callback(payload)
        return res
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return {"success": False, "error": str(e)}
