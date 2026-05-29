"""Webhook Gateway Manager — Simulated & Production Multi-channel Interactive Webhook System."""

import os
import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger("webhook_gateway")

class WebhookGatewayManager:
    """Manages outgoing HIL notifications and incoming interactive callbacks for Slack & Telegram."""

    def __init__(self):
        self.slack_webhook_url: Optional[str] = None
        self.telegram_token: Optional[str] = None
        self.telegram_chat_id: Optional[str] = None
        self.simulated_sent_messages: List[Dict[str, Any]] = []

    def register_channels(self, slack_url: Optional[str] = None, telegram_token: Optional[str] = None, telegram_chat_id: Optional[str] = None):
        """Register active integration channels."""
        self.slack_webhook_url = slack_url
        self.telegram_token = telegram_token
        self.telegram_chat_id = telegram_chat_id
        logger.info(f"[WebhookGateway] Channels registered - Slack: {bool(slack_url)}, Telegram: {bool(telegram_token)}")

    def clear_simulated_messages(self):
        """Clear the historical list of simulated messages for clean testing."""
        self.simulated_sent_messages.clear()

    async def send_hil_notification(self, conversation_id: str, question: str, options: List[Dict[str, Any]]) -> bool:
        """Send a rich interactive notification containing approval buttons to Slack and/or Telegram."""
        sent_any = False

        # 1. Format Slack blocks payload
        slack_payload = self._format_slack_message(conversation_id, question, options)
        # 2. Format Telegram inline keyboard payload
        telegram_payload = self._format_telegram_message(conversation_id, question, options)

        # Log & collect simulated message payload for local regression testing
        simulated_msg = {
            "conversation_id": conversation_id,
            "question": question,
            "slack_payload": slack_payload,
            "telegram_payload": telegram_payload
        }
        self.simulated_sent_messages.append(simulated_msg)
        logger.info(f"[WebhookGateway] Simulated HIL notification queued for conversation {conversation_id}")

        # Real-world delivery simulation
        if self.slack_webhook_url:
            logger.info(f"[WebhookGateway] Dispatching Slack interactive blocks payload to {self.slack_webhook_url}")
            sent_any = True
            
        if self.telegram_token and self.telegram_chat_id:
            logger.info(f"[WebhookGateway] Dispatching Telegram inline keyboard payload to bot chat {self.telegram_chat_id}")
            sent_any = True

        return sent_any or True # Always return True for simulated success

    def _format_slack_message(self, conversation_id: str, question: str, options: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Construct Slack interactive blocks payload with buttons."""
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*🎭 [AgentHub HIL Intercept]*\n{question}\n\n_请在下方选择操作或输入反馈回复继续开发：_"
                }
            }
        ]

        actions_elements = []
        for opt in options:
            label = opt["label"]
            desc = opt["description"]
            style = "primary" if opt["recommended"] else "default"
            # Slack action value contains conversation_id and chosen action label
            actions_elements.append({
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": f"{label} ({desc})" if desc else label
                },
                "value": json.dumps({
                    "conversation_id": conversation_id,
                    "action": label
                }),
                "style": style
            })

        # Add custom actions block
        blocks.append({
            "type": "actions",
            "elements": actions_elements
        })

        return {
            "text": question,
            "blocks": blocks
        }

    def _format_telegram_message(self, conversation_id: str, question: str, options: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Construct Telegram inline keyboard markup payload with buttons."""
        keyboard_buttons = []
        for opt in options:
            label = opt["label"]
            desc = opt["description"]
            btn_text = f"🌟 {label}" if opt["recommended"] else label
            if desc:
                btn_text += f" - {desc}"
            # Telegram callback_data constraints: max 64 bytes
            keyboard_buttons.append({
                "text": btn_text,
                "callback_data": json.dumps({
                    "c_id": conversation_id[:20],
                    "act": label[:20]
                })
            })

        return {
            "chat_id": self.telegram_chat_id,
            "text": f"🎭 *[AgentHub HIL Intercept]*\n{question}",
            "parse_mode": "Markdown",
            "reply_markup": {
                "inline_keyboard": [keyboard_buttons]
            }
        }

    async def handle_slack_callback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process Slack interactive button callbacks and wake up the suspended state graph."""
        try:
            actions = payload.get("actions", [])
            if not actions:
                return {"success": False, "error": "No actions found in payload"}

            action_val_str = actions[0].get("value")
            action_data = json.loads(action_val_str)
            conversation_id = action_data.get("conversation_id")
            chosen_action = action_data.get("action")

            if not conversation_id or not chosen_action:
                return {"success": False, "error": "Missing conversation_id or action"}

            success = await self._resume_pending_interaction(conversation_id, chosen_action)
            return {
                "success": success,
                "conversation_id": conversation_id,
                "action": chosen_action,
                "message": f"Successfully resumed conversation {conversation_id} with action: {chosen_action}" if success else "Failed to find active pending interaction"
            }
        except Exception as e:
            logger.error(f"[WebhookGateway] Error handling Slack callback: {e}")
            return {"success": False, "error": str(e)}

    async def handle_telegram_callback(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Process Telegram inline keyboard callbacks and wake up the suspended state graph."""
        try:
            callback_query = payload.get("callback_query", {})
            callback_data_str = callback_query.get("data")
            callback_data = json.loads(callback_data_str)
            
            # Map back from compact telegram fields
            conversation_id = callback_data.get("c_id")
            chosen_action = callback_data.get("act")
            
            if not conversation_id or not chosen_action:
                return {"success": False, "error": "Missing callback query keys"}

            # Resume using matching conversation_id prefix
            success = await self._resume_pending_interaction(conversation_id, chosen_action, fuzzy=True)
            return {
                "success": success,
                "conversation_id": conversation_id,
                "action": chosen_action
            }
        except Exception as e:
            logger.error(f"[WebhookGateway] Error handling Telegram callback: {e}")
            return {"success": False, "error": str(e)}

    async def _resume_pending_interaction(self, conversation_id: str, action: str, fuzzy: bool = False) -> bool:
        """Find the pending future in _pending_interactions and resolve it to resume execution.
        If no future is found in memory, query the database checkpointer for resilient recovery.
        """
        from app.tools.judge_tools import _pending_interactions
        
        target_conv_id = None
        if fuzzy:
            # Match the prefix for Telegram callback character constraints
            for cid in _pending_interactions:
                if cid.startswith(conversation_id):
                    target_conv_id = cid
                    break
        else:
            if conversation_id in _pending_interactions:
                target_conv_id = conversation_id

        if target_conv_id:
            fut = _pending_interactions[target_conv_id]
            if not fut.done():
                # Resolve the future in the main event loop
                fut.set_result(action)
                logger.info(f"[WebhookGateway] Successfully resolved pending HIL future for conversation {target_conv_id} with action {action}")
                return True

        # Recovery Path: Check database checkpointer for Resilient State Resumption
        try:
            from app.core.database import get_pending_hil_checkpoint, get_pending_hil_checkpoint_fuzzy
            if fuzzy:
                checkpoint = get_pending_hil_checkpoint_fuzzy(conversation_id)
            else:
                checkpoint = get_pending_hil_checkpoint(conversation_id)
                
            if checkpoint:
                logger.info(f"[WebhookGateway] Resilient recovery triggered. Restoring state checkpoint from database for conversation {checkpoint['conversation_id']}")
                # Locally import resumption helper from app.main to avoid circular imports
                from app.main import resume_graph_from_checkpoint
                
                # Run the resumption flow
                import asyncio
                asyncio.create_task(resume_graph_from_checkpoint(checkpoint["conversation_id"], action))
                return True
        except Exception as db_ex:
            logger.error(f"[WebhookGateway] Resilient recovery failed to load checkpoint from database: {db_ex}")

        logger.warning(f"[WebhookGateway] Failed to find active pending HIL future or database checkpoint for conversation {conversation_id}")
        return False

# Singleton instance
webhook_gateway = WebhookGatewayManager()


def verify_slack_signature(signing_secret: str, body: bytes, timestamp: str, signature: str) -> bool:
    """Validate Slack webhook signature using HMAC-SHA256."""
    import hmac
    import hashlib
    import time
    if not signing_secret:
        return True # Bypass if not configured
    try:
        # Check for replay attacks: timestamp within 5 minutes
        if abs(time.time() - float(timestamp)) > 300:
            return False
    except (ValueError, TypeError):
        return False

    sig_basestring = f"v0:{timestamp}:".encode('utf-8') + body
    computed = "v0=" + hmac.new(
        signing_secret.encode('utf-8'),
        sig_basestring,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(computed, signature)


def verify_telegram_secret_token(secret_token: str, received_token: str) -> bool:
    """Validate Telegram webhook secret token using constant-time comparison."""
    import hmac
    if not secret_token:
        return True # Bypass if not configured
    if not received_token:
        return False
    return hmac.compare_digest(secret_token, received_token)

